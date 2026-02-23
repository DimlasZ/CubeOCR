from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os
import sys
import re
import csv
import glob
import numpy as np
import easyocr
from PIL import Image, ImageDraw
import io
from difflib import get_close_matches

# Project root is one level up from this scripts/ folder
PROJECT_ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
from config import SCOPES, MAIN_FOLDER_ID

DRAFTED_DECKS_DIR = os.path.join(PROJECT_ROOT, 'data', 'drafted_decks')
CLEAN_OUTPUT_DIR  = os.path.join(PROJECT_ROOT, 'data', 'clean')
CARDLIST_DIR      = os.path.join(PROJECT_ROOT, 'data', 'cardlist')

SIMILARITY_THRESHOLD = 0.65

# --- Load official card list ---
cube_lists = glob.glob(os.path.join(CARDLIST_DIR, 'dimlas*_cardlist.csv'))
if not cube_lists:
    raise FileNotFoundError(f'No cube list found in {CARDLIST_DIR}')
CUBE_LIST_FILE = sorted(
    cube_lists,
    key=lambda f: int(re.search(r'dimlas(\d+)_cardlist', f).group(1)),
    reverse=True
)[0]

official_cards = set()
name_to_scryfall_id = {}
with open(CUBE_LIST_FILE, 'r', encoding='utf-8', newline='') as f:
    reader = csv.DictReader(f)
    name_col     = next((c for c in reader.fieldnames if c.strip().lower() == 'name'), None)
    scryfall_col = next((c for c in reader.fieldnames if c.strip().lower() == 'scryfall_id'), None)
    for row in reader:
        card = row[name_col].strip()
        if card:
            official_cards.add(card)
            if scryfall_col:
                name_to_scryfall_id[card] = row[scryfall_col].strip()
official_cards_lower = {c.lower(): c for c in official_cards}
print(f'Loaded {len(official_cards)} official cards from {os.path.basename(CUBE_LIST_FILE)}')

# --- Initialize EasyOCR ---
print('Initializing EasyOCR with GPU...')
reader_ocr = easyocr.Reader(['en'], gpu=True)
print('EasyOCR ready!\n')

# --- Google Drive auth ---
TOKEN_PATH       = os.path.join(PROJECT_ROOT, 'token.json')
CREDENTIALS_PATH = os.path.join(PROJECT_ROOT, 'credentials.json')
if os.path.exists(TOKEN_PATH):
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
else:
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(TOKEN_PATH, 'w') as token:
        token.write(creds.to_json())
drive_service = build('drive', 'v3', credentials=creds)

# --- Drive helpers ---
def get_folders(parent_id, name_pattern=None):
    """Get non-trashed folders from a parent folder."""
    query   = f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    folders = drive_service.files().list(q=query, fields='files(id, name)').execute().get('files', [])
    if name_pattern:
        folders = [f for f in folders if re.search(name_pattern, f['name'])]
    return folders

def get_files(parent_id, mime_type_filter=None):
    """Get non-trashed files from a folder, sorted by name."""
    query = f"'{parent_id}' in parents and trashed=false"
    if mime_type_filter:
        query += f" and mimeType contains '{mime_type_filter}'"
    files = drive_service.files().list(q=query, fields='files(id, name, mimeType)').execute().get('files', [])
    return sorted(files, key=lambda x: x['name'])

def is_player_file(filename):
    """Check if file is a player file (not an overview/backup file)."""
    name_lower = filename.lower()
    if '+' in filename:            return False
    if 'result'   in name_lower:   return False
    if 'standing' in name_lower:   return False
    if re.search(r'^r\d', name_lower): return False
    return True

def download_image(file_id):
    """Download image file from Google Drive."""
    return drive_service.files().get_media(fileId=file_id).execute()

# --- Find newest draft on Drive ---
print('Locating newest draft on Google Drive...')
season_folders = get_folders(MAIN_FOLDER_ID, r'Season \d+')
newest_season  = max(season_folders, key=lambda f: int(re.search(r'Season (\d+)', f['name']).group(1)))
print(f'  Season  : {newest_season["name"]}')

folders_in_season = get_folders(newest_season['id'])
pictures_folder   = next(f for f in folders_in_season if f['name'].lower() == 'pictures')

draft_folders = get_folders(pictures_folder['id'], r'\d{8}\s+Draft\s+\d+')
newest_draft  = max(draft_folders, key=lambda f: int(re.match(r'(\d{8})', f['name']).group(1)))
print(f'  Draft   : {newest_draft["name"]}')

