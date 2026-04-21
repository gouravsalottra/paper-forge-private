"""FORGE analyst pipeline: correlation regimes and DCC diagnostics."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import ruptures as rpt
from arch import arch_model
from scipy.optimize import minimize

INPUT_PATH = Path("outputs/commodity_returns.csv")
OUTPUT_DIR = Path("outputs")
ROLLING_PATH = OUTPUT_DIR / "rolling_correlations.csv"
REGIMES_PATH = OUTPUT_DIR / "correlation_regimes.csv"
DCC_PATH = OUTPUT_DIR / "dcc_correlations.csv"
SUMMARY_PATH = OUTPUT_DIR / "analyst_summary.csv"
PASSPORT_PATH = OUTPUT_DIR / "analyst_passport.json"

ROLLING_WINDOW = 252
MIN_BREAK_SIZE = 63


@dataclass
class DCCResult:
    a: float
    b: float
    correlations: np.ndarray


def load_returns(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    return df.dropna(how="any")


def compute_rolling_pairwise_corr(returns: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for left, right in combinations(returns.columns, 2):
        corr = returns[left].rolling(window=ROLLING_WINDOW, min_periods=ROLLING_WINDOW).corr(returns[right])
        pair_name = f"{left}__{right}"
        frame = pd.DataFrame(
            {
                "date": corr.index,
                "pair": pair_name,
                "correlation": corr.values,
            }
        ).dropna(subset=["correlation"])
        frames.append(frame)

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["date", "pair", "correlation"])
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    return out


def detect_breaks(rolling_corr: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for pair, grp in rolling_corr.groupby("pair", sort=True):
        s = grp.sort_values("date")
        y = s["correlation"].to_numpy(dtype=np.float64).reshape(-1, 1)
        if y.shape[0] < (MIN_BREAK_SIZE * 2):
            continue

        model = rpt.Pelt(model="rbf", min_size=MIN_BREAK_SIZE).fit(y)
        pen = np.log(max(len(y), 2)) * np.var(y)
        breakpoints = model.predict(pen=float(max(pen, 1e-8)))

        for bp in breakpoints[:-1]:
            idx = int(bp - 1)
            if idx < 0 or idx >= len(s):
                continue
            rows.append(
                {
                    "pair": pair,
                    "break_date": s.iloc[idx]["date"],
                    "break_index": int(bp),
                }
            )

    out = pd.DataFrame(rows, columns=["pair", "break_date", "break_index"])
    if not out.empty:
        out["break_date"] = pd.to_datetime(out["break_date"]).dt.strftime("%Y-%m-%d")
    return out


def _dcc_loglik(params: np.ndarray, z: np.ndarray, qbar: np.ndarray) -> float:
    a, b = float(params[0]), float(params[1])
    if a < 0.0 or b < 0.0 or (a + b) >= 0.999:
        return 1e9

    t, _ = z.shape
    q_t = qbar.copy()
    ll = 0.0

    for i in range(t):
        if i > 0:
            z_prev = z[i - 1][:, None]
            q_t = (1.0 - a - b) * qbar + a * (z_prev @ z_prev.T) + b * q_t

        d = np.sqrt(np.clip(np.diag(q_t), 1e-12, None))
        d_inv = np.diag(1.0 / d)
        r_t = d_inv @ q_t @ d_inv

        # numerical stabilization
        r_t[0, 0] = 1.0
        r_t[1, 1] = 1.0
        det = np.linalg.det(r_t)
        if det <= 0 or not np.isfinite(det):
            return 1e9

        inv = np.linalg.inv(r_t)
        zi = z[i][:, None]
        quad = (zi.T @ inv @ zi).item()
        ll += 0.5 * (np.log(det) + float(quad))

    return float(ll)


def fit_dcc_pair(z_pair: np.ndarray) -> DCCResult:
    qbar = np.cov(z_pair.T)
    if qbar.shape != (2, 2):
        qbar = np.eye(2)

    qbar += np.eye(2) * 1e-10

    cons = ({"type": "ineq", "fun": lambda x: 0.999 - x[0] - x[1]},)
    bounds = [(1e-8, 0.95), (1e-8, 0.95)]

    res = minimize(
        _dcc_loglik,
        x0=np.array([0.03, 0.95]),
        args=(z_pair, qbar),
        method="SLSQP",
        bounds=bounds,
        constraints=cons,
        options={"maxiter": 500, "ftol": 1e-9},
    )

    if not res.success:
        a, b = 0.03, 0.95
    else:
        a, b = float(res.x[0]), float(res.x[1])

    t = z_pair.shape[0]
    q_t = qbar.copy()
    rho = np.zeros(t, dtype=np.float64)

    for i in range(t):
        if i > 0:
            zp = z_pair[i - 1][:, None]
            q_t = (1.0 - a - b) * qbar + a * (zp @ zp.T) + b * q_t

        denom = np.sqrt(max(q_t[0, 0], 1e-12) * max(q_t[1, 1], 1e-12))
        rho[i] = float(np.clip(q_t[0, 1] / denom, -1.0, 1.0))

    return DCCResult(a=a, b=b, correlations=rho)


def compute_dcc_correlations(returns: pd.DataFrame) -> pd.DataFrame:
    # Univariate GARCH(1,1) standardized residuals
    std_resids: dict[str, pd.Series] = {}
    for col in returns.columns:
        # Scale returns for numerically stable GARCH estimation.
        series = (returns[col].dropna() * 100.0)
        model = arch_model(series, mean="Zero", vol="GARCH", p=1, q=1, dist="normal")
        fit = model.fit(disp="off")
        sr = fit.std_resid.dropna()
        std_resids[col] = sr

    z_df = pd.concat(std_resids, axis=1, join="inner").dropna()
    z_df.columns = returns.columns

    frames: list[pd.DataFrame] = []
    for left, right in combinations(z_df.columns, 2):
        z_pair = z_df[[left, right]].to_numpy(dtype=np.float64)
        dcc = fit_dcc_pair(z_pair)
        frame = pd.DataFrame(
            {
                "date": z_df.index.strftime("%Y-%m-%d"),
                "pair": f"{left}__{right}",
                "correlation": dcc.correlations,
            }
        )
        frames.append(frame)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["date", "pair", "correlation"])


def build_summary(rolling_corr: pd.DataFrame, regimes: pd.DataFrame, dcc_corr: pd.DataFrame) -> pd.DataFrame:
    rolling_stats = (
        rolling_corr.groupby("pair", as_index=False)["correlation"]
        .agg(mean_rolling_corr="mean", std_rolling_corr="std")
    )

    if regimes.empty:
        breaks = pd.DataFrame({"pair": rolling_stats["pair"], "regime_breaks": 0})
    else:
        breaks = regimes.groupby("pair", as_index=False).size().rename(columns={"size": "regime_breaks"})

    dcc_stats = dcc_corr.groupby("pair", as_index=False)["correlation"].mean().rename(columns={"correlation": "dcc_mean_corr"})

    out = rolling_stats.merge(breaks, on="pair", how="left").merge(dcc_stats, on="pair", how="left")
    out["regime_breaks"] = out["regime_breaks"].fillna(0).astype(int)
    out = out.sort_values("pair").reset_index(drop=True)
    return out


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_passport(file_map: dict[str, Path], row_counts: dict[str, int]) -> None:
    passport = {
        "files": {
            name: {
                "path": str(path),
                "sha256": sha256_file(path),
                "row_count": int(row_counts[name]),
            }
            for name, path in file_map.items()
        },
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    PASSPORT_PATH.write_text(json.dumps(passport, indent=2), encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    returns = load_returns(INPUT_PATH)

    rolling = compute_rolling_pairwise_corr(returns)
    rolling.to_csv(ROLLING_PATH, index=False)

    regimes = detect_breaks(rolling)
    regimes.to_csv(REGIMES_PATH, index=False)

    dcc = compute_dcc_correlations(returns)
    dcc.to_csv(DCC_PATH, index=False)

    summary = build_summary(rolling, regimes, dcc)
    summary.to_csv(SUMMARY_PATH, index=False)

    write_passport(
        file_map={
            "rolling_correlations": ROLLING_PATH,
            "correlation_regimes": REGIMES_PATH,
            "dcc_correlations": DCC_PATH,
            "analyst_summary": SUMMARY_PATH,
        },
        row_counts={
            "rolling_correlations": len(rolling),
            "correlation_regimes": len(regimes),
            "dcc_correlations": len(dcc),
            "analyst_summary": len(summary),
        },
    )

    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
