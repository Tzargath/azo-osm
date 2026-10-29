#!/bin/zsh
# Konkurs GUGiK — wskaźnik pokrycia dla wariantów sieci. Te same jednostki, popyt, bariery i parametry
# (planistyczne KG PSP: alarm JRG 3 / OSP 10 min, v_poza 3 km/h, R_max 300 m, progi 8 i 15 min).
# Użycie: ./02_licz_warianty.sh <wariant> <warstwa_jednostek>   wariant: v1 | v1p (OSM + service/track) | v2 | v3 | v4 (v3 + NMT)
R=${0:A:h}; source $R/gdal_env.sh
QP=/Applications/QGIS-final-4_2_2.app/Contents/MacOS/qgis_process
W=$R/dane/wejscie.gpkg; J=${2:-jednostki_ksrg}; mkdir -p $R/wyniki; cd $R/wyniki
case $1 in
  v1) NET=siec_osm;     CF=highway; SP="motorway,75,trunk,75,primary,60,secondary,50,tertiary,30,unclassified,30,residential,30,living_street,30,motorway_link,75,trunk_link,75,primary_link,60,secondary_link,50,tertiary_link,30" ;;
  v1p) NET=siec_osm_plus; CF=highway; SP="motorway,75,trunk,75,primary,60,secondary,50,tertiary,30,unclassified,30,residential,30,living_street,30,motorway_link,75,trunk_link,75,primary_link,60,secondary_link,50,tertiary_link,30,service,30,track1,30,track,15" ;;
  v1pt) NET=siec_osm_plus; CF=highway; SP="motorway,75,trunk,75,primary,60,secondary,50,tertiary,50,unclassified,30,residential,30,living_street,30,motorway_link,75,trunk_link,75,primary_link,60,secondary_link,50,tertiary_link,50,service,30,track1,30,track,15" ;;  # test czułości: tertiary jak DP
  v2) NET=siec_bdot_v2; CF=kat;     SP="A,75,S,75,DK,60,DW,60,DP,50,DG,30,GR,15" ;;
  v3) NET=siec_bdot_v3; CF=kat;     SP="A,75,S,75,DK,60,DW,60,DP,50,DG,30,GR,15" ;;
  v4) NET=siec_bdot_v3; CF=kat;     SP="A,75,S,75,DK,60,DW,60,DP,50,DG,30,GR,15"; DEM="DEM=$R/dane/nmt/nmt_10m_2417.tif" ;;
esac
$QP run azo:wskaznik_pokrycia -- NETWORK="$W|layername=$NET" CLASS_FIELD=$CF SPEEDS="$SP" DEFAULT_SPEED=30 \
  POINTS="$W|layername=$J" TYPE_FIELD=typ ALARMS="JRG,3,PSP,3,OSP-KSRG,10,OSP,10" DEFAULT_ALARM=10 \
  DEMAND="$W|layername=popyt" POP_FIELD=lud THRESHOLDS="8,15" OFFROAD_SPEED=3 OFFROAD_MAX=300 \
  BARRIERS="$W|layername=bariery_bdot" TOLERANCE=25 ${DEM:-} OUTPUT=pokrycie_${1}_${J}.gpkg > log_${1}_${J}.txt 2>&1
grep -A3 "POKRYCIE LUDNOŚCI" log_${1}_${J}.txt
