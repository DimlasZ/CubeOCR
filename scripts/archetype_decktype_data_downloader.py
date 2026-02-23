# Archetype & Decktype List Downloader
# Downloads archetype and decktype data from ManaCore and saves unique value lists.
#
# Outputs:
#   - data/archetype_decktype_data/archetype_list.csv
#   - data/archetype_decktype_data/decktype_list.csv

import pandas as pd
import requests
import os
import time
from io import StringIO

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'data', 'archetype_decktype_data')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Cache-busting param forces GitHub CDN to serve the latest file
cache_bust = f"?t={int(time.time())}"

# --- Archetypes ---
ARCHETYPE_URL = "https://raw.githubusercontent.com/GuySchnidrig/ManaCore/main/data/processed/card_archetype_game_winrates.csv"
print(f"Downloading archetypes from: {ARCHETYPE_URL}")
df_arch = pd.read_csv(StringIO(requests.get(ARCHETYPE_URL + cache_bust).text))
archetypes = sorted(df_arch['archetype'].unique())
print(f"Unique archetypes: {archetypes}")
archetype_list_file = os.path.join(OUTPUT_DIR, 'archetype_list.csv')
pd.DataFrame({'archetype': archetypes}).to_csv(archetype_list_file, index=False)
print(f"Saved {len(archetypes)} archetypes to {archetype_list_file}")

# --- Decktypes ---
DECKTYPE_URL = "https://raw.githubusercontent.com/GuySchnidrig/ManaCore/main/data/processed/decktype_game_winrate.csv"
print(f"\nDownloading decktypes from: {DECKTYPE_URL}")
df_dt = pd.read_csv(StringIO(requests.get(DECKTYPE_URL + cache_bust).text))
decktypes = sorted(df_dt['decktype'].unique())
print(f"Unique decktypes: {decktypes}")
decktype_list_file = os.path.join(OUTPUT_DIR, 'decktype_list.csv')
pd.DataFrame({'decktype': decktypes}).to_csv(decktype_list_file, index=False)
print(f"Saved {len(decktypes)} decktypes to {decktype_list_file}")
