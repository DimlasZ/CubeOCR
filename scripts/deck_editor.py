import os
import time
import streamlit as st
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent.parent
CLEAN_DIR = ROOT / "data" / "clean"
CARD_LIST_PATH = ROOT / "data" / "cardlist" / "dimlas5_cardlist.csv"
ARCHETYPE_LIST_PATH = ROOT / "data" / "archetype_decktype_data" / "archetype_list.csv"
DECKTYPE_LIST_PATH = ROOT / "data" / "archetype_decktype_data" / "decktype_list.csv"
OUTPUT_DIR = ROOT / "data" / "final"
EMPTY = "—"


@st.cache_data
def load_cube():
    df = pd.read_csv(CARD_LIST_PATH)
    return df[["name", "scryfall_id"]]


@st.cache_data
def load_archetypes():
    df = pd.read_csv(ARCHETYPE_LIST_PATH)
    return df["archetype"].dropna().tolist()


def load_decktypes():
    df = pd.read_csv(DECKTYPE_LIST_PATH)
    return df["decktype"].dropna().tolist()


def save_decktype(name):
    df = pd.read_csv(DECKTYPE_LIST_PATH)
    new_row = pd.DataFrame({"decktype": [name]})
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(DECKTYPE_LIST_PATH, index=False)


def get_draft_folders():
    if not CLEAN_DIR.exists():
        return []
    return sorted([d.name for d in CLEAN_DIR.iterdir() if d.is_dir()])


def get_players(draft_folder):
    folder = CLEAN_DIR / draft_folder
    csvs = list(folder.glob("clean_*.csv"))
    return sorted([f.stem.replace("clean_", "", 1) for f in csvs])


def load_player_cards(draft_folder, player):
    path = CLEAN_DIR / draft_folder / f"clean_{player}.csv"
    df = pd.read_csv(path)
    return df[["name", "scryfall_id"]].to_dict("records")


def get_annotated_image_path(draft_folder, player):
    path = CLEAN_DIR / draft_folder / "clean images" / f"annotated_{player}.jpeg"
    return path if path.exists() else None


def player_key(draft, player):
    return f"state__{draft}__{player}"


def init_player_state(draft_folder, player):
    key = player_key(draft_folder, player)
    if key not in st.session_state:
        cards = load_player_cards(draft_folder, player)
        archetype, decktype = load_saved_state(draft_folder, player)
        st.session_state[key] = {
            "cards": cards,
            "archetype": archetype,
            "decktype": decktype,
        }


def load_saved_state(draft_folder, player):
    out_path = OUTPUT_DIR / f"{draft_folder}.csv"
    if not out_path.exists():
        return None, None
    df = pd.read_csv(out_path)
    row = df[df["player"] == player]
    if row.empty:
        return None, None
    return row.iloc[0]["archetype"], row.iloc[0]["decktype"]


def do_save(state, player, draft):
    archetype = state["archetype"]
    decktype = state["decktype"]
    if not archetype or archetype == EMPTY:
        st.toast("Select an archetype first.", icon="⚠️")
        return
    if not decktype or decktype == EMPTY:
        st.toast("Select a decktype first.", icon="⚠️")
        return
    if not state["cards"]:
        st.toast("No cards in deck.", icon="⚠️")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{draft}.csv"
    rows = [
        {
            "archetype": archetype,
            "decktype": decktype,
            "player": player,
            "quantity": 1,
            "scryfallId": card["scryfall_id"],
        }
        for card in state["cards"]
    ]
    new_df = pd.DataFrame(rows)

    if out_path.exists():
        existing = pd.read_csv(out_path)
        existing = existing[existing["player"] != player]
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    combined.to_csv(out_path, index=False)
    st.toast(f"Saved {len(rows)} cards for {player}.", icon="✅")


# ── App ──────────────────────────────────────────────────────────────────────

st.set_page_config(layout="wide", page_title="CubeOCR Deck Editor")

