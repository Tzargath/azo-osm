#!/bin/zsh
APP=/Applications/QGIS-final-4_0_3.app/Contents
export PROJ_LIB="$APP/Resources/qgis/proj" PROJ_DATA="$PROJ_LIB" GDAL_DATA="$APP/Resources/qgis/gdal"
QP="$APP/MacOS/qgis_process"; D=/Users/tomasz/azo_gzm/data
LOG=/Users/tomasz/azo_gzm/figbuf.log; echo "START $(date)" > "$LOG"
rm -f /Users/tomasz/azo_gzm/figbuf.DONE "$D"/cov_*_34.gpkg "$D"/cov_*_3857.gpkg "$D"/tmp_m*.gpkg

buf () {  # input field out
  "$QP" run native:buffer -- INPUT="$D/$1" DISTANCE="field:$2" SEGMENTS=6 \
     END_CAP_STYLE=0 JOIN_STYLE=0 DISSOLVE=true OUTPUT="$D/$3" >> "$LOG" 2>&1
  echo "buf $1/$2 rc=$? -> $3 $(date)" >> "$LOG"
}
buf foci_naive.gpkg  r8  cov_naive8_34.gpkg
buf foci_naive.gpkg  r15 cov_naive15_34.gpkg
buf foci_method.gpkg r8  tmp_m8.gpkg
buf foci_method.gpkg r15 tmp_m15.gpkg
# przycięcie barierami (tylko metodyka)
"$QP" run native:difference -- INPUT="$D/tmp_m8.gpkg"  OVERLAY="$D/barriers34.gpkg" OUTPUT="$D/cov_method8_34.gpkg"  >> "$LOG" 2>&1
"$QP" run native:difference -- INPUT="$D/tmp_m15.gpkg" OVERLAY="$D/barriers34.gpkg" OUTPUT="$D/cov_method15_34.gpkg" >> "$LOG" 2>&1
# reprojekcja do 3857
for f in cov_naive8 cov_naive15 cov_method8 cov_method15; do
  "$QP" run native:reprojectlayer -- INPUT="$D/${f}_34.gpkg" TARGET_CRS=EPSG:3857 OUTPUT="$D/${f}_3857.gpkg" >> "$LOG" 2>&1
done
echo "ALLDONE $(date)" >> "$LOG"; touch /Users/tomasz/azo_gzm/figbuf.DONE