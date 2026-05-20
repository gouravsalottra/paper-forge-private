from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

CONTAINER_NAME = "research-artifacts"
MOCK_ACCOUNT_URL = "https://mock.blob.local"

_MOCK_BLOBS: dict[str, bytes] = {}
logger = logging.getLogger(__name__)

# Local fallback root — used in development when Azure is unavailable
_LOCAL_STORE = Path(os.getenv("LOCAL_ARTIFACT_DIR") or str(Path.cwd() / "artifact_store")).resolve()


class BlobStorageUnavailableError(RuntimeError):
    """Structured storage failure that can be rendered by the API/UI."""

    def __init__(self, message: str = "Artifact storage is unavailable.") -> None:
        super().__init__(message)
        self.error_code = "BLOB_UNAVAILABLE"
        self.system_state = "blob_unavailable"
        self.available_actions = ["retry", "check_storage_configuration"]


def reset_mock_storage() -> None:
    """Clear the in-memory blob store used by tests."""
    _MOCK_BLOBS.clear()


def _environment() -> str:
    return os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "development")).lower()


def _is_production() -> bool:
    return _environment() == "production"


def _is_mock_backend() -> bool:
    return _environment() == "test" or os.getenv("THRIVARC_STORAGE_BACKEND", "").lower() == "mock"


def _json_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return str(value).encode("utf-8")


def _normalize_path(session_id: str, path: str, version: int | None = None) -> str:
    clean_session = str(session_id).strip().strip("/")
    clean_path = str(path).strip().strip("/")
    if not clean_session:
        raise BlobStorageUnavailableError("Session id is required for artifact storage.")
    if not clean_path:
        raise BlobStorageUnavailableError("Artifact path is required for artifact storage.")
    if clean_path.startswith(f"sessions/{clean_session}/"):
        return clean_path
    parts = clean_path.split("/", 1)
    if version is not None and len(parts) == 2 and not parts[1].startswith("v"):
        clean_path = f"{parts[0]}/v{int(version)}/{parts[1]}"
    return f"sessions/{clean_session}/{clean_path}"


# ── Local filesystem fallback ─────────────────────────────────────────────────

def _local_write(blob_path: str, data: bytes) -> None:
    dest = _LOCAL_STORE / blob_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def _local_read(blob_path: str) -> bytes:
    src = _LOCAL_STORE / blob_path
    if not src.exists():
        raise BlobStorageUnavailableError(f"Artifact not found in local store: {blob_path}")
    return src.read_bytes()


def _local_list(prefix: str) -> list[str]:
    base = _LOCAL_STORE / prefix
    if not base.exists():
        return []
    return [str(p.relative_to(_LOCAL_STORE)).replace("\\", "/") for p in base.rglob("*") if p.is_file()]


