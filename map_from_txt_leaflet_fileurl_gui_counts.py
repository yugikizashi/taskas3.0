#!/usr/bin/env python3
# map_from_txt_leaflet_fileurl_gui_counts.py
import re
import tempfile
import webbrowser
import sys
import json
from pathlib import Path
from collections import defaultdict
import datetime

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

FIELD_MAPPING_RULES = {
    "Provider Name": ["provider name", "provider n", "provider"],
    "Retain Date": ["retain date", "retain d"],
    "aParty Number": ["aparty number", "aparty nu", "aparty"],
    "bParty Number": ["bparty number", "bparty nu", "bparty"],
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

# Griežtesnis koordinačių regex
COORD_RE = re.compile(r"([-+]?\d{1,3}\.\d{4,8})\s*[,;\s\t]\s*([-+]?\d{1,3}\.\d{4,8})")

# Lietuvos/Europos ribos (filtravimui)
LAT_MIN, LAT_MAX = 53.8, 56.5
LON_MIN, LON_MAX = 20.5, 27.0


def safe_js_string(text: str) -> str:
    if not text:
        return ""
    return str(text).replace("\\", "/").replace("'", "").replace('"', "").strip()


def find_column_index(header_parts, targets):
    for target in targets:
        t_clean = target.lower().strip()
        for idx, part in enumerate(header_parts):
            p_clean = part.lower().strip()
            if p_clean == t_clean or p_clean.startswith(t_clean[:7]):
                return idx
    return None


def parse_retain_date(date_str: str):
    if not date_str or date_str == "Nenurodyta":
        return None
    date_str = date_str.strip()
    formats = [
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M", "%d-%m-%Y %H:%M:%S", "%Y/%m/%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S", "%Y.%m.%d %H:%M:%S"
    ]
    for fmt in formats:
        try:
            return datetime.datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def is_valid_coordinate(lat: float, lon: float) -> bool:
    """Tikrina ar koordinatės yra realistiškos Lietuvai/Europai"""
    return (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX) or \
           (-90 <= lat <= 90 and -180 <= lon <= 180)


def parse_file_to_records(text: str):
    records = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return records

    header_idx = -1
    delimiter = "\t"
    field_map = {}

    for idx, line in enumerate(lines):
        current_delim = "\t" if "\t" in line else (";" if ";" in line else ",")
        parts = [p.strip().lower() for p in line.split(current_delim)]

        found_count = 0
        temp_map = {}
        for field_key, aliases in FIELD_MAPPING_RULES.items():
            col_idx = find_column_index(parts, aliases)
            if col_idx is not None:
                temp_map[field_key] = col_idx
                found_count += 1

        if found_count >= 3:
            header_idx = idx
            delimiter = current_delim
            field_map = temp_map
            break

    if header_idx == -1:
        return records

    for line in lines[header_idx + 1:]:
        parts = [p.strip() for p in line.split(delimiter)]
        if len(parts) < 2:
            continue

        row_info = {f: "Nenurodyta" for f in DISPLAY_FIELDS}

        for field_key, col_idx in field_map.items():
            if col_idx < len(parts) and parts[col_idx]:
                row_info[field_key] = safe_js_string(parts[col_idx])

        # Datos apdorojimas
        retain_date_str = row_info.get("Retain Date", "Nenurodyta")
        dt = parse_retain_date(retain_date_str)
        if dt:
            row_info["_datetime"] = dt
            row_info["Retain Date"] = dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            row_info["_datetime"] = None

        # === Koordinačių paieška (patobulinta) ===
        lat, lon = None, None

        # Pirmenybė CellId1
        try:
            l1 = row_info.get("CellId1 Latitude", "")
            o1 = row_info.get("CellId1 Longitude", "")
            if l1 and o1 and l1 != "Nenurodyta" and o1 != "Nenurodyta":
                lat = float(l1.replace(",", "."))
                lon = float(o1.replace(",", "."))
        except ValueError:
            pass

        # Jei CellId1 netinkamos — CellId2
        if lat is None or lon is None or not is_valid_coordinate(lat, lon):
            try:
                l2 = row_info.get("CellId2 Latitude", "")
                o2 = row_info.get("CellId2 Longitude", "")
                if l2 and o2 and l2 != "Nenurodyta" and o2 != "Nenurodyta":
                    lat = float(l2.replace(",", "."))
                    lon = float(o2.replace(",", "."))
            except ValueError:
                pass

        # Jei vis dar nėra — ieškome tekste (regex)
        if lat is None or lon is None or not is_valid_coordinate(lat, lon):
            match = COORD_RE.search(line)
            if match:
                try:
                    lat = float(match.group(1).replace(",", "."))
                    lon = float(match.group(2).replace(",", "."))
                except ValueError:
                    pass

        if lat is None or lon is None or not is_valid_coordinate(lat, lon):
            continue

        # Galutinis patikrinimas
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue

        row_info["_lat"] = round(lat, 6)
        row_info["_lon"] = round(lon, 6)

        # === Adreso tvarkymas (tikslus iš failo) ===
        addr1 = row_info.get("CellId1 Address", "Nenurodyta")
        addr2 = row_info.get("CellId2 Address", "Nenurodyta")

        if addr1 and addr1 != "Nenurodyta" and len(addr1) > 5:
            row_info["_address"] = addr1
        elif addr2 and addr2 != "Nenurodyta" and len(addr2) > 5:
            row_info["_address"] = addr2
        else:
            row_info["_address"] = "Adresas nenurodytas"

        records.append(row_info)

    return records


def aggregate_records(records):
    aggregated = defaultdict(lambda: {
        "count": 0,
        "details": [],
        "address": "Adresas nenurodytas",
        "first_date": None,
        "last_date": None
    })

    for r in records:
        key = (r["_lat"], r["_lon"])
        aggregated[key]["count"] += 1
        aggregated[key]["details"].append(r)

        # Naudojame tikslų adresą iš _address
        if r["_address"] and r["_address"] != "Adresas nenurodytas":
            aggregated[key]["address"] = r["_address"]

        # Datų intervalas
        dt = r.get("_datetime")
        if dt:
            if not aggregated[key]["first_date"] or dt < aggregated[key]["first_date"]:
                aggregated[key]["first_date"] = dt
            if not aggregated[key]["last_date"] or dt > aggregated[key]["last_date"]:
                aggregated[key]["last_date"] = dt

    # Chronologinis rūšiavimas
    for key in aggregated:
        aggregated[key]["details"].sort(key=lambda x: x.get("_datetime") or datetime.datetime.min)

    return aggregated


def make_leaflet_html(aggregated_data, title="Žemėlapis"):
    points = list(aggregated_data.items())
    if not points:
        return "<h2>Nerasta jokių įrašų su koordinatėmis</h2>"

    first = points[0][0]
    markers_js = []
    bounds_points_js = []

    for (lat, lon), info in points:
        cnt = info["count"]
        main_addr = info["address"]

        first_dt = info.get("first_date")
        last_dt = info.get("last_date")
        date_range = ""
        if first_dt and last_dt:
            if first_dt.date() == last_dt.date():
                date_range = f"{first_dt.strftime('%Y-%m-%d %H:%M')} – {last_dt.strftime('%H:%M')}"
            else:
                date_range = f"{first_dt.strftime('%Y-%m-%d')} – {last_dt.strftime('%Y-%m-%d')}"

        popup_html = f"<div style='min-width:390px; max-height:500px; overflow-y:auto; font-family:sans-serif; font-size:11.2px; line-height:1.45;'>"
        popup_html += f"<b>Adresas:</b> {main_addr}<br>"
        popup_html += f"<b>Koordinatės:</b> {lat:.6f}, {lon:.6f}<br>"
        if date_range:
            popup_html += f"<b>Laikotarpis:</b> {date_range}<br>"
        popup_html += "<hr style='border:0; border-top:1px solid #ccc; margin: 8px 0;'>"

        for idx, det in enumerate(info["details"]):
            dt = det.get("_datetime")
            time_str = dt.strftime("%H:%M:%S") if dt else ""
            popup_html += f"<div style='margin-bottom:12px; padding: 9px; background: #f9f9f9; border-radius: 5px; border-left: 4px solid #0078AA;'>"
            popup_html += f"<b style='color:#0078AA;'>Sujungimas #{idx+1}</b> <small>{time_str}</small><br>"
            for f in DISPLAY_FIELDS:
                if f == "Retain Date":
                    continue
                val = det.get(f, "Nenurodyta")
                if val and val != "Nenurodyta":
                    popup_html += f"<b>{f}:</b> {val}<br>"
            popup_html += "</div>"

        popup_html += f"<div style='margin-top:10px; font-weight:bold; color:#111;'>Iš viso: <b>{cnt}×</b></div></div>"

        safe_popup = json.dumps(popup_html)
        markers_js.append(f"""
            (function() {{
                var m = L.marker([{lat}, {lon}]).addTo(map);
                m.bindPopup({safe_popup}, {{maxWidth: 410}});
                m.bindTooltip('{cnt}×', {{permanent: true, direction: 'top', className: 'count-tip'}});
            }})();
        """)
        bounds_points_js.append(f"[{lat}, {lon}]")

    markers_combined = "\n".join(markers_js)
    fit_js = "var bounds = L.latLngBounds([\n" + ", ".join(bounds_points_js) + "\n]);\nmap.fitBounds(bounds);" if len(points) > 1 else f"map.setView([{first[0]}, {first[1]}], 14);"

    # Suvestinė
    summary_rows = sorted(points, key=lambda x: x[1]["count"], reverse=True)
    summary_html_rows = ""
    for (lat, lon), info in summary_rows:
        addr = info["address"]
        short_addr = addr[:35] + "..." if len(addr) > 35 else addr
        summary_html_rows += f"""
        <tr>
            <td style='word-wrap:break-word;'><span title='{addr}'>{short_addr}</span></td>
            <td style='color:#555; font-size:11px; white-space:nowrap;'>{lat:.5f},<br>{lon:.5f}</td>
            <td style='text-align:right; font-weight:bold; color:#0078AA;'>{info['count']}×</td>
        </tr>
        """

    total = sum(info["count"] for _, info in points)
    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
html,body,#map {{height:100%;margin:0;padding:0}}
#map {{height:100vh}}
.count-tip {{background:#111;color:#fff;border:none;border-radius:6px;padding:2px 7px;font-weight:bold;}}
#summary {{position:absolute; top:10px; left:10px; z-index:1000; background:rgba(255,255,255,.97); padding:12px; border-radius:10px;
           max-height:80vh; overflow-y:auto; box-shadow:0 4px 15px rgba(0,0,0,.15); width:370px; font:12px/1.45 system-ui;}}
</style>
</head>
<body>
<div id="map"></div>
<div id="summary">
  <h3>Suvestinė</h3>
  <div style="color:#666;font-size:11px;margin-bottom:8px;">Vietų: <b>{len(points)}</b> • Sujungimų: <b>{total}</b></div>
  <table style="width:100%; border-collapse:collapse;">
    <thead><tr><th>Adresas</th><th>Koordinatės</th><th style="text-align:right">Sujung.</th></tr></thead>
    <tbody>{summary_html_rows}</tbody>
  </table>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
var map = L.map('map');
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{maxZoom:19, attribution:'© OpenStreetMap'}}).addTo(map);
{markers_combined}
{fit_js}
</script>
</body>
</html>
"""
    return html


# === Žemiau likusi dalis be pakeitimų (dialogai, klaidos ir t.t.) ===
def choose_file_dialog():
    if tk is None: return None
    root = tk.Tk(); root.withdraw()
    path = filedialog.askopenfilename(title="Pasirink failą", filetypes=[("Tekstiniai failai", "*.txt *.csv *.tsv"), ("All", "*.*")])
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
        show_error("Nepavyko rasti jokių įrašų su koordinatėmis.\nPatikrinkite, ar faile yra CellId1/CellId2 Latitude/Longitude.")
        return

    aggregated = aggregate_records(records)
    html = make_leaflet_html(aggregated, title=path.name)

    out = Path(tempfile.gettempdir()) / "leaflet_map_fixed.html"
    out.write_text(html, encoding='utf-8')
    webbrowser.open(out.as_uri())


if __name__ == '__main__':
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
        if not p.exists():
            show_error(f"Failas nerastas: {p}")
            sys.exit(1)
        process_file(p)
    else:
        chosen = choose_file_dialog()
        if chosen:
            process_file(Path(chosen))
        else:
            show_error("Failas nepasirinktas.")
