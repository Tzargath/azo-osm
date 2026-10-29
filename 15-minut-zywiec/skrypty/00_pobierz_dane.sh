#!/bin/zsh
# Konkurs GUGiK 2026 — pobranie danych wejściowych dla powiatu żywieckiego (TERYT 2417). Wszystko publiczne.
#   BDOT10k (opendata GUGiK) · NMT 10 m (WCS Geoportalu) · ortofotomapa 10 m (WMS Geoportalu) · OSM (Overpass, do porównania)
# ⚠ OSM to migawka z dnia pobrania (28.10.2026) — ponowne pobranie da nieco inne liczby wariantów V1/V1+.
set -e
R=${0:A:h}; D=$R/dane; mkdir -p $D/nmt $D/orto $D/osm_st
curl -sL -o $D/bdot_2417.zip "https://opendata.geoportal.gov.pl/bdot10k/schemat2021/24/2417_GML.zip"
unzip -q -o $D/bdot_2417.zip -d $D/bdot_2417
source $R/gdal_env.sh
rm -f $D/bdot_2417.gpkg
for L in OT_SKJZ_L OT_SWRS_L OT_PTWP_A OT_SKTR_L OT_BUBD_A OT_ADJA_A OT_ADMS_P; do
  ogr2ogr -q -f GPKG -update -append $D/bdot_2417.gpkg "$(find $D/bdot_2417 -name "*_${L}.xml" | head -1)" -nln $L; done
python3 $R/narzedzia/pobierz_geoportal.py --warstwa nmt  --res 10 --bbox2180 495500,169000,535500,218500 --out $D/nmt  --nazwa nmt_10m_2417
gdal_edit.py -a_nodata 0 $D/nmt/nmt_10m_2417.tif           # poza granicą państwa usługa zwraca 0
python3 $R/narzedzia/pobierz_geoportal.py --warstwa orto --res 10 --bbox2180 495000,169000,535500,218500 --out $D/orto --nazwa orto_10m_2417 --watki 2

# OSM: V1 = filtr dróg jak w artykule (bez service/track); V1+ = dodatkowo service/track (4 kafle — Overpass dławi całość)
OV=https://overpass-api.de/api/interpreter; BB="49.373976,18.926579,49.848882,19.500765"
H='^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link)$'
curl -s -A "gugik-azo/1.0" -o $D/osm_drogi.osm --data-urlencode "data=[out:xml][timeout:180];(way[\"highway\"~\"$H\"]($BB););(._;>;);out body;" $OV
S=49.393976; N=49.828882; W=18.946579; E=19.480765; MY=$(( (S+N)/2 )); MX=$(( (W+E)/2 )); i=0
for bb in "$S,$W,$MY,$MX" "$S,$MX,$MY,$E" "$MY,$W,$N,$MX" "$MY,$MX,$N,$E"; do i=$((i+1))
  curl -s -A "gugik-azo/1.0" -o $D/osm_st/t$i.osm --data-urlencode \
    "data=[out:xml][timeout:120];(way[\"highway\"~\"^(service|track)\$\"]($bb););(._;>;);out body;" $OV; done
echo "dane pobrane → teraz: ./01_przygotuj_dane.sh && narzedzia/pyqgis.sh 01b_popyt_i_jednostki.py"
