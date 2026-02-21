"""
Draft pipeline runner
Runs the 3 preparation scripts in order, then launches the Deck Editor.

Usage:
    python run_pipeline.py
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SCRIPTS = ROOT / "scripts"

NOTEBOOKS = [
    "cubecobra card list downloader",
    "extractor and OCR",
    "archetype_decktype_data_downloader",
]

TIMEOUT_SECONDS = 1800  # 30 min — OCR on 12 players can be slow


def run_notebook(name: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  Running: {name}")
    print(f"{'=' * 60}")
    subprocess.run(
        [
            sys.executable, "-m", "jupyter", "nbconvert",
            "--to", "notebook",
            "--execute",
            "--inplace",
            f"--ExecutePreprocessor.timeout={TIMEOUT_SECONDS}",
            f"{name}.ipynb",
        ],
        cwd=SCRIPTS,
        check=True,
    )
    print(f"  Done: {name}")


def main() -> None:
    print("Starting draft pipeline...")

    for notebook in NOTEBOOKS:
        run_notebook(notebook)

    print(f"\n{'=' * 60}")
    print("  All scripts done. Launching Deck Editor...")
    print(f"{'=' * 60}\n")

    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(SCRIPTS / "deck_editor.py")],
        cwd=ROOT,
    )


if __name__ == "__main__":
    main()
