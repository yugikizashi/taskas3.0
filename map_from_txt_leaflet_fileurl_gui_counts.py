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

# Žemėlapio lentelėse naudojami pilni ir gražūs laukų pavadinimai
DISPLAY_FIELDS = [
    "Provider Name", "Retain Date", "aParty Number", "bParty Number", 
    "Dialed Number", "Duration", "Service Type", "Service", 
    "Connection Type", "Connection Status", "CellId1", "CellId2", 
    "CellId1 Address", "CellId2 Address", "CellId1 Latitude", "CellId1 Longitude", 
    "CellId2 Latitude", "CellId2 Longitude", "plmn", "IMEI", "IMSI"
]

# Reguliarusis reiškinys koordinačių paieškai tekste, jei stulpeliai nesuveiktų
COORD_RE = re.compile(r"([-+]?\d{{1,3}}\.\d+)\s*[,;\s\t]\s*([-+]?\d{{1,3}}\.\d+)")

def safe_js_string(text: str) -> str:
    """Išvalo tekstą, kad HTML/JS kodas nesulūžtų."""
    if not text:
        return ""
    return str(text).replace("\\", "/").replace("'", "").replace('"', "").strip()

def find_column_index(header_parts, targets):
    """Suranda stulpelio indeksą pagal pilną arba nukirstą pavadinimą."""
    for target in targets:
        t_clean = target.lower().strip()
        for idx, part in enumerate(header_parts):
            p_clean = part.lower().strip()
            if p_clean == t_clean or p_clean.startswith(t_clean[:7]):
                return idx
    return None

def parse_file_to_records(text: str):
    """Nuskaito duomenis, lanksčiai ieškodamas koordinačių CellId1 arba CellId2 laukuose."""
    records = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return records

    first_line = lines[0]
    delimiter = "\t" if "\t" in first_line else (";" if ";" in first_line else ",")
    header_parts = [p.strip() for p in first_line.split(delimiter)]
    
    # Prisitaikome prie tavo stulpelių pavadinimų variantų iš nuotraukų
    field_mapping_rules = {
        "Provider Name": ["provider name", "provider n", "provider"],
        "Retain Date": ["retain date", "retain d"],
        "aParty Number": ["aparty number", "aparty nu"],
        "bParty Number": ["bparty number", "bparty nu"],
        "Dialed Number": ["dialed number", "dialed nu"],
        "Duration": ["duration"],
        "Service Type": ["service type", "service ty"],
        "Service": ["service"],
        "Connection Type": ["connection type", "connectic"],
        "Connection Status": ["connection status", "connectic status"],
        "CellId1": ["cellid1"],
        "CellId2": ["cellid2"],
        "CellId1 Address": ["cellid1 address", "cellid1 ad"],
        "CellId2 Address": ["cellid2 address", "cellid2 ad"],
        "CellId1 Latitude": ["cellid1 latitude", "cellid1 lat"],
        "CellId1 Longitude": ["cellid1 longitude", "cllid1 longitude", "cllid1 lon"],
        "CellId2 Latitude": ["cellid2 latitude", "cellid2 lat"],
        "CellId2 Longitude": ["cellid2 longitude", "cellid2 lo"],
        "plmn": ["plmn"],
        "IMEI": ["imei"],
        "IMSI": ["imsi"]
    }
    
    field_map = {}
    for field_key, aliases in field_mapping_rules.items():
        idx = find_column_index(header_parts, aliases)
        if idx is not None:
            field_map[field_key] = idx

    for line in lines[1:]:
        parts = [p.strip() for p in line.split(delimiter)]
        if len(parts) < 2:
            continue
            
        row_info = {f: "Nenurodyta" for f in DISPLAY_FIELDS}
        
        for field_key, col_idx in field_map.items():
            if col_idx < len(parts) and parts[col_idx]:
                row_info[field_key] = safe_js_string(parts[col_idx])
        
        lat, lon = None, None

        # 1 STRATEGIJA: Tikriname CellId1 koordinates
        try:
            l1 = row_info.get("CellId1 Latitude", "Nenurodyta")
            o1 = row_info.get("CellId1 Longitude", "Nenurodyta")
            if l1 != "Nenurodyta" and o1 != "Nenurodyta":
                lat = float(l1.replace(",", "."))
                lon = float(o1.replace(",", "."))
        except ValueError:
            lat, lon = None, None

        # 2 STRATEGIJA: Jei CellId1 tuščias/netinkamas, tikriname CellId2 koordinates
        if lat is None or lon is None or lat == 0:
            try:
                l2 = row_info.get("CellId2 Latitude", "Nenurodyta")
                o2 = row_info.get("CellId2 Longitude", "Nenurodyta")
                if l2 != "Nenurodyta" and o2 != "Nenurodyta":
                    lat = float(l2.replace(",", "."))
                    lon = float(o2.replace(",", "."))
            except ValueError:
                lat, lon = None, None

        # 3 STRATEGIJA: Jei stulpeliuose tuščia, ieškome bet kur eilutės tekste
        if lat is None or lon is None or lat == 0:
            match = COORD_RE.search(line)
            if match:
                try:
                    lat = float(match.group(1).replace(",", "."))
                    lon = float(match.group(2).replace(",", "."))
                except ValueError:
                    continue

        # Jei koordinačių rasti nepavyko, šią eilutę praleidžiame
        if lat is None or lon is None or lat == 0:
            continue

        if -90 <= lat <= 90 and -180 <= lon <= 180:
            row_info["_lat"] = round(lat, 5)
            row_info["_lon"] = round(lon, 5)
            records.append(row_info)

    return records

