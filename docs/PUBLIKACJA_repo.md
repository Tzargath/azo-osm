# Publikacja w publicznym repozytorium + dystrybucja wtyczki

Stan przygotowania (✅ zrobione automatycznie):
- `.gitignore` wyklucza `data/` (519 MB), `data3857/` (23 MB), `__pycache__/`, `*.pyc`, paczki `*.zip` — repo będzie lekkie i odtwarzalne.
- Skan sekretów: **czysto** (zero tokenów/kluczy/haseł poza `data/`).
- `metadata.txt`: autor **Tomasz Zuchlke**, email `tomasz.zuchlke@ultraflow.run`, wersja **1.6.1**.
- `LICENSE` (MIT, © 2026 Tomasz Zuchlke) i `README.md` na miejscu.
- Skrypt `build_plugin_zip.sh` buduje paczkę wtyczki gotową do instalacji/Release.

---

## 1. Co trafia do repo, a co NIE

**TAK** (kod + dokumentacja, ~kilka MB):
- `qgis_plugin/azo_izochrony/` — wtyczka (źródła),
- `01_fetch_osm.py`, `02_isochrones.py`, `03_run_buffers.sh`, `04_build_map.py` — pipeline odtwarzający dane,
- `docs/`, `README.md`, `LICENSE`, `.gitignore`,
- opcjonalnie `figury_art/` (2,4 MB) — ryciny do artykułu.

**NIE** (duże/odtwarzalne/robocze — już w `.gitignore`):
- `data/`, `data3857/` — warstwy GPKG/OSM (odtwarzalne z `01_fetch_osm.py`),
- `*.osm`, `*.log`, `*.DONE`, `__pycache__/`, `*.zip`, `.DS_Store`.

> Uwaga: **nie commituj realnych warstw JRG/OSP-KSRG z KW PSP** — to dane służbowe. Repo zawiera tylko pipeline OSM (demonstracyjny) i kod. Jeśli `figury/` (23 MB) nie są potrzebne publicznie, dopisz `figury/` do `.gitignore`.

---

## 2. Inicjalizacja repo i pierwszy push

Repozytorium docelowe (z `metadata.txt`): **https://github.com/Tzargath/azo-osm**

```bash
cd ~/azo_gzm
git init -b main
git add .
git status            # ZWERYFIKUJ: czy nie wchodzi data/ ani nic wrażliwego
git commit -m "AZO: pipeline OSM + wtyczka QGIS Izochrony AZO (PSP) v1.6.1"

# utwórz repo na GitHub (jednorazowo) i podłącz:
gh repo create Tzargath/azo-osm --public --source=. --remote=origin --push
#   ALBO ręcznie, gdy repo już istnieje:
# git remote add origin https://github.com/Tzargath/azo-osm.git
# git push -u origin main
```

Sanity-check przed pushem: `git ls-files | grep -E '^data/|\.osm$' ` musi być **puste**.

---

## 3. Dystrybucja samej wtyczki (dla strażaków/QGIS)

### A. Szybko: ZIP + GitHub Release
```bash
./build_plugin_zip.sh                       # → azo_izochrony-1.6.1.zip
gh release create v1.6.1 azo_izochrony-1.6.1.zip -t "Izochrony AZO v1.6.1 (QGIS 4 / Qt6)" \
   -n "Kompatybilność z QGIS 4 / Qt6 (qgisMaximumVersion=4.99, supportsQt6) — bez zmian funkcjonalnych względem 1.6.0."
```
Użytkownik instaluje w QGIS: **Wtyczki → Zarządzaj i instaluj → Zainstaluj z ZIP**.

### B. Oficjalnie: repozytorium wtyczek QGIS (plugins.qgis.org)
Zasięg: widoczna dla wszystkich w Menedżerze wtyczek QGIS.
1. Konto na https://plugins.qgis.org (OSGEO ID).
2. Wymogi metadanych (✅ mamy): `name, qgisMinimumVersion, description, version, author, email, about, repository`. Dodaj `experimental=False` (jest).
3. **Upload** `azo_izochrony-1.6.1.zip` → „Share a plugin". Po zatwierdzeniu aktualizacje idą przez kolejne uploady ZIP z podbitą wersją.

---

## 4. Wydanie aktualizacji (za każdym razem)
1. Podbij `version=` w `qgis_plugin/azo_izochrony/metadata.txt` + dopisek w `changelog=`.
2. `./build_plugin_zip.sh`
3. `git commit -am "v1.x.y — opis"; git push`
4. `gh release create vX.Y.Z azo_izochrony-X.Y.Z.zip` (i/lub upload na plugins.qgis.org).

---

## 5. Checklist przed upublicznieniem
- [ ] `git status` / `git ls-files` — brak `data/`, `*.osm`, danych służbowych KW PSP.
- [ ] `LICENSE` i autor zgodne (Tomasz Zuchlke).
- [ ] README opisuje: cel, instalację, dane wejściowe, ograniczenia („materiał poglądowy; do celów urzędowych: BDOT10k + dane KW/KP PSP").
- [ ] ZIP instaluje się czysto na świeżym profilu QGIS.