def _local_delete_prefix(prefix: str) -> None:
    base = _LOCAL_STORE / prefix
    if base.is_file():
        base.unlink(missing_ok=True)
        return
    if not base.exists():
        return
    for path in sorted(base.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass
    try:
        base.rmdir()
    except OSError:
        pass


# ── Azure helpers ─────────────────────────────────────────────────────────────

def _get_blob_service_client():
    try:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient
    except Exception as exc:  # pragma: no cover
        raise BlobStorageUnavailableError("Azure Blob SDK is unavailable.") from exc

    account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
    account_name = os.getenv("AZURE_STORAGE_ACCOUNT", "paperforgeartifacts")
    if not account_url:
        account_url = f"https://{account_name}.blob.core.windows.net"
    try:
        return BlobServiceClient(account_url=account_url, credential=DefaultAzureCredential())
    except Exception as exc:  # pragma: no cover
        raise BlobStorageUnavailableError("Azure Blob client could not be created.") from exc


def _upload_bytes(blob_path: str, data: bytes) -> str:
    """Upload bytes to storage. Returns backend name used ('mock'|'azure_blob'|'local')."""
    if _is_mock_backend():
        _MOCK_BLOBS[blob_path] = data
        return "mock"

    # Try Azure first
    if not _is_production():
        # In development, attempt Azure but fall back to local on any error
        try:
            client = _get_blob_service_client()
            client.get_blob_client(container=CONTAINER_NAME, blob=blob_path).upload_blob(data, overwrite=True)
            return "azure_blob"
        except Exception as exc:
            logger.warning(
                "Azure blob upload failed (%s: %s) — falling back to local filesystem storage at %s",
                type(exc).__name__, exc, _LOCAL_STORE,
            )
            _local_write(blob_path, data)
            return "local"
    else:
        # Production: Azure is mandatory — hard fail
        client = _get_blob_service_client()
        try:
            client.get_blob_client(container=CONTAINER_NAME, blob=blob_path).upload_blob(data, overwrite=True)
            return "azure_blob"
        except Exception as exc:
            raise BlobStorageUnavailableError() from exc


def _download_bytes(blob_path: str) -> bytes:
    if _is_mock_backend():
        try:
            return _MOCK_BLOBS[blob_path]
        except KeyError as exc:
            raise BlobStorageUnavailableError("Artifact was not found in storage.") from exc

    # Try Azure first, then local fallback in dev
    if not _is_production():
        try:
            client = _get_blob_service_client()
            return client.get_blob_client(container=CONTAINER_NAME, blob=blob_path).download_blob().readall()
        except Exception:
            pass
        try:
            return _local_read(blob_path)
        except BlobStorageUnavailableError:
            raise
        except Exception as exc:
            raise BlobStorageUnavailableError("Artifact could not be read.") from exc
    else:
        client = _get_blob_service_client()
        try:
            return client.get_blob_client(container=CONTAINER_NAME, blob=blob_path).download_blob().readall()
        except Exception as exc:
            raise BlobStorageUnavailableError("Artifact could not be read from storage.") from exc


# ── Public API ────────────────────────────────────────────────────────────────

def download_blob(blob_path: str) -> bytes:
    """Download a blob by its absolute Blob Storage path."""
    clean_path = str(blob_path).strip().strip("/")
    if not clean_path:
        raise BlobStorageUnavailableError("Blob path is required.")
    return _download_bytes(clean_path)


def list_blobs(prefix: str) -> list[str]:
    """List absolute blob paths under a prefix."""
    clean_prefix = str(prefix).strip().strip("/")
    if _is_mock_backend():
        return sorted(path for path in _MOCK_BLOBS if path.startswith(clean_prefix))
    if not _is_production():
        try:
            client = _get_blob_service_client()
            container = client.get_container_client(CONTAINER_NAME)
            return [item.name for item in container.list_blobs(name_starts_with=clean_prefix)]
        except Exception:
            return _local_list(clean_prefix)
    client = _get_blob_service_client()
    try:
        container = client.get_container_client(CONTAINER_NAME)
        return [item.name for item in container.list_blobs(name_starts_with=clean_prefix)]
    except Exception as exc:
        raise BlobStorageUnavailableError("Blob list could not be read from storage.") from exc


def _delete_blob_path(blob_path: str) -> None:
    clean_path = str(blob_path).strip().strip("/")
    if not clean_path:
        return
    if _is_mock_backend():
        _MOCK_BLOBS.pop(clean_path, None)
        return
    if not _is_production():
        try:
            client = _get_blob_service_client()
            client.get_blob_client(container=CONTAINER_NAME, blob=clean_path).delete_blob(delete_snapshots="include")
            return
        except Exception:
            _local_delete_prefix(clean_path)
            return
    client = _get_blob_service_client()
    try:
        client.get_blob_client(container=CONTAINER_NAME, blob=clean_path).delete_blob(delete_snapshots="include")
    except Exception as exc:
        raise BlobStorageUnavailableError("Blob delete could not be completed.") from exc


def delete_session_artifacts(session_id: str) -> int:
    """Delete all artifacts under sessions/{session_id}/ and return the count removed."""
    prefix = f"sessions/{str(session_id).strip().strip('/')}/"
    blobs = list_blobs(prefix)
    for blob_path in blobs:
        _delete_blob_path(blob_path)
    if not _is_production():
        _local_delete_prefix(prefix)
    return len(blobs)


def write_artifact(session_id: str, path: str, content: Any, *, version: int | None = None) -> dict[str, Any]:
    """Write an artifact under sessions/{session_id}/ and return its storage reference."""
    blob_path = _normalize_path(session_id, path, version=version)
    data = _json_bytes(content)
    try:
        backend = _upload_bytes(blob_path, data)
    except BlobStorageUnavailableError:
        raise
    except Exception as exc:
        raise BlobStorageUnavailableError() from exc
    return {
        "backend": backend,
        "container": CONTAINER_NAME,
        "blob_path": blob_path,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def read_artifact(session_id: str, path: str, *, version: int | None = None) -> bytes:
    """Read an artifact from storage as bytes."""
    blob_path = _normalize_path(session_id, path, version=version)
    try:
        return _download_bytes(blob_path)
    except BlobStorageUnavailableError:
        raise
    except Exception as exc:
        raise BlobStorageUnavailableError() from exc


def get_artifact_url(session_id: str, path: str, *, version: int | None = None, expires_in_seconds: int = 3600) -> str:
    """Return a one-hour signed URL for an artifact."""
    blob_path = _normalize_path(session_id, path, version=version)
    url = get_download_url(blob_path, expiry_hours=max(1, int(expires_in_seconds / 3600)))
    if not url:
        raise BlobStorageUnavailableError("Signed artifact URL could not be created.")
    return url


def get_download_url(blob_path: str, expiry_hours: int = 24) -> str | None:
    """Return a user-delegation SAS URL for a blob path, or None on failure."""
    clean_path = str(blob_path).strip().strip("/")
    if not clean_path:
        return None
    expiry_hours = max(1, int(expiry_hours or 24))
    expires = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)
    encoded = quote(clean_path)
    if _is_mock_backend():
        return f"{MOCK_ACCOUNT_URL}/{CONTAINER_NAME}/{encoded}?{urlencode({'se': expires.isoformat(), 'sig': 'mock'})}"

    # In dev — return a local file:// URL so artifacts are accessible
    if not _is_production():
        local_path = _LOCAL_STORE / clean_path
        if local_path.exists():
            return local_path.as_uri()
        # Try Azure SAS as best effort
        try:
            from azure.storage.blob import BlobSasPermissions, generate_blob_sas
            account_name = os.getenv("AZURE_STORAGE_ACCOUNT", "paperforgeartifacts")
            client = _get_blob_service_client()
            user_delegation_key = client.get_user_delegation_key(datetime.now(timezone.utc), expires)
            sas = generate_blob_sas(
                account_name=account_name,
                container_name=CONTAINER_NAME,
                blob_name=clean_path,
                user_delegation_key=user_delegation_key,
                permission=BlobSasPermissions(read=True),
                expiry=expires,
            )
            return f"https://{account_name}.blob.core.windows.net/{CONTAINER_NAME}/{encoded}?{sas}"
        except Exception:
            return None

    try:
        from azure.storage.blob import BlobSasPermissions, generate_blob_sas
    except Exception:
        logger.warning("Azure Blob SAS SDK unavailable; falling back to streaming download endpoint.")
        return None

    account_name = os.getenv("AZURE_STORAGE_ACCOUNT", "paperforgeartifacts")
    try:
        client = _get_blob_service_client()
        user_delegation_key = client.get_user_delegation_key(datetime.now(timezone.utc), expires)
        sas = generate_blob_sas(
            account_name=account_name,
            container_name=CONTAINER_NAME,
            blob_name=clean_path,
            user_delegation_key=user_delegation_key,
            permission=BlobSasPermissions(read=True),
            expiry=expires,
        )
    except Exception:
        logger.warning("Could not create user-delegation SAS for blob path %s", clean_path)
        return None
    return f"https://{account_name}.blob.core.windows.net/{CONTAINER_NAME}/{encoded}?{sas}"


def list_artifacts(session_id: str) -> list[dict[str, Any]]:
    """Return artifact metadata and signed read URLs for a session."""
    prefix = f"sessions/{str(session_id).strip().strip('/')}/"
    if _is_mock_backend():
        artifacts: list[dict[str, Any]] = []
        for blob_path, data in sorted(_MOCK_BLOBS.items()):
            if not blob_path.startswith(prefix):
                continue
            relative = blob_path[len(prefix):]
            download_url = get_download_url(blob_path)
            artifacts.append({
                "name": relative.rsplit("/", 1)[-1],
                "path": blob_path,
                "url": download_url,
                "download_url": download_url,
                "size": len(data),
            })
        return artifacts

    if not _is_production():
        try:
            client = _get_blob_service_client()
            container = client.get_container_client(CONTAINER_NAME)
            return [
                {
                    "name": item.name.rsplit("/", 1)[-1],
                    "path": item.name,
                    "url": get_download_url(item.name),
                    "download_url": get_download_url(item.name),
                    "size": getattr(item, "size", 0),
                }
                for item in container.list_blobs(name_starts_with=prefix)
            ]
        except Exception:
            # Fall back to local filesystem listing
            paths = _local_list(prefix)
            return [
                {
                    "name": p.rsplit("/", 1)[-1],
                    "path": p,
                    "url": (_LOCAL_STORE / p).as_uri(),
                    "download_url": (_LOCAL_STORE / p).as_uri(),
                    "size": (_LOCAL_STORE / p).stat().st_size if (_LOCAL_STORE / p).exists() else 0,
                }
                for p in paths
            ]

    client = _get_blob_service_client()
    try:
        container = client.get_container_client(CONTAINER_NAME)
        return [
            {
                "name": item.name.rsplit("/", 1)[-1],
                "path": item.name,
                "url": download_url,
                "download_url": download_url,
                "size": getattr(item, "size", 0),
            }
            for item in container.list_blobs(name_starts_with=prefix)
            for download_url in [get_download_url(item.name)]
        ]
    except Exception as exc:
        raise BlobStorageUnavailableError("Artifact list could not be read from storage.") from exc
