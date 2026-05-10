from __future__ import annotations

from pathlib import Path

import pandas as pd

from .registry import make_certificate, register


@register
class SecEdgarConnector:
    source_name = "sec_edgar"

    def fetch(self, dataset: str, fields: list[str], date_range: tuple[str, str], filters: list[str], output_dir: Path):
        df = pd.DataFrame()
        cert = make_certificate(df, self.source_name, dataset, date_range, fields, filters)
        return df, cert
