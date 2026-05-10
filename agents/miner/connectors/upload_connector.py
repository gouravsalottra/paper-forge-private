from __future__ import annotations

from pathlib import Path

import pandas as pd

from .registry import make_certificate, register


@register
class UploadConnector:
    source_name = "upload"

    def fetch(self, dataset: str, fields: list[str], date_range: tuple[str, str], filters: list[str], output_dir: Path):
        uploads_candidates = [
            output_dir / "data" / "uploads",
            Path("data") / "uploads",
        ]
        csv_path = None
        pq_path = None
        for uploads in uploads_candidates:
            c = uploads / f"{dataset}.csv"
            q = uploads / f"{dataset}.parquet"
            if c.exists() or q.exists():
                csv_path, pq_path = c, q
                break
        if csv_path is None or pq_path is None:
            uploads = uploads_candidates[0]
            csv_path = uploads / f"{dataset}.csv"
            pq_path = uploads / f"{dataset}.parquet"
        if csv_path.exists():
            df = pd.read_csv(csv_path)
        elif pq_path.exists():
            df = pd.read_parquet(pq_path)
        else:
            raise FileNotFoundError(f"Upload dataset not found: {csv_path} or {pq_path}")
        cert = make_certificate(df, self.source_name, dataset, date_range, fields, filters)
        return df, cert
