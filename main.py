"""
Telefono išklotinės analizatorius
CDR Analyzer - Bitė / LT operatoriai
Duomenys apdorojami lokaliai, niekas neišsiunčiama.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkintermapview
import pandas as pd
import threading
import os
import sys
from datetime import datetime
from collections import defaultdict
import webbrowser

# ── Spalvos ──────────────────────────────────────────────────────────────────
BG       = "#0f1117"
SURFACE  = "#1a1d27"
CARD     = "#22263a"
ACCENT   = "#4f8ef7"
ACCENT2  = "#e05c5c"
ACCENT3  = "#4fd1a5"
TEXT     = "#e8eaf0"
MUTED    = "#7a7f9a"
BORDER   = "#2e3250"

SERVICE_COLORS = {
    "outCall": "#4f8ef7",
    "inCall":  "#4fd1a5",
    "outSMS":  "#f7c74f",
    "inSMS":   "#b07af7",
    "data":    "#7a7f9a",
}

# ── Žymeklių spalvos žemėlapyje ──────────────────────────────────────────────
MARKER_COLORS = {
    "outCall": "blue",
    "inCall":  "green",
    "outSMS":  "orange",
    "inSMS":   "purple",
    "data":    "gray",
}


def parse_cdr(filepath):
    """Nuskaito Bitė formato TSV failą, grąžina DataFrame."""
    # Rask eilutę su antrašte
    header_line = None
    with open(filepath, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        if line.startswith("Provider Name"):
            header_line = i
            break

    if header_line is None:
        raise ValueError("Nepavyko rasti duomenų antraštės eilutės.")

    df = pd.read_csv(
        filepath,
        sep="\t",
        skiprows=header_line,
        encoding="utf-8",
        on_bad_lines="skip",
    )

    # Normalizuok stulpelių vardus
    df.columns = df.columns.str.strip()

    # Stulpelių mapingas (atsparus skirtingiems pavadinimams)
    rename = {}
    for c in df.columns:
        cl = c.lower().replace(" ", "").replace("\t", "")
        if cl == "retaindate":            rename[c] = "datetime"
        elif cl == "aparty" or cl == "apartnumber": rename[c] = "aParty"
        elif cl == "bparty" or cl == "bpartynumber": rename[c] = "bParty"
        elif cl == "duration":            rename[c] = "duration"
        elif cl == "service":             rename[c] = "service"
        elif cl == "servicetype":         rename[c] = "serviceType"
        elif cl == "cellid1address":      rename[c] = "addr1"
        elif cl == "cellid2address":      rename[c] = "addr2"
        elif "cellid1lat" in cl:          rename[c] = "lat1"
        elif "llid1lon" in cl or "cellid1lon" in cl: rename[c] = "lon1"
        elif "cellid2lat" in cl:         rename[c] = "lat2"
        elif "cellid2lon" in cl:         rename[c] = "lon2"
    df = df.rename(columns=rename)

    # Priversk skaitinius stulpelius
    for col in ["lat1","lon1","lat2","lon2","duration"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Suformuok serviceType stulpelį
    if "serviceType" not in df.columns and "service" in df.columns:
        df["serviceType"] = df["service"]
    elif "serviceType" not in df.columns:
        df["serviceType"] = "unknown"

    # Konvertuok datą
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")

    return df


class CDRApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("📡 CDR Analizatorius  |  Bitė išklotinė")
        self.configure(bg=BG)
        self.geometry("1280x800")
        self.minsize(900, 600)

        self.df_full = None      # visi duomenys
        self.df_filtered = None  # filtruoti
        self.markers = []

        self._build_ui()

    # ── UI kūrimas ────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ─ Viršutinė juosta ─
        topbar = tk.Frame(self, bg=SURFACE, height=56)
        topbar.pack(fill="x", side="top")
        topbar.pack_propagate(False)

        tk.Label(topbar, text="📡", font=("Segoe UI", 20), bg=SURFACE, fg=ACCENT
                 ).pack(side="left", padx=(16,4), pady=8)
        tk.Label(topbar, text="CDR Analizatorius", font=("Segoe UI", 15, "bold"),
                 bg=SURFACE, fg=TEXT).pack(side="left", pady=8)
        tk.Label(topbar, text="• duomenys apdorojami lokaliai",
                 font=("Segoe UI", 9), bg=SURFACE, fg=MUTED).pack(side="left", padx=12, pady=8)

        self.btn_open = tk.Button(
            topbar, text="📂  Atidaryti .txt failą",
            font=("Segoe UI", 10, "bold"),
            bg=ACCENT, fg="white", relief="flat", cursor="hand2",
            activebackground="#3a6fd4", activeforeground="white",
            padx=16, pady=6,
            command=self._open_file
        )
        self.btn_open.pack(side="right", padx=16, pady=10)

        # ─ Pagrindinis turinys ─
        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True)

        # Kairė šoninė juosta
        sidebar = tk.Frame(main, bg=SURFACE, width=300)
        sidebar.pack(fill="y", side="left")
        sidebar.pack_propagate(False)

        self._build_sidebar(sidebar)

        # Dešinė dalis – kortelės + žemėlapis
        right = tk.Frame(main, bg=BG)
        right.pack(fill="both", expand=True)

        self._build_stats_bar(right)
        self._build_map_and_table(right)

        # Statusas
        self.status_var = tk.StringVar(value="Pasirinkite .txt failą viršuje →")
        tk.Label(self, textvariable=self.status_var,
                 font=("Segoe UI", 9), bg=SURFACE, fg=MUTED,
                 anchor="w", padx=12
                 ).pack(fill="x", side="bottom", ipady=4)

    def _build_sidebar(self, parent):
        tk.Label(parent, text="FILTRAI", font=("Segoe UI", 9, "bold"),
                 bg=SURFACE, fg=MUTED, anchor="w"
                 ).pack(fill="x", padx=16, pady=(18,4))

        # Paslaugos
        tk.Label(parent, text="Paslaugos tipas", font=("Segoe UI", 10),
                 bg=SURFACE, fg=TEXT, anchor="w").pack(fill="x", padx=16, pady=(8,2))

        self.svc_vars = {}
        svc_frame = tk.Frame(parent, bg=SURFACE)
        svc_frame.pack(fill="x", padx=16)
        services = [("outCall","📞 Išeinantys skambučiai"),
                    ("inCall", "📲 Įeinantys skambučiai"),
                    ("outSMS","✉️  Išeinančios SMS"),
                    ("inSMS", "📨 Įeinančios SMS"),
                    ("data",  "🌐 Duomenys")]
        for key, label in services:
            var = tk.BooleanVar(value=True)
            self.svc_vars[key] = var
            cb = tk.Checkbutton(svc_frame, text=label, variable=var,
                                bg=SURFACE, fg=TEXT, selectcolor=CARD,
                                activebackground=SURFACE, activeforeground=TEXT,
                                font=("Segoe UI", 9), anchor="w",
                                command=self._apply_filters)
            cb.pack(fill="x", pady=1)

        # Numerio filtras
        tk.Label(parent, text="Filtruoti numerį (aParty/bParty)",
                 font=("Segoe UI", 10), bg=SURFACE, fg=TEXT, anchor="w"
                 ).pack(fill="x", padx=16, pady=(16,2))
        self.num_var = tk.StringVar()
        self.num_var.trace_add("write", lambda *_: self._apply_filters())
        num_entry = tk.Entry(parent, textvariable=self.num_var,
                             bg=CARD, fg=TEXT, insertbackground=TEXT,
                             relief="flat", font=("Segoe UI", 10))
        num_entry.pack(fill="x", padx=16, ipady=6)

        # Datos filtras
        tk.Label(parent, text="Data nuo", font=("Segoe UI", 10),
                 bg=SURFACE, fg=TEXT, anchor="w").pack(fill="x", padx=16, pady=(12,2))
        self.date_from = tk.Entry(parent, bg=CARD, fg=TEXT,
                                  insertbackground=TEXT, relief="flat",
                                  font=("Segoe UI", 10))
        self.date_from.pack(fill="x", padx=16, ipady=6)
        self.date_from.insert(0, "")

        tk.Label(parent, text="Data iki", font=("Segoe UI", 10),
                 bg=SURFACE, fg=TEXT, anchor="w").pack(fill="x", padx=16, pady=(8,2))
        self.date_to = tk.Entry(parent, bg=CARD, fg=TEXT,
                                insertbackground=TEXT, relief="flat",
                                font=("Segoe UI", 10))
        self.date_to.pack(fill="x", padx=16, ipady=6)

        btn_date = tk.Button(parent, text="Taikyti datos filtrą",
                             bg=CARD, fg=ACCENT, relief="flat",
                             font=("Segoe UI", 9), cursor="hand2",
                             command=self._apply_filters)
        btn_date.pack(fill="x", padx=16, pady=(8,0), ipady=6)

        # Reset
        tk.Button(parent, text="↺  Išvalyti visus filtrus",
                  bg=CARD, fg=MUTED, relief="flat",
                  font=("Segoe UI", 9), cursor="hand2",
                  command=self._reset_filters
                  ).pack(fill="x", padx=16, pady=(8,0), ipady=6)

        # Legenda
        tk.Label(parent, text="LEGENDA", font=("Segoe UI", 9, "bold"),
                 bg=SURFACE, fg=MUTED, anchor="w"
                 ).pack(fill="x", padx=16, pady=(24,4))
        for key, label in services:
            color = SERVICE_COLORS.get(key, MUTED)
            row = tk.Frame(parent, bg=SURFACE)
            row.pack(fill="x", padx=16, pady=1)
            tk.Label(row, text="●", fg=color, bg=SURFACE,
                     font=("Segoe UI", 12)).pack(side="left")
            tk.Label(row, text=label, fg=TEXT, bg=SURFACE,
                     font=("Segoe UI", 9)).pack(side="left", padx=4)

    def _build_stats_bar(self, parent):
        self.stats_frame = tk.Frame(parent, bg=BG)
        self.stats_frame.pack(fill="x", padx=12, pady=(12,4))

        self.stat_cards = {}
        labels = [("Visi", "total"), ("Skambučiai", "calls"),
                  ("SMS", "sms"), ("Duomenys", "data"),
                  ("Unikalūs nr.", "unique")]
        for title, key in labels:
            card = tk.Frame(self.stats_frame, bg=CARD, padx=14, pady=8)
            card.pack(side="left", padx=4, fill="y")
            tk.Label(card, text=title, font=("Segoe UI", 8),
                     bg=CARD, fg=MUTED).pack()
            val = tk.Label(card, text="—", font=("Segoe UI", 18, "bold"),
                           bg=CARD, fg=ACCENT)
            val.pack()
            self.stat_cards[key] = val

    def _build_map_and_table(self, parent):
        paned = tk.PanedWindow(parent, orient="vertical",
                               bg=BG, sashwidth=6, sashrelief="flat")
        paned.pack(fill="both", expand=True, padx=12, pady=(0,4))

        # Žemėlapis
        map_frame = tk.Frame(paned, bg=CARD)
        self.map_widget = tkintermapview.TkinterMapView(
            map_frame, corner_radius=0)
        self.map_widget.pack(fill="both", expand=True)
        self.map_widget.set_position(55.17, 23.88)
        self.map_widget.set_zoom(7)
        # OpenStreetMap – nemokamas, lokalus
        self.map_widget.set_tile_server(
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
        paned.add(map_frame, minsize=260)

        # Lentelė
        table_frame = tk.Frame(paned, bg=CARD)
        paned.add(table_frame, minsize=140)

        cols = ("datetime","aParty","bParty","serviceType","duration","addr1")
        col_labels = ("Data / laikas","Skambinantis","Skambinamasis",
                      "Tipas","Trukmė (s)","Vieta")
        self.tree = ttk.Treeview(table_frame, columns=cols,
                                 show="headings", height=8)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview",
                        background=CARD, foreground=TEXT,
                        fieldbackground=CARD, rowheight=24,
                        font=("Segoe UI", 9))
        style.configure("Treeview.Heading",
                        background=SURFACE, foreground=MUTED,
                        font=("Segoe UI", 9, "bold"), relief="flat")
        style.map("Treeview", background=[("selected", ACCENT)])

        for col, lbl in zip(cols, col_labels):
            self.tree.heading(col, text=lbl,
                              command=lambda c=col: self._sort_tree(c))
            self.tree.column(col, width=140, anchor="w")

        vsb = ttk.Scrollbar(table_frame, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_row_select)

        # Lentelės spalvos pagal tipą
        for svc, color in SERVICE_COLORS.items():
            self.tree.tag_configure(svc, foreground=color)

    # ── Failo atidarymas ──────────────────────────────────────────────────────

    def _open_file(self):
        path = filedialog.askopenfilename(
            title="Pasirinkite išklotinės .txt failą",
            filetypes=[("Tekstiniai failai","*.txt"),("Visi failai","*.*")])
        if not path:
            return
        self.status_var.set(f"Kraunama: {os.path.basename(path)} …")
        self.update()
        threading.Thread(target=self._load_file, args=(path,), daemon=True).start()

    def _load_file(self, path):
        try:
            df = parse_cdr(path)
            self.df_full = df
            self.after(0, self._on_loaded)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Klaida", str(e)))
            self.after(0, lambda: self.status_var.set("Klaida įkeliant failą."))

    def _on_loaded(self):
        # Nustatyk datos filtro laukus
        if "datetime" in self.df_full.columns:
            mn = self.df_full["datetime"].min()
            mx = self.df_full["datetime"].max()
            self.date_from.delete(0, "end")
            self.date_from.insert(0, mn.strftime("%Y-%m-%d") if pd.notna(mn) else "")
            self.date_to.delete(0, "end")
            self.date_to.insert(0, mx.strftime("%Y-%m-%d") if pd.notna(mx) else "")

        self._apply_filters()
        self.status_var.set(
            f"Įkelta: {len(self.df_full)} įrašų  •  duomenys apdorojami lokaliai")

    # ── Filtrai ───────────────────────────────────────────────────────────────

    def _apply_filters(self):
        if self.df_full is None:
            return
        df = self.df_full.copy()

        # Paslaugos
        active = [k for k, v in self.svc_vars.items() if v.get()]
        if active:
            df = df[df["serviceType"].isin(active)]

        # Numeris
        num = self.num_var.get().strip()
        if num:
            mask = (df.get("aParty", pd.Series()).astype(str).str.contains(num, na=False) |
                    df.get("bParty", pd.Series()).astype(str).str.contains(num, na=False))
            df = df[mask]

        # Datos
        if "datetime" in df.columns:
            df_val = self.date_from.get().strip()
            dt_val = self.date_to.get().strip()
            try:
                if df_val:
                    df = df[df["datetime"] >= pd.to_datetime(df_val)]
                if dt_val:
                    df = df[df["datetime"] <= pd.to_datetime(dt_val) + pd.Timedelta(days=1)]
            except Exception:
                pass

        self.df_filtered = df
        self._refresh_stats()
        self._refresh_table()
        self._refresh_map()

    def _reset_filters(self):
        for v in self.svc_vars.values():
            v.set(True)
        self.num_var.set("")
        if self.df_full is not None and "datetime" in self.df_full.columns:
            mn = self.df_full["datetime"].min()
            mx = self.df_full["datetime"].max()
            self.date_from.delete(0,"end")
            self.date_from.insert(0, mn.strftime("%Y-%m-%d") if pd.notna(mn) else "")
            self.date_to.delete(0,"end")
            self.date_to.insert(0, mx.strftime("%Y-%m-%d") if pd.notna(mx) else "")
        self._apply_filters()

    # ── Statistika ────────────────────────────────────────────────────────────

    def _refresh_stats(self):
        df = self.df_filtered
        if df is None or df.empty:
            for v in self.stat_cards.values():
                v.config(text="0")
            return
        svc = df["serviceType"]
        calls = svc.isin(["inCall","outCall"]).sum()
        sms   = svc.isin(["inSMS","outSMS"]).sum()
        data  = (svc == "data").sum()
        nums  = set()
        for col in ["aParty","bParty"]:
            if col in df.columns:
                nums.update(df[col].dropna().astype(str).unique())
        self.stat_cards["total"].config(text=f"{len(df):,}")
        self.stat_cards["calls"].config(text=f"{calls:,}")
        self.stat_cards["sms"].config(text=f"{sms:,}")
        self.stat_cards["data"].config(text=f"{data:,}")
        self.stat_cards["unique"].config(text=f"{len(nums):,}")

    # ── Lentelė ───────────────────────────────────────────────────────────────

    def _refresh_table(self):
        self.tree.delete(*self.tree.get_children())
        if self.df_filtered is None or self.df_filtered.empty:
            return
        df = self.df_filtered.head(2000)  # Rodyti iki 2000 eilučių
        for _, row in df.iterrows():
            dt  = str(row.get("datetime",""))[:19]
            aP  = str(row.get("aParty",""))
            bP  = str(row.get("bParty",""))
            svc = str(row.get("serviceType",""))
            dur = str(int(row.get("duration",0)) if pd.notna(row.get("duration")) else "")
            adr = str(row.get("addr1",""))
            tag = svc if svc in SERVICE_COLORS else ""
            self.tree.insert("","end", values=(dt,aP,bP,svc,dur,adr), tags=(tag,))

    def _sort_tree(self, col):
        if self.df_filtered is None:
            return
        ascending = True
        if hasattr(self, "_last_sort") and self._last_sort == col:
            ascending = not getattr(self,"_sort_asc", True)
        self._last_sort = col
        self._sort_asc = ascending
        if col in self.df_filtered.columns:
            self.df_filtered = self.df_filtered.sort_values(
                col, ascending=ascending, na_position="last")
            self._refresh_table()

    def _on_row_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0])["values"]
        # Rask eilutę pagal datą ir numerį
        if self.df_filtered is None:
            return
        dt_str = str(vals[0])
        mask = self.df_filtered.apply(
            lambda r: str(r.get("datetime",""))[:19] == dt_str, axis=1)
        rows = self.df_filtered[mask]
        if rows.empty:
            return
        row = rows.iloc[0]
        lat = row.get("lat1")
        lon = row.get("lon1")
        if pd.notna(lat) and pd.notna(lon):
            self.map_widget.set_position(lat, lon)
            self.map_widget.set_zoom(15)

    # ── Žemėlapis ─────────────────────────────────────────────────────────────

    def _refresh_map(self):
        # Išvalyti senus žymeklius
        for m in self.markers:
            try:
                m.delete()
            except Exception:
                pass
        self.markers.clear()

        if self.df_filtered is None or self.df_filtered.empty:
            return

        df = self.df_filtered

        # Surinkti unikalias vietas su statistika
        loc_stats = defaultdict(lambda: defaultdict(int))

        for _, row in df.iterrows():
            svc = str(row.get("serviceType","unknown"))
            for lat_col, lon_col, addr_col in [
                ("lat1","lon1","addr1"), ("lat2","lon2","addr2")]:
                lat = row.get(lat_col)
                lon = row.get(lon_col)
                if pd.notna(lat) and pd.notna(lon) and lat != 0 and lon != 0:
                    key = (round(float(lat),5), round(float(lon),5))
                    loc_stats[key][svc] += 1
                    if "addr" not in loc_stats[key]:
                        loc_stats[key]["addr"] = str(row.get(addr_col,""))

        # Padėk žymeklius (maks 500 vietų)
        for (lat, lon), stats in list(loc_stats.items())[:500]:
            total = sum(v for k,v in stats.items() if k != "addr")
            addr  = stats.get("addr","")
            # Dominuojantis tipas
            svc_counts = {k:v for k,v in stats.items() if k not in ("addr",)}
            dominant = max(svc_counts, key=svc_counts.get) if svc_counts else "data"
            color = MARKER_COLORS.get(dominant, "gray")

            tip  = f"{addr}\n"
            tip += "\n".join(f"{k}: {v}" for k,v in svc_counts.items())
            tip += f"\nViso: {total}"

            m = self.map_widget.set_marker(
                lat, lon,
                text=f"{total}" if total > 1 else "",
                marker_color_circle=color,
                marker_color_outside=color,
                command=lambda marker, t=tip: self._show_marker_info(t)
            )
            self.markers.append(m)

        # Centruok žemėlapį
        lats = [k[0] for k in loc_stats.keys()]
        lons = [k[1] for k in loc_stats.keys()]
        if lats:
            clat = sum(lats)/len(lats)
            clon = sum(lons)/len(lons)
            self.map_widget.set_position(clat, clon)
            if len(loc_stats) == 1:
                self.map_widget.set_zoom(14)
            else:
                self.map_widget.set_zoom(11)

        self.status_var.set(
            f"Rodoma: {len(self.df_filtered):,} įrašų  •  "
            f"{len(loc_stats)} unikalių vietų žemėlapyje  •  "
            f"duomenys apdorojami lokaliai")

    def _show_marker_info(self, text):
        win = tk.Toplevel(self)
        win.title("Vietos informacija")
        win.configure(bg=CARD)
        win.geometry("340x200")
        tk.Label(win, text=text, bg=CARD, fg=TEXT,
                 font=("Segoe UI", 10), justify="left",
                 padx=16, pady=16, wraplength=310).pack(fill="both", expand=True)
        tk.Button(win, text="Uždaryti", command=win.destroy,
                  bg=ACCENT, fg="white", relief="flat",
                  font=("Segoe UI", 10), padx=12, pady=6).pack(pady=(0,12))


def main():
    app = CDRApp()
    app.mainloop()


if __name__ == "__main__":
    main()
