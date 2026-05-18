from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

try:  # Modal is an optional runtime dependency for local test environments.
    import modal
except Exception:  # pragma: no cover - exercised only when modal is absent.
    modal = None  # type: ignore[assignment]


MODAL_APP_NAME = os.getenv("MODAL_APP_NAME", "thrivarc-compute")
MODAL_FUNCTION_NAME = os.getenv("MODAL_FUNCTION_NAME", "run_analysis_code")
DEFAULT_TIMEOUT_SECONDS = int(os.getenv("MODAL_EXECUTION_TIMEOUT_SECONDS", "900"))
MAX_RETURN_FILE_BYTES = int(os.getenv("MODAL_MAX_RETURN_FILE_BYTES", str(25 * 1024 * 1024)))
DEFAULT_MONTHLY_BUDGET_USD = float(os.getenv("MODAL_MONTHLY_BUDGET_USD", "28"))
DEFAULT_ESTIMATED_USD_PER_SECOND = float(os.getenv("MODAL_ESTIMATED_USD_PER_SECOND", "0.00015"))
ROUTER_FAILURE_THRESHOLD = int(os.getenv("MODAL_ROUTER_FAILURE_THRESHOLD", "3"))

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModalAccount:
    alias: str
    token_id: str
    token_secret: str
    enabled: bool = True
    monthly_budget_usd: float = DEFAULT_MONTHLY_BUDGET_USD

if modal is not None:
    app = modal.App(MODAL_APP_NAME)
    image = (
        modal.Image.debian_slim(python_version="3.12")
        .pip_install(
            "pandas==2.2.3",
            "numpy==2.1.3",
            "scipy==1.15.3",
            "statsmodels==0.14.4",
            "linearmodels==7.0",
            "arch==8.0.0",
            "matplotlib==3.10.0",
            "yfinance==0.2.66",
            "seaborn==0.13.2",
        )
    )
else:  # pragma: no cover
    app = None
    image = None


def _extract_json_from_text(text: str) -> dict[str, Any] | None:
    text = str(text or "").strip()
    if not text:
        return None
    for line in reversed([ln.strip() for ln in text.splitlines() if ln.strip()]):
        try:
            parsed = json.loads(line)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            continue
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _minimal_subprocess_env(extra: dict[str, str]) -> dict[str, str]:
    allowed = {
        "PATH",
        "PYTHONPATH",
        "PYTHONUNBUFFERED",
        "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE",
        "MPLCONFIGDIR",
    }
    env = {key: value for key, value in os.environ.items() if key in allowed and value}
    env["PYTHONUNBUFFERED"] = "1"
    env.update(extra)
    return env


def _collect_files(directory: str, *, kind: str, suffixes: set[str]) -> list[dict[str, Any]]:
    from pathlib import Path

    files: list[dict[str, Any]] = []
    root = Path(directory)
    if not root.exists():
        return files
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        data = path.read_bytes()
        if len(data) > MAX_RETURN_FILE_BYTES:
            files.append(
                {
                    "kind": kind,
                    "filename": path.name,
                    "relative_path": str(path.relative_to(root)),
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "skipped": True,
                    "reason": "file exceeded Modal return size limit",
                }
            )
            continue
        files.append(
            {
                "kind": kind,
                "filename": path.name,
                "relative_path": str(path.relative_to(root)),
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "content_b64": base64.b64encode(data).decode("ascii"),
            }
        )
    return files