def aggregate_records(records):
    """Sugrupuoja sujungimus pagal identiškas koordinates."""
    aggregated = defaultdict(lambda: {"count": 0, "details": [], "address": "Nenurodytas adresas"})
    
    for r in records:
        key = (r["_lat"], r["_lon"])
        aggregated[key]["count"] += 1
        aggregated[key]["details"].append(r)
        
        # Sumanus adreso parinkimas suvestinei: pirmenybė CellId1, jei tuščia – CellId2
        c1_addr = r.get("CellId1 Address", "Nenurodyta")
        c2_addr = r.get("CellId2 Address", "Nenurodyta")
        
        if c1_addr != "Nenurodyta" and c1_addr:
            aggregated[key]["address"] = c1_addr
        elif c2_addr != "Nenurodyta" and c2_addr:
            aggregated[key]["address"] = c2_addr
            
    return aggregated

def make_leaflet_html(aggregated_data, title="Žemėlapis"):
    points = list(aggregated_data.items())
    first = points[0][0] if points else (0, 0)

    markers_js = []
    bounds_points_js = []
    
    for (lat, lon), info in points:
        cnt = info["count"]
        main_addr = info["address"]
        
        popup_html = f"<div style='min-width:350px; max-height:400px; overflow-y:auto; font-family:sans-serif; font-size:11px; line-height:1.5;'>"
        popup_html += f"<b>Adresas:</b> {main_addr}<br><small><b>Koordinatės:</b> {lat}, {lon}</small><hr style='border:0; border-top:1px solid #ccc; margin: 8px 0;'>"
        
        for idx, det in enumerate(info["details"]):
            popup_html += f"<div style='margin-bottom:12px; padding: 8px; background: #f9f9f9; border-radius: 4px; border-left: 4px solid #0078AA;'>"
            popup_html += f"<b style='color:#0078AA; font-size:12px;'>Sujungimas #{idx+1}</b><br style='margin-bottom:6px;'>"
            
            for f in DISPLAY_FIELDS:
                val = det.get(f, "Nenurodyta")
                if val and val != "Nenurodyta":
                    popup_html += f"<b>{f}:</b> {val}<br>"
            popup_html += "</div>"
            
        popup_html += f"<div style='margin-top:8px; font-weight:bold; font-size:12px; color:#111;'>Viso sujungimų šioje vietoje: {cnt}×</div></div>"

        safe_popup_html = json.dumps(popup_html)

        markers_js.append(
            f"""
            (function() {{
                var m = L.marker([{lat}, {lon}]).addTo(map);
                m.bindPopup({safe_popup_html}, {{maxWidth: 380}});
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
        addr_full = info["address"]
        addr_short = addr_full if len(addr_full) <= 30 else addr_full[:27] + "..."
        
        summary_html_rows += f"""
        <tr>
            <td style='max-width:140px; word-wrap:break-word;'><span title='{addr_full}'>{addr_short}</span></td>
            <td style='color:#555; font-size:11px; white-space:nowrap;'>{lat:.5f},<br>{lon:.5f}</td>
            <td style='text-align:right; font-weight:bold; color:#0078AA;'>{info['count']}×</td>
        </tr>
        """

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
  background: rgba(255,255,255,.96); padding:12px; border-radius:10px;
  max-height: 80vh; overflow-y:auto; box-shadow:0 4px 15px rgba(0,0,0,.15);
  font: 12px/1.4 system-ui, -apple-system, sans-serif;
  width: 340px;
}}
#summary table {{ border-collapse: collapse; width:100%; table-layout: fixed; }}
#summary th, #summary td {{ padding:6px 4px; border-bottom:1px solid #eee; text-align:left; vertical-align:middle; }}
#summary h3 {{ margin:0 0 4px 0; font-size:15px; color:#111; }}
#summary .small {{ color:#666; font-size:11px; margin-bottom:10px; }}
</style>
</head>
<body>
<div id="map"></div>

<div id="summary">
  <h3>Suvestinė</h3>
  <div class="small">Unikalių vietų: <b>{unique_places}</b> · Sujungimų viso: <b>{total_visits}</b></div>
  <table>
    <thead>
      <tr>
        <th style='width:45%'>Adresas</th>
        <th style='width:35%'>Koordinatės</th>
        <th style='width:20%; text-align:right;'>Sujung.</th>
      </tr>
    </thead>
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
        title="Pasirink failą su duomenimis",
        filetypes=[("Tekstiniai / CSV failai", "*.txt *.csv"), ("Visi failai", "*.*")]
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
        
    records = parse_file_to_records(text)
    if not records:
        show_error("KLAIDA: Failo struktūra neatitinka reikalavimų arba jame visiškai nėra koordinačių.")
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
