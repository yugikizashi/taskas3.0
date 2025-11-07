# 🗺️ map-from-txt-leaflet-counts

**Be API rakto, be lokalaus serverio (file://).** Programa skaito `.txt`, randa `Latitude/Longitude`, **sugrupuoja** vietas ir rodo **kiek kartų** kiekviena vieta užfiksuota:
- ant markerio – pastovus `N×` (pvz., `3×`),
- viršuje kairėje – suvestinė lentelė (unikalios vietos, bendras skaičius, rikiuota mažėjančiai).

## Naudojimas
- Paleisk EXE ir pasirink `.txt`, arba:
  ```bash
  python map_from_txt_leaflet_fileurl_gui_counts.py path/to/koordinates.txt
  ```

## Kaip grupuojama
Pagal suapvalintas koordinates (numatytai **5** skaitmenys po kablelio). Tai leidžia sugrupuoti labai artimus taškus į tą pačią vietą.
Jei nori kitokio tikslumo (pvz., 6 ar 4 skaičiai), pakeisk `precision` programos kode.

## EXE kūrimas (Windows)
```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --name map_from_txt_leaflet_counts map_from_txt_leaflet_fileurl_gui_counts.py
```
Rezultatas: `dist/map_from_txt_leaflet_counts.exe`

## GitHub Actions
`/.github/workflows/build-exe.yml` – automatiškai sukuria `.exe` kaip **Artifacts**.

## Pavyzdinis įvesties failas
Žr. `test_coords.txt`.

## Pastabos
Naudojamas `file://` – veikia su Leaflet CDN ir OSM plytelėmis. Jei naršyklė kažką blokuotų, pabandyk kitą naršyklę (Chrome/Edge/Firefox).
