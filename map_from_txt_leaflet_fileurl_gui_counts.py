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

# Reguliarūs reiškiniai duomenų ištraukimui
COORD_RE = re.compile(r"([-+]?\d{1,3}\.\d+)\s*[,;\s]\s*([-+]?\d{1,3}\.\d+)")
DATE_RE = re.compile(r"(\d{4}[-/.]\d{2}[-/.]\d{2}(?:\s+\d{2}:\d{2}(?:\:\d{2})?)?|\d{2}[-/.]\d{2}[-/.]\d{4}(?:\s+\d{2}:\d{2}(?:\:\d{2})?)?)")
CELL_RE = re.compile(r"(?:cell\s*id|cid)[:\s=-]*(\d+)", re.IGNORECASE)

def safe_js_string(text: str) -> str:
    """Išvalo tekstą nuo bet kokių simbolių, galinčių sulaužyti JavaScript."""
    if not text:
        return ""
    # Pašaliname abiejų rūšių kabutes ir backslash'us
    text = text.replace("\\", "/").replace("'", "").replace('"', "")
    # Pašaliname eilutės perkėlimus, kad JS neskaitytų kaip nebaigtos eilutės
    text = text.replace("\n", " ").replace("\r", " ")
    return text.strip()

def parse_file_lines(text: str):
    """Nuskaito tekstą eilutėmis ir ištraukia koordinates bei info."""
    records = []
    lines = text.splitlines()
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # 1. Ieškome koordinačių
        coord_match = COORD_RE.search(line)
        if not coord_match:
            continue
            
        lat, lon = float(coord_match.group(1)), float(coord_match.group(2))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
            
        remaining_text = line.replace(coord_match.group(0), "")
        
        # 2. Ieškome Datos ir Laiko
        date_match = DATE_RE.search(remaining_text)
        date_val = safe_js_string(date_match.group(1)) if date_match else "Nenurodyta"
        if date_match:
            remaining_text = remaining_text.replace(date_match.group(0), "")
            
        # 3. Ieškome Cell ID
        cell_ids = CELL_RE.findall(remaining_text)
        cell_val = safe_js_string(", ".join(cell_ids)) if cell_ids else "Nenurodyta"
        for cid in cell_ids:
            remaining_text = re.sub(rf"(?:cell\s*id|cid)[:\s=-]*{cid}", "", remaining_text, flags=re.IGNORECASE)
            
        # 4. Adresas (viskas, kas liko)
        address_val = re.sub(r'^[\s,;\-]+|[\s,;\-]+$', '', remaining_text).strip()
        address_val = safe_js_string(address_val)
        if not address_val:
            address_val = "Nenurodytas adresas"
            
        records.append({
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "date": date_val,
            "cell_id": cell_val,
            "address": address_val
        })
        
    return records

def aggregate_records(records):
    """Sugrupuoja įrašus pagal unikalias koordinates."""
    aggregated = defaultdict(lambda: {"count": 0, "details": [], "addresses": set()})
    
    for r in records:
        key = (r["lat"], r["lon"])
        aggregated[key]["count"] += 1
        aggregated[key]["details"].append({
            "date": r["date"],
            "cell_id": r["cell_id"]
        })
        if r["address"] and r["address"] != "Nenurodytas adresas":
            aggregated[key]["addresses"].add(r["address"])
            
    for key in aggregated:
        if aggregated[key]["addresses"]:
            aggregated[key]["main_address"] = " | ".join(sorted(list(aggregated[key]["addresses"])))
        else:
            aggregated[key]["main_address"] = "Nenurodytas adresas"
            
    return aggregated

