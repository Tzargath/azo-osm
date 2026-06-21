#!/usr/bin/env bash
# Pakuje wtyczkę QGIS „Izochrony AZO (PSP)" do ZIP gotowego do:
#   • instalacji w QGIS (Wtyczki → Zainstaluj z ZIP),
#   • wgrania jako Release na GitHub,
#   • zgłoszenia do oficjalnego repozytorium wtyczek QGIS (plugins.qgis.org).
# Struktura ZIP wymagana przez QGIS: pojedynczy katalog `azo_izochrony/` z metadata.txt w środku.
set -euo pipefail
cd "$(dirname "$0")/qgis_plugin"

VER=$(grep -E '^version=' azo_izochrony/metadata.txt | cut -d= -f2 | tr -d '[:space:]')
OUT="../azo_izochrony-${VER}.zip"
rm -f "$OUT"

# pakuj tylko źródła wtyczki (bez cache, bez plików systemowych)
zip -r "$OUT" azo_izochrony \
  -x '*/__pycache__/*' -x '*.pyc' -x '*/.DS_Store' -x '*.qgs~' -x '*.qgz~' >/dev/null

echo "ZIP: $OUT"
unzip -l "$OUT" | sed -n '1,40p'
