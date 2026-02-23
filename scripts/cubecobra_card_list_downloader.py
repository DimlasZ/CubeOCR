# CubeCobra Card List Downloader
# Downloads your cube's card list from CubeCobra and saves it as a sorted .csv file.
# Run this whenever you want an up-to-date local copy of your cube.
#
# What it does:
#   1. Fetches the cube CSV export from CubeCobra using the cube ID
#   2. Parses card names, set codes, and collector numbers
#   3. Saves them alphabetically to a local CSV file ({CUBE_ID}_cardlist.csv)
#   4. Enriches with Scryfall IDs using set + collector number

import requests
import csv
import io
import os
import sys
import time

# Project root is one level up from this scripts/ folder
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARDLIST_DIR = os.path.join(PROJECT_ROOT, 'data', 'cardlist')

CUBE_ID = "dimlas5"
CSV_URL = f"https://cubecobra.com/cube/download/csv/{CUBE_ID}"

print(f"Downloading from: {CSV_URL}")

response = requests.get(CSV_URL)
response.raise_for_status()

# Parse CSV and extract card data
csv_data = csv.DictReader(io.StringIO(response.text))
cards = []

for row in csv_data:
    name = row.get('name', row.get('Name', '')).strip()
    set_code = row.get('Set', '').strip().lower()
    collector_num = row.get('Collector Number', '').strip()
    if name:
        cards.append({'name': name, 'set': set_code, 'collector_number': collector_num})

print(f"Downloaded {len(cards)} cards")

# Save to CSV file (sorted by name)
os.makedirs(CARDLIST_DIR, exist_ok=True)
output_file = os.path.join(CARDLIST_DIR, f"{CUBE_ID}_cardlist.csv")
cards.sort(key=lambda c: c['name'])

with open(output_file, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['name', 'set', 'collector_number', 'scryfall_id'])
    writer.writeheader()
    for card in cards:
        writer.writerow({'name': card['name'], 'set': card['set'],
                         'collector_number': card['collector_number'], 'scryfall_id': ''})

print(f"Saved {len(cards)} cards to {output_file}")

# --- Scryfall ID Enrichment ---
# Uses set code + collector number from CubeCobra to get the EXACT scryfall ID
# for the specific printing in your cube (not a random printing).
# Batch lookup via /cards/collection (75 per request), with retry on failure.

MAX_RETRIES = 3
BATCH_SIZE  = 75

# Load card data from the saved CSV
cards = []
with open(output_file, 'r', encoding='utf-8', newline='') as f:
    reader = csv.DictReader(f)
    for row in reader:
        cards.append({
            'name': row['name'],
            'set': row['set'],
            'collector_number': row['collector_number'],
            'scryfall_id': row.get('scryfall_id', '')
        })

print(f"Loaded {len(cards)} cards from {output_file}")

# Build batch identifiers using set + collector_number
identifiers = []
for card in cards:
    if card['set'] and card['collector_number']:
        identifiers.append({
            'set': card['set'],
            'collector_number': card['collector_number']
        })
    else:
        identifiers.append({'name': card['name']})

batches = [identifiers[i:i + BATCH_SIZE] for i in range(0, len(identifiers), BATCH_SIZE)]
print(f"Fetching scryfall IDs in {len(batches)} batches...\n")

# set/collector_number -> scryfall_id
scryfall_map = {}

for i, batch in enumerate(batches, 1):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                "https://api.scryfall.com/cards/collection",
                json={"identifiers": batch},
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()

            for card in data.get("data", []):
                key = f"{card['set']}|{card['collector_number']}"
                scryfall_map[key] = card["id"]
                # Also store by name (front face) as fallback key
                front_name = card["name"].split(" // ")[0].strip()
                scryfall_map[f"name|{front_name}"] = card["id"]
                scryfall_map[f"name|{card['name']}"] = card["id"]

            print(f"  Batch {i}/{len(batches)} done ({len([v for k,v in scryfall_map.items() if not k.startswith('name|')])} found so far)")
            time.sleep(0.1)
            break
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt < MAX_RETRIES:
                wait = attempt * 5
                print(f"  Batch {i} attempt {attempt} failed — retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  Batch {i} FAILED after {MAX_RETRIES} attempts: {e}")

# Match results back to cards
for card in cards:
    key = f"{card['set']}|{card['collector_number']}"
    if key in scryfall_map:
        card['scryfall_id'] = scryfall_map[key]
    else:
        # Fallback: try by name
        name_key = f"name|{card['name']}"
        if name_key in scryfall_map:
            card['scryfall_id'] = scryfall_map[name_key]

# Write enriched CSV
with open(output_file, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['name', 'set', 'collector_number', 'scryfall_id'])
    writer.writeheader()
    writer.writerows(cards)

# Summary
total_found = sum(1 for c in cards if c['scryfall_id'])
total_cards = len(cards)
missing = [c['name'] for c in cards if not c['scryfall_id']]
print(f"\n{'='*40}")
print(f"  Total found   : {total_found}/{total_cards}")
if missing:
    print(f"  Still missing ({len(missing)}):")
    for name in missing:
        print(f"    - {name}")
else:
    print(f"  Full cube matched!")
print(f"{'='*40}")