if modal is not None:

    @app.function(image=image, timeout=DEFAULT_TIMEOUT_SECONDS, name=MODAL_FUNCTION_NAME)
    def run_analysis_code(payload: dict[str, Any]) -> dict[str, Any]:
        """Execute one generated-code attempt inside Modal and return files to the API."""
        import importlib.metadata
        import platform
        import subprocess
        import sys
        import tempfile
        import time
        from pathlib import Path

        started = time.time()
        session_id = str(payload.get("session_id") or "modal-compute")
        code = str(payload.get("code") or "")
        timeout_seconds = int(payload.get("timeout_seconds") or 120)
        blueprint_json = str(payload.get("blueprint_json") or "{}")

        with tempfile.TemporaryDirectory(prefix="thrivarc-modal-") as tmpdir:
            root = Path(tmpdir)
            data_path = root / "analysis_input.csv"
            event_path = root / "events.csv"
            figures_dir = root / "figures"
            results_dir = root / "results"
            logs_dir = root / "logs"
            figures_dir.mkdir(parents=True, exist_ok=True)
            results_dir.mkdir(parents=True, exist_ok=True)
            logs_dir.mkdir(parents=True, exist_ok=True)

            data_path.write_bytes(base64.b64decode(payload.get("data_csv_b64") or ""))
            event_b64 = payload.get("event_csv_b64") or ""
            if event_b64:
                event_path.write_bytes(base64.b64decode(event_b64))
                event_env = str(event_path)
            else:
                event_env = ""

            code_path = root / "analysis.py"
            code_path.write_text(code, encoding="utf-8")
            env = _minimal_subprocess_env(
                {
                    "DATA_CSV_PATH": str(data_path),
                    "EVENT_CSV_PATH": event_env,
                    "FIGURES_DIR": str(figures_dir),
                    "RESULTS_DIR": str(results_dir),
                    "BLUEPRINT_JSON": blueprint_json,
                    "MPLCONFIGDIR": str(root / "mplconfig"),
                }
            )

            try:
                completed = subprocess.run(
                    [sys.executable, str(code_path)],
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    env=env,
                    cwd=str(root),
                )
                timed_out = False
            except subprocess.TimeoutExpired as exc:
                completed = None
                timed_out = True
                stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
                stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
            else:
                stdout = completed.stdout or ""
                stderr = completed.stderr or ""

            (logs_dir / "stdout.txt").write_text(stdout, encoding="utf-8", errors="replace")
            (logs_dir / "stderr.txt").write_text(stderr, encoding="utf-8", errors="replace")
            (logs_dir / "analysis_code.py").write_text(code, encoding="utf-8", errors="replace")

            package_names = ["pandas", "numpy", "scipy", "statsmodels", "linearmodels", "arch", "matplotlib", "yfinance"]
            packages: dict[str, str] = {}
            for name in package_names:
                try:
                    packages[name] = importlib.metadata.version(name)
                except Exception:
                    packages[name] = "not installed"

            files = []
            files.extend(_collect_files(str(results_dir), kind="result_csv", suffixes={".csv"}))
            files.extend(_collect_files(str(figures_dir), kind="figure", suffixes={".png", ".pdf"}))
            files.extend(_collect_files(str(logs_dir), kind="log", suffixes={".txt", ".py"}))

            returncode = 124 if timed_out else int(completed.returncode if completed is not None else 1)
            parsed = _extract_json_from_text(stdout)
            runtime_seconds = round(time.time() - started, 3)
            return {
                "success": returncode == 0,
                "backend": "modal",
                "session_id": session_id,
                "returncode": returncode,
                "timed_out": timed_out,
                "stdout": stdout[-12000:],
                "stderr": stderr[-12000:],
                "parsed": parsed,
                "files": files,
                "runtime_seconds": runtime_seconds,
                "environment": {
                    "python": sys.version,
                    "platform": platform.platform(),
                    "packages": packages,
                },
            }


def _modal_function(account: ModalAccount | None = None):
    if modal is None:
        raise RuntimeError("Modal SDK is not installed; cannot use Modal compute backend.")
    if os.getenv("MODAL_USE_DEPLOYED", "1").strip().lower() in {"1", "true", "yes"}:
        app_name = os.getenv("MODAL_APP_NAME", MODAL_APP_NAME)
        function_name = os.getenv("MODAL_FUNCTION_NAME", MODAL_FUNCTION_NAME)
        environment_name = os.getenv("MODAL_ENVIRONMENT") or None
        client = modal.Client.from_credentials(account.token_id, account.token_secret) if account else None
        return modal.Function.from_name(app_name, function_name, environment_name=environment_name, client=client)
    # This mode is useful only when the module is running under Modal's own app
    # runner. A normal API container should use the deployed lookup above.
    return run_analysis_code


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _usage_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _account_env_name(alias: str, suffix: str) -> str:
    clean = "".join(ch if ch.isalnum() else "_" for ch in alias.upper())
    return f"MODAL_{clean}_{suffix}"


def load_modal_accounts() -> list[ModalAccount]:
    aliases = [item.strip() for item in os.getenv("MODAL_ACCOUNT_ALIASES", os.getenv("MODAL_ACCOUNT_ALIAS", "primary")).split(",") if item.strip()]
    accounts: list[ModalAccount] = []
    for alias in aliases:
        token_id = os.getenv(_account_env_name(alias, "TOKEN_ID"))
        token_secret = os.getenv(_account_env_name(alias, "TOKEN_SECRET"))
        if alias == "primary":
            token_id = token_id or os.getenv("MODAL_TOKEN_ID")
            token_secret = token_secret or os.getenv("MODAL_TOKEN_SECRET")
        enabled = os.getenv(_account_env_name(alias, "ENABLED"), "1").strip().lower() not in {"0", "false", "no"}
        budget = float(os.getenv(_account_env_name(alias, "MONTHLY_BUDGET_USD"), os.getenv("MODAL_MONTHLY_BUDGET_USD", str(DEFAULT_MONTHLY_BUDGET_USD))))
        if token_id and token_secret:
            accounts.append(ModalAccount(alias=alias, token_id=token_id, token_secret=token_secret, enabled=enabled, monthly_budget_usd=budget))
    return accounts


