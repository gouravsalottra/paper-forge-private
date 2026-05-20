from __future__ import annotations

import base64
import json
import os
import textwrap
import uuid
from pathlib import Path
from typing import Any

from storage.blob import get_artifact_url, write_artifact


def _is_test_mode() -> bool:
    return bool(os.getenv("PYTEST_CURRENT_TEST") or os.getenv("THRIVARC_STORAGE_BACKEND") == "mock")


def _workspace_seed_script(payload_url: str, token: str) -> str:
    return textwrap.dedent(
        f"""
        set -euo pipefail
        mkdir -p /workspace
        python - <<'PY'
        import base64, json, os, urllib.request
        with urllib.request.urlopen({payload_url!r}) as response:
            payload = json.loads(response.read().decode("utf-8"))
        notebook = payload.get("notebook", "")
        with open("/workspace/analysis.ipynb", "w", encoding="utf-8") as handle:
            handle.write(notebook)
        for item in payload.get("seed_files", []):
            name = os.path.basename(item.get("filename") or "seed.txt")
            content = base64.b64decode(item.get("content_b64") or "")
            with open(os.path.join("/workspace", name), "wb") as handle:
                handle.write(content)
        PY
        python -m jupyterlab \
          --ip=0.0.0.0 \
          --port=8888 \
          --ServerApp.root_dir=/workspace \
          --ServerApp.preferred_dir=/workspace \
          --ServerApp.open_browser=False \
          --ServerApp.token={token!r} \
          --ServerApp.password='' \
          --ServerApp.disable_check_xsrf=True \
          --ServerApp.allow_remote_access=True \
          --ServerApp.allow_origin='*' \
          --ServerApp.tornado_settings='{{"headers": {{"Content-Security-Policy": "frame-ancestors *"}}}}'
        """
    ).strip()


def _seed_entries(seed_files: dict[str, bytes | str] | None) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for filename, content in (seed_files or {}).items():
        if isinstance(content, str):
            raw = content.encode("utf-8")
        else:
            raw = bytes(content)
        entries.append({"filename": str(filename), "content_b64": base64.b64encode(raw).decode("ascii")})
    return entries


def _bootstrap_payload_path(session_id: str) -> str:
    return f"06_compute/notebook/bootstrap/{uuid.uuid4().hex}.json"


def _bootstrap_payload_url(session_id: str, notebook_text: str, seed_files: dict[str, bytes | str] | None) -> str:
    payload_path = _bootstrap_payload_path(session_id)
    payload = {
        "notebook": notebook_text,
        "seed_files": _seed_entries(seed_files),
    }
    write_artifact(session_id, payload_path, payload)
    return get_artifact_url(session_id, payload_path, expires_in_seconds=3600)


def launch_or_resume_workspace(
    session_id: str,
    notebook_text: str,
    seed_files: dict[str, bytes | str] | None = None,
    existing_workspace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if existing_workspace and existing_workspace.get("status") == "running" and existing_workspace.get("access_url"):
        return dict(existing_workspace)

    if _is_test_mode():
        return {
            "status": "running",
            "backend": "modal",
            "modal_account_alias": "primary",
            "sandbox_id": f"test-sandbox-{session_id}",
            "access_url": f"https://example.test/{session_id}/lab",
            "can_embed": True,
            "sync_status": "not_synced",
        }

    import modal

    from api import modal_compute

    accounts = modal_compute.load_modal_accounts()
    account, routing = modal_compute.select_modal_account(accounts)
    client = modal.Client.from_credentials(account.token_id, account.token_secret)
    app = modal.App.lookup(
        os.getenv("MODAL_APP_NAME", getattr(modal_compute, "MODAL_APP_NAME", "thrivarc-compute")),
        create_if_missing=True,
        environment_name=os.getenv("MODAL_ENVIRONMENT") or None,
        client=client,
    )
    image = (
        modal.Image.debian_slim(python_version="3.12")
        .pip_install(
            "jupyterlab",
            "pandas",
            "numpy",
            "scipy",
            "statsmodels",
            "matplotlib",
            "linearmodels",
            "arch",
            "ipykernel",
            "nbformat",
        )
    )
    access_token = uuid.uuid4().hex
    payload_url = _bootstrap_payload_url(session_id, notebook_text, seed_files)
    sandbox = modal.Sandbox.create(
        "bash",
        "-lc",
        _workspace_seed_script(payload_url, access_token),
        image=image,
        app=app,
        timeout=int(os.getenv("THRIVARC_NOTEBOOK_TIMEOUT_SECONDS", "14400")),
        idle_timeout=int(os.getenv("THRIVARC_NOTEBOOK_IDLE_TIMEOUT_SECONDS", "3600")),
        encrypted_ports=[8888],
        readiness_probe=modal.sandbox.Probe.with_tcp(8888),
        client=client,
    )
    sandbox.wait_until_ready(timeout=int(os.getenv("THRIVARC_NOTEBOOK_STARTUP_TIMEOUT_SECONDS", "300")))
    tunnel = sandbox.tunnels(timeout=60).get(8888)
    access_url = f"{tunnel.url}/lab/tree/analysis.ipynb?token={access_token}" if tunnel else ""
    return {
        "status": "running",
        "backend": "modal",
        "modal_account_alias": account.alias,
        "sandbox_id": sandbox.object_id,
        "access_url": access_url,
        "can_embed": bool(access_url),
        "sync_status": "not_synced",
        "routing": routing,
    }


def sync_workspace_artifacts(session_id: str, workspace: dict[str, Any]) -> dict[str, Any]:
    if _is_test_mode():
        synced = [
            f"sessions/{session_id}/06_compute/notebook/analysis.ipynb",
            f"sessions/{session_id}/06_compute/notebook/analysis.py",
        ]
        return {"synced_paths": synced, "status": "synced"}

    import modal

    from api import modal_compute

    alias = str(workspace.get("modal_account_alias") or "primary")
    account = next((item for item in modal_compute.load_modal_accounts() if item.alias == alias), None)
    if account is None:
        raise RuntimeError(f"Notebook workspace account alias {alias} is not configured.")
    client = modal.Client.from_credentials(account.token_id, account.token_secret)
    sandbox = modal.Sandbox.from_id(str(workspace.get("sandbox_id")), client=client)
    sandbox.hydrate()

    synced_paths: list[str] = []
    try:
        entries = sandbox.ls("/workspace")
    except Exception:
        entries = []

    for entry in entries:
        name = os.path.basename(str(entry))
        if not name or name.startswith("."):
            continue
        suffix = Path(name).suffix.lower()
        if suffix not in {".ipynb", ".py", ".csv", ".png", ".pdf", ".txt", ".json"}:
            continue
        remote_path = entry if str(entry).startswith("/") else f"/workspace/{name}"
        mode = "rb" if suffix in {".png", ".pdf"} else "r"
        with sandbox.open(remote_path, mode) as handle:
            content = handle.read()
        if isinstance(content, str):
            raw = content.encode("utf-8")
        else:
            raw = bytes(content)
        artifact_path = f"06_compute/notebook/{name}" if suffix in {".ipynb", ".py"} else f"06_compute/notebook/artifacts/{name}"
        artifact = write_artifact(session_id, artifact_path, raw)
        synced_paths.append(artifact.get("blob_path") or f"sessions/{session_id}/{artifact_path}")
    return {"synced_paths": synced_paths, "status": "synced" if synced_paths else "idle"}
