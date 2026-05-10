from __future__ import annotations

from pathlib import Path

import pandas as pd

from .registry import make_certificate, register


@register
class WRDSFuturesConnector:
    source_name = "wrds_futures"

    def fetch(self, dataset: str, fields: list[str], date_range: tuple[str, str], filters: list[str], output_dir: Path):
        # Wrapper placeholder to keep API stable while preserving existing miner WRDS pipeline.
        df = pd.DataFrame()
        cert = make_certificate(df, self.source_name, dataset, date_range, fields, filters)
        return df, cert
