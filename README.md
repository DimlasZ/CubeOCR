# CubeOCR

A Python pipeline that automatically reads drafted Magic: The Gathering cube decks from player photos using OCR, then matches them against a known card list to produce clean, structured output per player — ready for tournament export.

---

## Pipeline overview

```
python run_pipeline.py
```

Runs the following steps in order:

| Step | Script | What it does |
|------|--------|--------------|
| 1 | `cubecobra_card_list_downloader.py` | Downloads the cube card list from CubeCobra and enriches each card with its Scryfall ID |
| 2 | `extractor_and_OCR.py` | Connects to Google Drive, finds the newest draft folder, runs EasyOCR on each player image, validates card names against the cube list, outputs CSVs and annotated images |
| 3 | `archetype_decktype_data_downloader.py` | Downloads archetype and decktype reference lists from [ManaCore](https://github.com/GuySchnidrig/ManaCore) |
| 4 | `deck_editor.py` | Launches a Streamlit app to manually review and correct OCR results, and assign archetype/decktype per player |
| 5 | `build_tournament_export.py` | Downloads match results from TournamentOrganizer on GitHub, combines with the final deck data, and packages everything into a `.zip` |

---

## Data flow

```
data/
├── cardlist/               ← cube card list with Scryfall IDs
├── archetype_decktype_data/← archetype + decktype reference lists
├── drafted_decks/          ← raw OCR output per draft (one CSV per player)
│   └── {draft}/
│       ├── {player}.csv            ← unvalidated OCR names
│       └── detailed OCR/
│           └── detailed_{player}.csv  ← status per detection (exact/corrected/unmatched/duplicate)
├── clean/                  ← validated output per draft
│   └── {draft}/
│       ├── clean_{player}.csv      ← matched card names + Scryfall IDs
│       └── clean images/
│           └── annotated_{player}.jpeg  ← image with green/red boxes per detection
├── final/                  ← deck editor output (reviewed + archetype/decktype assigned)
└── zip/                    ← tournament export zips
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

EasyOCR runs on GPU by default. A CUDA-capable GPU is recommended for speed but not required.

### 2. Google Drive API

- Go to [Google Cloud Console](https://console.cloud.google.com/)
- Create a project and enable the **Google Drive API**
- Create OAuth 2.0 credentials (Desktop app)
- Download `credentials.json` and place it in the project root
- Add yourself as a test user in the OAuth consent screen

On first run, a browser window opens for Google sign-in. A `token.json` is then saved for future runs.

### 3. Configure Drive folder

Set your top-level Google Drive folder ID in `config.py`:

```python
MAIN_FOLDER_ID = 'your-folder-id-here'
```

The pipeline expects this folder structure on Drive:

```
Main Folder/
└── Season {N}/
    └── Pictures/
        └── {YYYYMMDD} Draft {N}/
            ├── {Player}.jpg
            └── ...
```

---

## Requirements

- Python 3.10+
- A CUDA GPU (optional, but EasyOCR is significantly faster with one)
- Google Drive API credentials (see Setup)

---

## Notes

- `credentials.json` and `token.json` are excluded via `.gitignore` — never commit these
- The pipeline automatically picks the newest Season and Draft folder from Drive
- OCR validation uses fuzzy matching (threshold: 0.65) — cards not in the cube list are flagged as `unmatched` for manual review in the deck editor
