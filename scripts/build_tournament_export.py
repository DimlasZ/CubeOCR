"""
build_tournament_export.py
--------------------------
Combines the newest data/final/*.csv with the newest matches file from
DimlasZ/TournamentOrganizer-NativeReact/results on GitHub, then packages both into a
.zip that mirrors the structure of the existing Draft csv data exports.

Output zip layout:
    data/zip/{date}_tournament_export.zip
        {date}_matches.csv          ← downloaded from GitHub as-is
        {date}_drafted_decks.csv    ← final CSV + "tournament" column added

Usage:
    python scripts/build_tournament_export.py
"""

import glob
import os
import zipfile
from io import StringIO

import pandas as pd
import requests

ROOT          = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIP_DIR       = os.path.join(ROOT, "data", "zip")
DATA_FINAL    = os.path.join(ROOT, "data", "final")

GITHUB_API    = "https://api.github.com/repos/DimlasZ/TournamentOrganizer-NativeReact/contents/results"


def fetch_newest_github_matches():
    """Return (filename, raw_csv_text) for the newest file in the GitHub results folder."""
    resp = requests.get(GITHUB_API, timeout=30)
    resp.raise_for_status()
    files = sorted(resp.json(), key=lambda f: f["name"], reverse=True)
    if not files:
        raise FileNotFoundError("No files found in GitHub results/ folder")
    newest = files[0]
    print(f"GitHub file: {newest['name']}")
    raw = requests.get(newest["download_url"], timeout=30)
    raw.raise_for_status()
    return newest["name"], raw.text


def find_newest_final_csv():
    """Return the path to the newest CSV in data/final/."""
    candidates = sorted(glob.glob(os.path.join(DATA_FINAL, "*.csv")), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No CSV files found in {DATA_FINAL}")
    path = candidates[0]
    print(f"Final CSV:   {os.path.basename(path)}")
    return path


def main():
    # ── 1. Download matches from GitHub ──────────────────────────────────────
    gh_filename, matches_text = fetch_newest_github_matches()
    df_matches = pd.read_csv(StringIO(matches_text))

    # ── 2. Extract tournament date and derive date prefix ────────────────────
    # matches filename is like "2026_01_25_matches.csv" → date prefix "2026_01_25"
    date_prefix = gh_filename.replace("_matches.csv", "")
    tournament_date = df_matches["tournamentDate"].iloc[0]
    print(f"Tournament date: {tournament_date}  (prefix: {date_prefix})")

    # ── 3. Load newest final CSV and add "tournament" column ─────────────────
    final_path = find_newest_final_csv()
    df_decks = pd.read_csv(final_path)
    df_decks["tournament"] = tournament_date

    # ── 4. Build zip ─────────────────────────────────────────────────────────
    zip_name    = f"{date_prefix}_tournament_export.zip"
    zip_path    = os.path.join(ZIP_DIR, zip_name)
    decks_name  = f"{date_prefix}_drafted_decks.csv"
    matches_name = gh_filename  # already the right name

    os.makedirs(ZIP_DIR, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(matches_name, matches_text)
        zf.writestr(decks_name, df_decks.to_csv(index=False))

    print(f"\nCreated: {zip_path}")
    print(f"  └── {matches_name}")
    print(f"  └── {decks_name}  (+tournament column)")


if __name__ == "__main__":
    main()
