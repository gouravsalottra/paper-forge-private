from __future__ import annotations

import webbrowser
from pathlib import Path


def authenticate_wrds(env_path: Path = Path('.env')) -> str:
    webbrowser.open("https://wrds-www.wharton.upenn.edu")
    input("Complete login in browser/2FA, then press Enter...")
    username = input("WRDS username: ").strip()
    if not username:
        raise ValueError("WRDS username is required")

    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding='utf-8', errors='ignore').splitlines()
    replaced = False
    out = []
    for line in lines:
        if line.startswith("WRDS_USERNAME="):
            out.append(f"WRDS_USERNAME={username}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"WRDS_USERNAME={username}")
    env_path.write_text("\n".join(out).strip() + "\n", encoding='utf-8')
    return username