all_files    = get_files(newest_draft['id'], mime_type_filter='image/')
player_files = [f for f in all_files if is_player_file(f['name'])]
print(f'  Players : {len(player_files)} image(s) found\n')

# --- Create output directories ---
draft_name    = newest_draft['name'].replace(' ', '_')
output_dir    = os.path.join(DRAFTED_DECKS_DIR, draft_name)
detailed_dir  = os.path.join(output_dir, 'detailed OCR')
clean_dir     = os.path.join(CLEAN_OUTPUT_DIR, draft_name)
clean_img_dir = os.path.join(clean_dir, 'clean images')
for d in [output_dir, detailed_dir, clean_dir, clean_img_dir]:
    os.makedirs(d, exist_ok=True)

print(f'Raw CSVs     : {output_dir}')
print(f'Detailed CSVs: {detailed_dir}')
print(f'Clean CSVs   : {clean_dir}')
print(f'Clean images : {clean_img_dir}')

# --- OCR helpers ---
def extract_text_from_image(image_bytes):
    """Extract text from image bytes using EasyOCR."""
    image   = Image.open(io.BytesIO(image_bytes))
    results = reader_ocr.readtext(np.array(image), detail=1)
    return image, results

def boxes_are_adjacent(bbox1, bbox2, max_x_distance=30, max_y_distance=10):
    """Check if two bounding boxes are close enough to be the same card name."""
    x1_min = min(p[0] for p in bbox1); x1_max = max(p[0] for p in bbox1)
    y1_min = min(p[1] for p in bbox1); y1_max = max(p[1] for p in bbox1)
    x2_min = min(p[0] for p in bbox2); x2_max = max(p[0] for p in bbox2)
    y2_min = min(p[1] for p in bbox2); y2_max = max(p[1] for p in bbox2)
    y_overlap      = not (y1_max < y2_min - max_y_distance or y2_max < y1_min - max_y_distance)
    horizontal_gap = min(abs(x1_max - x2_min), abs(x2_max - x1_min))
    return y_overlap and horizontal_gap <= max_x_distance

def merge_bboxes(bboxes):
    """Merge multiple bounding boxes into one encompassing box."""
    all_x = [p[0] for bbox in bboxes for p in bbox]
    all_y = [p[1] for bbox in bboxes for p in bbox]
    return [(min(all_x), min(all_y)), (max(all_x), min(all_y)),
            (max(all_x), max(all_y)), (min(all_x), max(all_y))]

def should_keep_text(text):
    """Filter out noise: short strings, mana symbols, UI labels, etc."""
    if len(text) < 3 or len(text) > 50:  return False
    if not any(c.isalpha() for c in text): return False
    if text.lower() in ['tap', 'untap', 'mana', 'cost', 'main', 'deck', 'sideboard']: return False
    if all(c.isdigit() or c in '{}/WUBRGC' for c in text): return False
    return True

def parse_and_merge_card_names(ocr_results):
    """Group adjacent OCR detections into single card names, sorted top to bottom."""
    filtered = []
    for bbox, text, confidence in ocr_results:
        if confidence < 0.05: continue
        text = text.strip()
        if not should_keep_text(text): continue
        filtered.append({
            'bbox': bbox, 'text': text, 'confidence': confidence,
            'x_min': min(p[0] for p in bbox), 'y_position': bbox[0][1]
        })

    merged_cards = []
    used = set()
    for i, det in enumerate(filtered):
        if i in used: continue
        group = [det]; used.add(i)
        changed = True
        while changed:
            changed = False
            for j, other in enumerate(filtered):
                if j in used: continue
                if any(boxes_are_adjacent(g['bbox'], other['bbox']) for g in group):
                    group.append(other); used.add(j); changed = True; break
        group.sort(key=lambda x: x['x_min'])
        merged_cards.append({
            'text':       ' '.join(d['text'] for d in group),
            'confidence': sum(d['confidence'] for d in group) / len(group),
            'bbox':       merge_bboxes([d['bbox'] for d in group]),
            'y_position': group[0]['y_position']
        })

    merged_cards.sort(key=lambda x: x['y_position'])
    return merged_cards

