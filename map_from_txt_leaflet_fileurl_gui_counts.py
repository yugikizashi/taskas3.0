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

# Tikslūs stulpelių pavadinimai iš tavo pateiktos nuotraukos
FIELDS = [
    "Provider Name", "Retain Date", "aParty Number", "bParty Number", 
    "Dialed Number", "Duration", "Service Type", "Service", 
    "Connection Type", "Connection Status", "CellId1", "CellId2", 
    "CellId1 Address", "CellId2 Address", "CellId1 Latitude", "CellId1 Longitude", 
    "CellId2 Latitude", "CellId2 Longitude", "plmn", "IMEI", "IMSI"
]

def safe_js_string(text: str) -> str:
    """Išvalo tekstą, kad jis nesulaužytų žemėlapio kodo."""
    if not text:
        return ""
    text = str(text).replace("\\", "/").replace("'", "").replace('"', "")
    return text.strip()

def parse_file_to_records(text: str):
    """Protingas failo nuskaitymas, palaikantis Tab, kablelio ir kabliataškio skirtukus."""
    records = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return records

    # Nustatome, koks skirtukas naudojamas pirmoje eilutėje (antraštėje)
    first_line = lines[0]
    if "\t" in first_line:
        delimiter = "\t"
    elif ";" in first_line:
        delimiter = ";"
    else:
        delimiter = ","

    # Sukuriame švarią antraštę (pašaliname tarpus kraštuose ir paverčiame mažosiomis raidėmis)
    header = [col.strip().lower() for col in first_line.split(delimiter)]
    
    # Patikriname, ar faile tikrai yra mūsų ieškomi stulpeliai
    has_any_field = any(f.lower() in header for f in FIELDS)
    if not has_any_field:
        return records  # Jei nerasta stulpelių, grąžiname tuščią sąrašą

    # Skaitome duomenų eilutes
    for line in lines[1:]:
        # Skaidome eilutę tik pagal nustatytą skirtuką
        parts = [p.strip() for p in line.split(delimiter)]
        
        row_info = {f: "Nenurodyta" for f in FIELDS}
        
        # Užpildome duomenis griežtai pagal stulpelių pavadinimus
        for f in FIELDS:
            f_lower = f.lower()
            if f_lower in header:
                h_idx = header.index(f_lower)
                if h_idx < len(parts) and parts[h_idx]:
                    row_info[f] = safe_js_string(parts[h_idx])

        # Bandom paimti koordinates iš konkrečių stulpelių
        try:
            lat_str = row_info.get("CellId1 Latitude", "0").replace(",", ".")
            lon_str = row_info.get("CellId1 Longitude", "0").replace(",", ".")
            
            lat = float(lat_str)
            lon = float(lon_str)
            
            # Jei CellId1 neturi koordinačių, tikriname CellId2
            if lat == 0 and lon == 0:
                lat_str = row_info.get("CellId2 Latitude", "0").replace(",", ".")
                lon_str = row_info.get("CellId2 Longitude", "0").replace(",", ".")
                lat = float(lat_str)
                lon = float(lon_str)
                
        except ValueError:
            continue

        # Jei koordinatės teisingos, išsaugojame įrašą
        if lat != 0 and lon != 0 and (-90 <= lat <= 90 and -180 <= lon <= 180):
            row_info["_lat"] = round(lat, 5)
            row_info["_lon"] = round(lon, 5)
            records.append(row_info)

    return records

def aggregate_records(records):
    """Sugrupuoja įrašus pagal unikalias koordinates (vietas)."""
    aggregated = defaultdict(lambda: {"count": 0, "details": [], "address": "Nenurodytas adresas"})
    
    for r in records:
        key = (r["_lat"], r["_lon"])
        aggregated[key]["count"] += 1
        aggregated[key]["details"].append(r)
        
        # Pagrindinis adresas suvestinei imamas iš "CellId1 Address"
        if r["CellId1 Address"] != "Nenurodyta" and r["CellId1 Address"]:
            aggregated[key]["address"] = r["CellId1 Address"]
        elif r["CellId2 Address"] != "Nenurodyta" and r["CellId2 Address"]:
            aggregated[key]["address"] = r["CellId2 Address"]
            
    return aggregated

def make_leaflet_html(aggregated_data, title="Žemėlapis"):
    points = list(aggregated_data.items())
    first = points[0][0] if points else (0, 0)

    markers_js = []
    bounds_points_js = []
    
    for (lat, lon), info in points:
        cnt = info["count"]
        main_addr = info["address"]
        
        # Langas paspaudus ant taško žemėlapyje
        popup_html = f"<div style='min-width:350px; max-height:400px; overflow-y:auto; font-family:sans-serif; font-size:11px; line-height:1.5;'>"
        popup_html += f"<b>Adresas:</b> {main_addr}<br><small><b>Koordinatės:</b> {lat}, {lon}</small><hr style='border:0; border-top:1px solid #ccc; margin: 8px 0;'>"
        
        for idx, det in enumerate(info["details"]):
            popup_html += f"<div style='margin-bottom:12px; padding: 8px; background: #f9f9f9; border-radius: 4px; border-left: 4px solid #0078AA;'>"
            popup_html += f"<b style='color:#0078AA; font-size:12px;'>Sujungimas #{idx+1}</b><br style='margin-bottom:6px;'>"
            
            # Sukame ciklą per stulpelius, kad išvestume TIKTAI juos
            for f in FIELDS:
                val = det.get(f, "Nenurodyta")
                if val and val != "Nenurodyta":
                    popup_html += f"<b>{f}:</b> {val}<br>"
            popup_html += "</div>"
            
        popup_html += f"<div style='margin-top:8px; font-weight:bold; font-size:12px; color:#111;'>Viso sujungimų čia: {cnt}×</div></div>"

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
        show_error("KLAIDA: Failo pirmoje eilutėje nerasti reikalingi stulpelių pavadinimai arba duomenyse nėra koordinačių.")
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
