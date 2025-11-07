#!/usr/bin/env python3
# map_from_txt_leaflet_fileurl_gui_counts.py
# Be API rakto, be lokalaus serverio (file://).
# Agreguoja koordinates ir parodo kiek KARTŲ kiekviena vieta užfiksuota:
# - Ant markerio: „N×“
# - Viršuje kairėje: suvestinė lentelė

import re, tempfile, webbrowser, sys
from pathlib import Path
from collections import defaultdict

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
except Exception:
    tk = None

COORD_RE = re.compile(r"([-+]?\d{1,3}\.\d+)")
PAIR_RE = re.compile(r"([-+]?\d{1,3}\.\d+)\s*[,;\s]\s*([-+]?\d{1,3}\.\d+)")

def parse_coordinates(text: str):
    coords = []
    # 1) tiesioginės poros "lat, lon"
    for m in PAIR_RE.finditer(text):
        lat, lon = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            coords.append((lat, lon))
    # 2) "Latitude" / "Longitude"
    lat_vals = re.findall(r"Latitude[:=\s]*([-+]?\d{1,3}\.\d+)", text, flags=re.IGNORECASE)
    lon_vals = re.findall(r"Longitude[:=\s]*([-+]?\d{1,3}\.\d+)", text, flags=re.IGNORECASE)
    if len(lat_vals) == len(lon_vals) and len(lat_vals) > 0:
        for la, lo in zip(lat_vals, lon_vals):
            la_f, lo_f = float(la), float(lo)
            if -90 <= la_f <= 90 and -180 <= lo_f <= 180:
                coords.append((la_f, lo_f))
    # 3) seka: lat lon lat lon
    if not coords:
        nums = [float(n) for n in COORD_RE.findall(text)]
        for i in range(0, len(nums)-1, 2):
            lat, lon = nums[i], nums[i+1]
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                coords.append((lat, lon))
    return coords

def aggregate_coords(coords, precision=5):
    counts = defaultdict(int)
    for lat, lon in coords:
        key = (round(lat, precision), round(lon, precision))
        counts[key] += 1
    return dict(counts)

def make_leaflet_html(counts_dict, title="Žemėlapis"):
    points = list(counts_dict.items())
    first = points[0][0] if points else (0, 0)

    markers_js = []
    bounds_points_js = []
    for (lat, lon), cnt in points:
        markers_js.append(
            f"""
            (function() {{
                var m = L.marker([{lat}, {lon}]).addTo(map);
                m.bindPopup('{lat}, {lon}<br><b>{cnt}×</b>');
                m.bindTooltip('{cnt}×', {{permanent: true, direction: 'top', className: 'count-tip'}});
            }})();
            """
        )
        bounds_points_js.append(f"[{lat}, {lon}]")

    # ❗️SUKURIAM VIENĄ STRING'Ą PRIEŠ f-STRING
    markers_combined = "\n".join(markers_js)

    if len(points) > 1:
        fit_js = (
            "var bounds = L.latLngBounds([\n                "
            + ", ".join(bounds_points_js)
            + "\n            ]);\n            map.fitBounds(bounds);"
        )
    else:
        fit_js = f"map.setView([{first[0]}, {first[1]}], 12);"

    summary_rows = sorted(points, key=lambda x: x[1], reverse=True)
    summary_html_rows = "\n".join(
        [f"<tr><td>{lat:.5f}, {lon:.5f}</td><td style='text-align:right'>{cnt}×</td></tr>"
         for (lat, lon), cnt in summary_rows]
    )
    total_visits = sum(cnt for _, cnt in points)
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
  background: rgba(255,255,255,.92); padding:10px; border-radius:10px;
  max-height: 60vh; overflow:auto; box-shadow:0 2px 10px rgba(0,0,0,.2);
  font: 14px/1.35 system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
}}
#summary table {{ border-collapse: collapse; }}
#summary th, #summary td {{ padding:4px 8px; border-bottom:1px solid #eee; }}
#summary h3 {{ margin:0 0 6px 0; font-size:16px; }}
#summary .small {{ color:#555; font-size:12px; margin-bottom:6px; }}
</style>
</head>
<body>
<div id="map"></div>

<div id="summary">
  <h3>Suvestinė</h3>
  <div class="small">Unikalių vietų: <b>{unique_places}</b> · Viso apsilankymų: <b>{total_visits}</b></div>
  <table>
    <thead><tr><th>Koordinatės</th><th>Kartai</th></tr></thead>
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
        title="Pasirink .txt failą su koordinatėmis",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
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
    coords = parse_coordinates(text)
    if not coords:
        show_error("Nerasta koordinačių šiame faile.")
        return
    counts = aggregate_coords(coords, precision=5)  # keisk 4/6 jei reikia kitokio sugrupavimo
    html = make_leaflet_html(counts, title=path.name)
    out = Path(tempfile.gettempdir()) / "leaflet_map_counts.html"
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