def make_leaflet_html(aggregated_data, title="Žemėlapis"):
    points = list(aggregated_data.items())
    first = points[0][0] if points else (0, 0)

    markers_js = []
    bounds_points_js = []
    
    for (lat, lon), info in points:
        cnt = info["count"]
        addr = info["main_address"]
        
        # Sukuriame popup HTML turinį saugiai
        popup_html = f"<b>{addr}</b><br><small>{lat}, {lon}</small><br><br>"
        popup_html += "<table style='font-size:11px; border-collapse:collapse; width:100%;'>"
        popup_html += "<tr style='border-bottom:1px solid #ccc; text-align:left;'><th>Data/Laikas</th><th>Cell ID</th></tr>"
        
        for det in info["details"]:
            popup_html += f"<tr><td style='padding:2px 4px;'>{det['date']}</td><td style='padding:2px 4px;'>{det['cell_id']}</td></tr>"
        popup_html += f"</table><br><b>Viso apsilankymų: {cnt}×</b>"

        # Naudojame json.dumps, kad visiškai apsisaugotume nuo JS klaidų perduodant tekstą
        safe_popup_html = json.dumps(popup_html)

        markers_js.append(
            f"""
            (function() {{
                var m = L.marker([{lat}, {lon}]).addTo(map);
                m.bindPopup({safe_popup_html}, {{maxWidth: 300}});
                m.bindTooltip('{cnt}×', {{permanent: true, direction: 'top', className: 'count-tip'}});
            }})();
            """
        )
        bounds_points_js.append(f"[{lat}, {lon}]")

    markers_combined = "\n".join(markers_js)

    if len(points) > 1:
        fit_js = "var bounds = L.latLngBounds([\n" + ", ".join(bounds_points_js) + "\n]);\nmap.fitBounds(bounds);"
    else:
        fit_js = f"map.setView([{first[0]}, {first[1]}], 12);"

    summary_rows = sorted(points, key=lambda x: x[1]["count"], reverse=True)
    summary_html_rows = ""
    for (lat, lon), info in summary_rows:
        addr_short = info["main_address"]
        if len(addr_short) > 25:
            addr_short = addr_short[:22] + "..."
        summary_html_rows += f"<tr><td><span title='{info['main_address']}'>{addr_short}</span><br><small style='color:#666'>{lat:.5f}, {lon:.5f}</small></td><td style='text-align:right; vertical-align:middle;'>{info['count']}×</td></tr>"

    total_visits = sum(info["count"] for _, info in points)
    unique_places = len(points)

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
html,body,#map {{height:100%;margin:0;padding:0}}
#map {{height:100vh}}
.count-tip {{
  background:#111;color:#fff;border:none;border-radius:6px;padding:2px 6px;font-weight:bold;
  box-shadow:0 1px 4px rgba(0,0,0,.3);
}}
#summary {{
  position:absolute; top:10px; left:10px; z-index:1000;
  background: rgba(255,255,255,.95); padding:12px; border-radius:10px;
  max-height: 75vh; overflow:auto; box-shadow:0 2px 10px rgba(0,0,0,.2);
  font: 13px/1.4 system-ui, -apple-system, sans-serif;
  width: 280px;
}}
#summary table {{ border-collapse: collapse; width:100%; }}
#summary th, #summary td {{ padding:6px 4px; border-bottom:1px solid #eee; text-align:left; }}
#summary h3 {{ margin:0 0 4px 0; font-size:15px; }}
#summary .small {{ color:#555; font-size:11px; margin-bottom:8px; }}
</style>
</head>
<body>
<div id="map"></div>

<div id="summary">
  <h3>Suvestinė</h3>
  <div class="small">Unikalių vietų: <b>{unique_places}</b> · Įrašų viso: <b>{total_visits}</b></div>
  <table>
    <thead><tr><th>Vieta / Koordinatės</th><th style='text-align:right'>Kartai</th></tr></thead>
    <tbody>
      {summary_html_rows}
    </tbody>
  </table>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
var map = L.map('map');
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 19,
    attribution: '© OpenStreetMap contributors'
}}).addTo(map);

{markers_combined}

{fit_js}
</script>
</body>
</html>
"""
    return html

def choose_file_dialog():
    if tk is None:
        return None
    root = tk.Tk(); root.withdraw()
    path = filedialog.askopenfilename(
        title="Pasirink failą su koordinatėmis ir informacija",
        filetypes=[("Tekstiniai failai", "*.txt *.csv"), ("Visi failai", "*.*")]
    )
    root.destroy()
    return path

def show_error(msg: str):
    if tk is not None:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Klaida", msg)
        root.destroy()
    else:
        print(msg)

def process_file(path: Path):
    try:
        text = path.read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        show_error(f"Nepavyko perskaityti failo:\n{e}")
        return
        
    records = parse_file_lines(text)
    if not records:
        show_error("Nerasta koordinačių ar tinkamų duomenų šiame faile.\nPatikrinkite, ar faile yra skaičiai formatu: 54.1234, 25.1234")
        return
        
    aggregated_data = aggregate_records(records)
    html = make_leaflet_html(aggregated_data, title=path.name)
    
    out = Path(tempfile.gettempdir()) / "leaflet_map_advanced.html"
    out.write_text(html, encoding='utf-8')
    webbrowser.open(out.as_uri())

if __name__ == '__main__':
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
        if not p.exists():
            show_error(f"Failas nerastas:\n{p}")
            sys.exit(1)
        process_file(Path(p))
    else:
        chosen = choose_file_dialog()
        if chosen:
            process_file(Path(chosen))
        else:
            show_error("Failas nepasirinktas.")