# Sidebar
with st.sidebar:
    st.header("Navigation")
    draft_folders = get_draft_folders()
    if not draft_folders:
        st.error("No draft folders found in data/clean/")
        st.stop()

    if "draft_select" not in st.session_state or st.session_state["draft_select"] not in draft_folders:
        st.session_state["draft_select"] = draft_folders[-1]

    draft_idx = draft_folders.index(st.session_state["draft_select"])
    draft = st.selectbox("Draft", draft_folders, index=draft_idx)
    st.session_state["draft_select"] = draft
    players = get_players(draft)
    if not players:
        st.error("No players found in this draft.")
        st.stop()

    out_path = OUTPUT_DIR / f"{draft}.csv"
    saved_players = []
    if out_path.exists():
        saved_players = pd.read_csv(out_path)["player"].unique().tolist()

    player = st.radio(
        "Player",
        players,
        format_func=lambda p: f"✅ {p}" if p in saved_players else p,
    )

    st.divider()
    if st.button("🏁 Finish & Export", use_container_width=True, type="primary"):
        st.session_state["finishing"] = True

    if st.session_state.get("finishing"):
        st.success("Export started — you can close this window now.")
        time.sleep(1)
        os._exit(0)

# Init state
init_player_state(draft, player)
state = st.session_state[player_key(draft, player)]

# ── Title row with save button ────────────────────────────────────────────────

title_col, save_col = st.columns([0.92, 0.08])
with title_col:
    st.title(f"CubeOCR Deck Editor — {player}")
with save_col:
    st.write("")
    if st.button("💾", help="Save deck", use_container_width=True):
        do_save(state, player, draft)

# ── Layout ───────────────────────────────────────────────────────────────────

img_col, edit_col = st.columns([1, 1])

# Left: annotated image
with img_col:
    st.subheader("Annotated image")
    img_path = get_annotated_image_path(draft, player)
    if img_path:
        st.image(str(img_path), use_container_width=True)
    else:
        st.warning("No annotated image found for this player.")

# Right: editor
with edit_col:

    # ── Metadata ──
    st.subheader("Deck metadata")

    archetypes = [EMPTY] + load_archetypes()
    saved_arch = state["archetype"]
    arch_idx = archetypes.index(saved_arch) if saved_arch in archetypes else 0
    selected_arch = st.selectbox("Archetype", archetypes, index=arch_idx)
    state["archetype"] = None if selected_arch == EMPTY else selected_arch

    decktypes = load_decktypes()
    ADD_NEW = "➕ Add new decktype..."
    dt_options = [EMPTY] + decktypes + [ADD_NEW]
    saved_dt = state["decktype"]
    dt_idx = dt_options.index(saved_dt) if saved_dt in dt_options else 0
    selected_dt = st.selectbox("Decktype", dt_options, index=dt_idx)

    if selected_dt == ADD_NEW:
        new_dt = st.text_input("New decktype name", key="new_decktype_input")
        if st.button("Add decktype") and new_dt.strip():
            save_decktype(new_dt.strip())
            state["decktype"] = new_dt.strip()
            st.success(f"Added '{new_dt.strip()}' to decktype list.")
            st.rerun()
    elif selected_dt == EMPTY:
        state["decktype"] = None
    else:
        state["decktype"] = selected_dt

    st.divider()

    # ── Card list ──
    st.subheader(f"Cards ({len(state['cards'])})")

    to_remove = None
    for i, card in enumerate(state["cards"]):
        c1, c2 = st.columns([6, 1])
        c1.write(card["name"])
        if c2.button("✕", key=f"rm_{i}", help="Remove card"):
            to_remove = i

    if to_remove is not None:
        state["cards"].pop(to_remove)
        st.rerun()

    st.divider()

    # ── Add card ──
    st.subheader("Add missing card")

    cube = load_cube()
    existing_ids = {c["scryfall_id"] for c in state["cards"]}
    available = cube[~cube["scryfall_id"].isin(existing_ids)]

    search = st.text_input("Search card name", key="card_search")
    filtered = available[available["name"].str.contains(search, case=False, na=False)] if search else available

    if not filtered.empty:
        selected_card = st.selectbox("Select card to add", filtered["name"].tolist(), key="card_select")
        if st.button("Add card"):
            row = filtered[filtered["name"] == selected_card].iloc[0]
            state["cards"].append({"name": row["name"], "scryfall_id": row["scryfall_id"]})
            st.rerun()
    else:
        st.info("No cards match your search.")
