from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class DataConnector(Protocol):
    source_name: str

    def fetch(
        self,
        dataset: str,
        fields: list[str],
        date_range: tuple[str, str],
        filters: list[str],
        output_dir: Path,
    ) -> tuple[pd.DataFrame, dict]:
        ...


CONNECTOR_REGISTRY: dict[str, type] = {}


def register(cls):
    CONNECTOR_REGISTRY[cls.source_name] = cls
    return cls


def get_connector(source_name: str) -> DataConnector:
    _bootstrap_registry()
    if source_name not in CONNECTOR_REGISTRY:
        raise ValueError(
            f"Unknown data source: '{source_name}'\n"
            f"Available: {sorted(CONNECTOR_REGISTRY.keys())}\n"
            f"To add a new source: create agents/miner/connectors/<name>.py and decorate the class with @register"
        )
    return CONNECTOR_REGISTRY[source_name]()


def make_certificate(df: pd.DataFrame, source: str, dataset: str, date_range: tuple[str, str], fields: list[str], filters: list[str]) -> dict:
    payload = df.to_csv(index=False).encode("utf-8")
    return {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "row_count": int(len(df)),
        "download_timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "dataset": dataset,
        "date_range": list(date_range),
        "fields": fields,
        "filters": filters,
        "acknowledged_deviations": {},
    }


def _bootstrap_registry() -> None:
    if CONNECTOR_REGISTRY:
        return
    from . import (  # noqa: F401
        yfinance_connector,
        wrds_futures_connector,
        wrds_crsp_connector,
        fred_connector,
        sec_edgar_connector,
        upload_connector,
    )


_bootstrap_registry()
