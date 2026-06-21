#!/bin/zsh
APP=/Applications/QGIS-final-4_0_3.app/Contents
export PROJ_LIB="$APP/Resources/qgis/proj" PROJ_DATA="$PROJ_LIB" GDAL_DATA="$APP/Resources/qgis/gdal"
QP="$APP/MacOS/qgis_process"; D=/Users/tomasz/azo_gzm/data
LOG=/Users/tomasz/azo_gzm/naivebuf.log; echo START>"$LOG"
rm -f /Users/tomasz/azo_gzm/naivebuf.DONE "$D"/cov_naive8_2180.gpkg "$D"/cov_naive15_2180.gpkg "$D"/cov_naive8_34n.gpkg "$D"/cov_naive15_34n.gpkg
"$QP" run native:buffer -- INPUT="$D/foci_naive_new.gpkg" DISTANCE="field:r8f"  SEGMENTS=6 END_CAP_STYLE=0 JOIN_STYLE=0 DISSOLVE=true OUTPUT="$D/cov_naive8_34n.gpkg"  >>"$LOG" 2>&1
"$QP" run native:buffer -- INPUT="$D/foci_naive_new.gpkg" DISTANCE="field:r15f" SEGMENTS=6 END_CAP_STYLE=0 JOIN_STYLE=0 DISSOLVE=true OUTPUT="$D/cov_naive15_34n.gpkg" >>"$LOG" 2>&1
"$QP" run native:reprojectlayer -- INPUT="$D/cov_naive8_34n.gpkg"  TARGET_CRS=EPSG:2180 OUTPUT="$D/cov_naive8_2180.gpkg"  >>"$LOG" 2>&1
"$QP" run native:reprojectlayer -- INPUT="$D/cov_naive15_34n.gpkg" TARGET_CRS=EPSG:2180 OUTPUT="$D/cov_naive15_2180.gpkg" >>"$LOG" 2>&1
echo ALLDONE>>"$LOG"; touch /Users/tomasz/azo_gzm/naivebuf.DONE
