#!/bin/zsh
# KROK 3 — bufor 250 m + dissolve + reprojekcja izochron do EPSG:3857 (headless qgis_process).
# Użycie:   ./03_run_buffers.sh          # warstwy JRG  (edges480/900   -> cov480/900_3857)
#           ./03_run_buffers.sh k        # JRG+KSRG     (edges480k/900k -> covk480/900_3857)
# Wymaga zmiennej QGIS_APP lub domyślnej ścieżki aplikacji QGIS (dostosuj pod swój system).
set -e
P="${1:-}"                                   # '' albo 'k'
QGIS_APP="${QGIS_APP:-/Applications/QGIS-final-4_0_3.app/Contents}"
export PROJ_LIB="$QGIS_APP/Resources/qgis/proj" PROJ_DATA="$PROJ_LIB" GDAL_DATA="$QGIS_APP/Resources/qgis/gdal"
QP="$QGIS_APP/MacOS/qgis_process"
BASE="$(cd "$(dirname "$0")" && pwd)"; D="$BASE/data"; OUT="$BASE/data3857"
mkdir -p "$OUT"

cover () {  # band  edges_in  cov_out
  local band=$1
  "$QP" run native:buffer -- INPUT="$D/edges${band}${P}.gpkg" DISTANCE=250 SEGMENTS=4 \
     END_CAP_STYLE=0 JOIN_STYLE=0 DISSOLVE=true OUTPUT="$D/cov${P}${band}_34.gpkg"
  "$QP" run native:reprojectlayer -- INPUT="$D/cov${P}${band}_34.gpkg" TARGET_CRS=EPSG:3857 \
     OUTPUT="$OUT/cov${P}${band}_3857.gpkg"
  rm -f "$D/cov${P}${band}_34.gpkg"
  echo "OK: cov${P}${band}_3857.gpkg"
}
cover 480
cover 900
echo "GOTOWE. Dalej: 04_build_map.py"
