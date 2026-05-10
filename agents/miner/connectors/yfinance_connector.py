from __future__ import annotations

from pathlib import Path

from .registry import make_certificate, register


@register
class YFinanceConnector:
    source_name = "yfinance"

    def fetch(self, dataset: str, fields: list[str], date_range: tuple[str, str], filters: list[str], output_dir: Path):
        import agents.miner.miner as miner

        df = miner.build_returns_frame().reset_index()
        cert = make_certificate(df, self.source_name, dataset, date_range, fields, filters)
        return df, cert