def _connect_db():
    from db.connection import get_db_connection

    return get_db_connection()


def _is_sqlite(conn: Any) -> bool:
    return isinstance(conn, sqlite3.Connection)


def _sql(conn: Any, statement: str) -> str:
    return statement if _is_sqlite(conn) else statement.replace("?", "%s")


def _execute(conn: Any, statement: str, params: tuple[Any, ...] = ()):
    if _is_sqlite(conn):
        return conn.execute(statement, params)
    cur = conn.cursor()
    cur.execute(_sql(conn, statement), params)
    return cur


def _ensure_router_schema(conn: Any) -> None:
    if _is_sqlite(conn):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS modal_account_usage (
              alias TEXT NOT NULL,
              usage_month TEXT NOT NULL,
              estimated_spend_usd REAL DEFAULT 0,
              monthly_budget_usd REAL DEFAULT 28,
              status TEXT DEFAULT 'healthy',
              failure_count INTEGER DEFAULT 0,
              last_failure_at TEXT,
              last_routed_at TEXT,
              updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (alias, usage_month)
            )
            """
        )
        conn.commit()
        return
    _execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS modal_account_usage (
          alias TEXT NOT NULL,
          usage_month TEXT NOT NULL,
          estimated_spend_usd DOUBLE PRECISION DEFAULT 0,
          monthly_budget_usd DOUBLE PRECISION DEFAULT 28,
          status TEXT DEFAULT 'healthy',
          failure_count INTEGER DEFAULT 0,
          last_failure_at TIMESTAMPTZ,
          last_routed_at TIMESTAMPTZ,
          updated_at TIMESTAMPTZ DEFAULT NOW(),
          PRIMARY KEY (alias, usage_month)
        )
        """,
    )
    conn.commit()


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default


def _usage_row(conn: Any, account: ModalAccount) -> dict[str, Any]:
    month = _usage_month()
    _execute(
        conn,
        "INSERT INTO modal_account_usage (alias, usage_month, estimated_spend_usd, monthly_budget_usd, status, failure_count, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (alias, usage_month) DO NOTHING",
        (account.alias, month, 0.0, account.monthly_budget_usd, "healthy", 0, _now_iso()),
    )
    if _is_sqlite(conn):
        conn.commit()
    else:
        conn.commit()
    row = _execute(conn, "SELECT * FROM modal_account_usage WHERE alias=? AND usage_month=?", (account.alias, month)).fetchone()
    return {
        "alias": _row_get(row, "alias", account.alias),
        "usage_month": _row_get(row, "usage_month", month),
        "estimated_spend_usd": float(_row_get(row, "estimated_spend_usd", 0) or 0),
        "monthly_budget_usd": float(_row_get(row, "monthly_budget_usd", account.monthly_budget_usd) or account.monthly_budget_usd),
        "status": _row_get(row, "status", "healthy"),
        "failure_count": int(_row_get(row, "failure_count", 0) or 0),
    }


def _eligible_accounts(conn: Any, accounts: list[ModalAccount], exclude_aliases: set[str] | None = None) -> list[tuple[ModalAccount, dict[str, Any]]]:
    exclude_aliases = exclude_aliases or set()
    eligible: list[tuple[ModalAccount, dict[str, Any]]] = []
    for account in accounts:
        if account.alias in exclude_aliases:
            continue
        row = _usage_row(conn, account)
        if not account.enabled:
            continue
        if row["estimated_spend_usd"] >= row["monthly_budget_usd"]:
            _execute(conn, "UPDATE modal_account_usage SET status=?, updated_at=? WHERE alias=? AND usage_month=?", ("blocked_over_budget", _now_iso(), account.alias, row["usage_month"]))
            conn.commit()
            continue
        if row["status"] == "unhealthy" and row["failure_count"] >= ROUTER_FAILURE_THRESHOLD:
            continue
        eligible.append((account, row))
    return sorted(eligible, key=lambda item: (item[1]["estimated_spend_usd"], item[1]["failure_count"], item[0].alias))