# --- Card validation ---
def validate_card(ocr_text, seen):
    """Match a single OCR result against the official card list.
    Returns (status, official_name). Status: exact | exact_corrected | fuzzy | duplicate | unmatched.
    `seen` is a set of already-used official names for duplicate detection.
    """
    if ocr_text.lower() in official_cards_lower:
        official_name = official_cards_lower[ocr_text.lower()]
        if official_name in seen:
            return 'duplicate', official_name
        seen.add(official_name)
        return ('exact' if ocr_text == official_name else 'exact_corrected'), official_name
    matches = get_close_matches(ocr_text, official_cards, n=1, cutoff=SIMILARITY_THRESHOLD)
    if matches:
        official_name = matches[0]
        if official_name in seen:
            return 'duplicate', official_name
        seen.add(official_name)
        return 'fuzzy', official_name
    return 'unmatched', None

# --- Image drawing ---
def draw_colored_boxes(image, merged_cards):
    """Draw green boxes for matched cards and red boxes for unmatched cards."""
    img_out = image.copy()
    draw    = ImageDraw.Draw(img_out)
    for card in merged_cards:
        color = 'green' if card['status'] in ('exact', 'exact_corrected', 'fuzzy') else 'red'
        draw.polygon(card['bbox'], outline=color, width=6)
    return img_out

# --- Main processing loop ---
print(f'Processing {len(player_files)} player(s)...')
print('-' * 60)

for idx, file in enumerate(player_files, 1):
    player_name = os.path.splitext(file['name'])[0]
    print(f'\n[{idx}/{len(player_files)}] {player_name}')

    try:
        print('  -> Downloading...')
        image_bytes = download_image(file['id'])

        print('  -> Running OCR...')
        original_image, ocr_results = extract_text_from_image(image_bytes)
        merged_cards = parse_and_merge_card_names(ocr_results)

        # Validate each detected card against the official list
        seen = set()
        for card in merged_cards:
            status, official_name     = validate_card(card['text'], seen)
            card['status']            = status
            card['official_name']     = official_name

        n_exact     = sum(1 for c in merged_cards if c['status'] in ('exact', 'exact_corrected'))
        n_corrected = sum(1 for c in merged_cards if c['status'] == 'fuzzy')
        n_unmatched = sum(1 for c in merged_cards if c['status'] == 'unmatched')
        n_duplicate = sum(1 for c in merged_cards if c['status'] == 'duplicate')
        print(f'  -> {len(merged_cards)} detections: {n_exact} exact, {n_corrected} corrected, {n_unmatched} unmatched, {n_duplicate} duplicates')

        # Save color-coded annotated image -> data/clean/{draft}/clean images/
        colored_image = draw_colored_boxes(original_image, merged_cards)
        img_path = os.path.join(clean_img_dir, f'annotated_{player_name}.jpeg')
        colored_image.save(img_path, quality=90)

        # Save raw OCR CSV (unvalidated) -> data/drafted_decks/{draft}/
        raw_csv_path = os.path.join(output_dir, f'{player_name}.csv')
        with open(raw_csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['name'])
            for card in merged_cards:
                writer.writerow([card['text']])

        # Save detailed validation CSV -> data/drafted_decks/{draft}/detailed OCR/
        detailed_path = os.path.join(detailed_dir, f'detailed_{player_name}.csv')
        with open(detailed_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['status', 'official_name', 'ocr_input', 'note'])
            for card in merged_cards:
                s     = card['status']
                oname = card['official_name'] or ''
                ocr   = card['text']
                if s in ('exact', 'exact_corrected'):
                    writer.writerow(['exact',     oname, ocr, ''])
                elif s == 'fuzzy':
                    writer.writerow(['corrected', oname, ocr, f'corrected from: {ocr}'])
                elif s == 'unmatched':
                    writer.writerow(['unmatched', '',    ocr, 'no match found'])
                elif s == 'duplicate':
                    writer.writerow(['duplicate', oname, ocr, 'duplicate removed'])

        # Save clean deck list -> data/clean/{draft}/
        clean_csv_path = os.path.join(clean_dir, f'clean_{player_name}.csv')
        with open(clean_csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['name', 'scryfall_id'])
            for card in merged_cards:
                if card['status'] in ('exact', 'exact_corrected', 'fuzzy'):
                    writer.writerow([card['official_name'], name_to_scryfall_id.get(card['official_name'], '')])

        print(f'  annotated_{player_name}.jpeg')
        print(f'  detailed_{player_name}.csv')
        print(f'  clean_{player_name}.csv')

    except Exception as e:
        print(f'  ERROR: {e}')

print(f'\n{"=" * 60}')
print(f'Done!')
print(f'  Clean images  -> {clean_img_dir}')
print(f'  Clean CSVs    -> {clean_dir}')
print(f'  Detailed CSVs -> {detailed_dir}')
