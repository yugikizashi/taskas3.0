#!/usr/bin/env python3
# map_from_txt_leaflet_fileurl_gui_counts.py

import re
import tempfile
import webbrowser
import sys
import json
from pathlib import Path
from collections import defaultdict

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
except Exception:
    tk = None

# Pagrindiniai laukai, kurių ieškosime faile
FIELDS = [
    "Provider Name", "Retain Date", "aParty Number", "bParty Number", 
    "Dialed Number", "Duration", "Service Type", "Service", 
    "Connection Type", "Connection Status", "CellId1", "CellId2", 
    "CellId1 Address", "CellId2 Address", "CellId1 Latitude", "CllId1 Longitude", 
    "CellId2 Latitude", "CellId2 Longitude", "plmn", "IMEI", "IMSI"
]

# Reguliarus reiškinys koordinatėms surasti teksto eilutėje
COORD_RE = re.compile(r"([-+]?\d{1,3}\.\d+)\s*[,;\s\t]\s*([-+]?\d{1,3}\.\d+)")

def safe_js_string(text: str) -> str:
    """Išvalo tekstą nuo bet kokių simbolių, galinčių sugadinti JavaScript."""
    if not text:
        return ""
    text = str(text).replace("\\", "/").replace("'", "").replace('"', "")
    text = text.replace("\n", " ").replace("\r", " ")
    return text.strip()

def parse_file_to_records(text: str):
    """
    Analizuoja failą eilutėmis. Bando surasti koordinates ir tavo nurodytus laukus.
    """
    records = []
    lines = text.splitlines()
    if not lines:
        return records

    # Tikriname, ar pirmoji eilutė yra stulpelių pavadinimai (antraip skaitome kaip TXT)
    header = [f.strip().lower() for f in re.split(r'[\t,;]', lines[0])]
    is_csv_or_tsv = any(f.lower() in header for f in FIELDS)

    for idx, line in enumerate(lines):
        if is_csv_or_tsv and idx == 0:
            continue  # Praleidžiame antraštę, jei tai CSV/TSV
            
        line_str = line.strip()
        if not line_str:
            continue

        lat, lon = None, None
        row_info = {f: "Nenurodyta" for f in FIELDS}

        # Jei failas labiau panašus į lentelę (CSV/TSV)
        if is_csv_or_tsv:
            parts = re.split(r'[\t,;]', line_