def select_modal_account(accounts: list[ModalAccount] | None = None, exclude_aliases: set[str] | None = None) -> tuple[ModalAccount, dict[str, Any]]:
    accounts = accounts if accounts is not None else load_modal_accounts()
    if not accounts:
        raise RuntimeError("No Modal accounts are configured. Set MODAL_ACCOUNT_ALIASES and per-account Modal token secrets.")
    with _connect_db() as conn:
        _ensure_router_schema(conn)
        eligible = _eligible_accounts(conn, accounts, exclude_aliases)
        if not eligible:
            raise RuntimeError("No Modal accounts are eligible: all are disabled, unhealthy, or over budget.")
        account, row = eligible[0]
        _execute(
            conn,
            "UPDATE modal_account_usage SET status=?, last_routed_at=?, updated_at=? WHERE alias=? AND usage_month=?",
            ("healthy", _now_iso(), _now_iso(), account.alias, row["usage_month"]),
        )
        conn.commit()
        routing = {
            "selected_alias": account.alias,
            "routing_reason": "least_spend_healthy_under_budget",
            "usage_month": row["usage_month"],
            "estimated_spend_usd": row["estimated_spend_usd"],
            "monthly_budget_usd": row["monthly_budget_usd"],
            "eligible_aliases": [candidate.alias for candidate, _ in eligible],
        }
        return account, routing


def record_modal_success(alias: str, runtime_seconds: float | int | None, returned_file_count: int = 0) -> dict[str, Any]:
    estimated_cost = max(0.0, float(runtime_seconds or 0.0)) * float(os.getenv("MODAL_ESTIMATED_USD_PER_SECOND", str(DEFAULT_ESTIMATED_USD_PER_SECOND)))
    month = _usage_month()
    with _connect_db() as conn:
        _ensure_router_schema(conn)
        _execute(
            conn,
            "INSERT INTO modal_account_usage (alias, usage_month, estimated_spend_usd, monthly_budget_usd, status, failure_count, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (alias, usage_month) DO NOTHING",
            (alias, month, 0.0, DEFAULT_MONTHLY_BUDGET_USD, "healthy", 0, _now_iso()),
        )
        _execute(
            conn,
            "UPDATE modal_account_usage SET estimated_spend_usd=estimated_spend_usd+?, status=?, updated_at=? WHERE alias=? AND usage_month=?",
            (estimated_cost, "healthy", _now_iso(), alias, month),
        )
        conn.commit()
    return {"estimated_cost_usd": estimated_cost, "returned_file_count": returned_file_count}


def record_modal_platform_failure(alias: str, error: str) -> None:
    month = _usage_month()
    with _connect_db() as conn:
        _ensure_router_schema(conn)
        _execute(
            conn,
            "INSERT INTO modal_account_usage (alias, usage_month, estimated_spend_usd, monthly_budget_usd, status, failure_count, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (alias, usage_month) DO NOTHING",
            (alias, month, 0.0, DEFAULT_MONTHLY_BUDGET_USD, "healthy", 0, _now_iso()),
        )
        _execute(
            conn,
            "UPDATE modal_account_usage SET failure_count=failure_count+1, status=CASE WHEN failure_count + 1 >= ? THEN 'unhealthy' ELSE status END, last_failure_at=?, updated_at=? WHERE alias=? AND usage_month=?",
            (ROUTER_FAILURE_THRESHOLD, _now_iso(), _now_iso(), alias, month),
        )
        conn.commit()
    logger.warning("Modal account %s platform failure: %s", alias, error[-500:])


def execute_in_modal_account(payload: dict[str, Any], account: ModalAccount) -> dict[str, Any]:
    function = _modal_function(account)
    return function.remote(payload)


def execute_in_modal(payload: dict[str, Any]) -> dict[str, Any]:
    """Submit one generated-code attempt to Modal.

    The payload intentionally contains data/code only. Production DB, Blob, and
    OpenAI credentials stay in the API container and are not sent to Modal.
    """
    if os.getenv("MODAL_ROUTER_ENABLED", "0").strip().lower() not in {"1", "true", "yes"}:
        function = _modal_function()
        result = function.remote(payload)
        result["modal_account_alias"] = os.getenv("MODAL_ACCOUNT_ALIAS", "primary")
        result["routing"] = {"selected_alias": result["modal_account_alias"], "routing_reason": "router_disabled"}
        return result

    accounts = load_modal_accounts()
    tried: list[str] = []
    last_error = ""
    for _ in range(max(1, len(accounts))):
        account, routing = select_modal_account(accounts, set(tried))
        tried.append(account.alias)
        try:
            result = execute_in_modal_account(payload, account)
            runtime = result.get("runtime_seconds")
            spend = record_modal_success(account.alias, runtime, len(result.get("files") or []))
            result["modal_account_alias"] = account.alias
            result["routing"] = {**routing, "tried_aliases": tried, **spend}
            return result
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            record_modal_platform_failure(account.alias, last_error)
            continue
    raise RuntimeError(f"All eligible Modal accounts failed. Tried={tried}. Last error={last_error}")
