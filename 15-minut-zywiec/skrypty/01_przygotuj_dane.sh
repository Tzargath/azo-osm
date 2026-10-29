#!/bin/zsh
# Konkurs GUGiK 2026 — przygotowanie danych AZO dla powiatu żywieckiego (TERYT 2417).
# WSZYSTKO z BDOT10k (opendata GUGiK) poza siecią OSM do wariantu porównawczego V1.
#
# Wyjście (dane/wejscie.gpkg, EPSG:2180):
#   powiat            — obrys powiatu (BDOT10k OT_ADJA_A, rodzaj=powiat; identyfikator PRG)
#   gminy             — 15 gmin (do zestawień)
#   siec_osm          — V1: OSM, filtr dróg JAK W ARTYKULE (bez service/track), pole highway
#   siec_bdot_v2      — V2: BDOT10k OT_SKJZ_L, drogi PUBLICZNE (krajowa…gminna), pole kat
#   siec_bdot_v3      — V3: V2 + drogi wewnętrzne; nawierzchnia nieutwardzona → kat GR
#   bariery_bdot      — rzeki (szer. z BDOT10k) + wody powierzchniowe + tory, jeden multipoligon
#   popyt             — budynki mieszkalne BDOT10k z ludnością wsi/miasta rozłożoną wg powierzchni
#
# Mapowanie kategorii zarządzania BDOT10k → klasy prędkości wtyczki (planistyczne, KG PSP):
#   krajowa + klasa „ekspresowa"/„autostrada" → S (75) · krajowa pozostałe → DK (60)
#   wojewódzka → DW (60) · powiatowa → DP (50) · gminna → DG (30)
#   V3: wewnętrzna utwardzona → DG (30) · nawierzchnia grunt naturalny/żwir/tłuczeń → GR (15)
set -e
R=${0:A:h}; source $R/gdal_env.sh
D=$R/dane; B=$D/bdot_2417.gpkg; W=$D/wejscie.gpkg
rm -f $W

# obrysy
ogr2ogr -q -f GPKG $W $B -nln powiat -dialect SQLite \
  -sql "SELECT nazwa, identyfikatorPRG AS prg, geometria AS geom FROM OT_ADJA_A WHERE rodzaj='powiat'"
ogr2ogr -q -f GPKG -update $W $B -nln gminy -dialect SQLite \
  -sql "SELECT nazwa, identyfikatorPRG AS prg, identyfikatorTERYTjednostki AS teryt, geometria AS geom FROM OT_ADJA_A WHERE rodzaj='gmina'"
ogr2ogr -q -f GeoJSON -overwrite /tmp/powiat_2180.geojson $W powiat

KAT="CASE
  WHEN kategoriaZarzadzania='krajowa' AND (klasaDrogi LIKE '%ekspresowa%' OR klasaDrogi LIKE '%autostrada%') THEN 'S'
  WHEN kategoriaZarzadzania='krajowa' THEN 'DK'
  WHEN kategoriaZarzadzania='wojewódzka' THEN 'DW'
  WHEN kategoriaZarzadzania='powiatowa' THEN 'DP'
  WHEN kategoriaZarzadzania='gminna' THEN 'DG'
  ELSE 'DG' END"
NIEUTW="materialNawierzchni IN ('grunt naturalny','żwir','tłuczeń')"

# V2: drogi publiczne (odpowiednik filtra OSM z artykułu)
ogr2ogr -q -f GPKG -update $W $B -nln siec_bdot_v2 -dialect SQLite -clipsrc /tmp/powiat_2180.geojson \
  -sql "SELECT $KAT AS kat, kategoriaZarzadzania AS zarz, materialNawierzchni AS naw, geometria AS geom
        FROM OT_SKJZ_L WHERE kategoriaZarzadzania IN ('krajowa','wojewódzka','powiatowa','gminna')"
# V3: + drogi wewnętrzne; nieutwardzone → GR
ogr2ogr -q -f GPKG -update $W $B -nln siec_bdot_v3 -dialect SQLite -clipsrc /tmp/powiat_2180.geojson \
  -sql "SELECT CASE WHEN $NIEUTW THEN 'GR' ELSE $KAT END AS kat, kategoriaZarzadzania AS zarz,
               materialNawierzchni AS naw, geometria AS geom FROM OT_SKJZ_L"

# V1: OSM (filtr dróg jak w artykule) — linie z pliku .osm
ogr2ogr -q -f GPKG -update $W $D/osm_drogi.osm lines -nln siec_osm -t_srs EPSG:2180 \
  -clipdst /tmp/powiat_2180.geojson -select highway,name -where "highway IS NOT NULL"

# bariery BDOT10k: rzeki (bufor = połowa szerokości, min 3 m) + wody powierzchniowe + tory (4 m)
ogr2ogr -q -f GPKG -update $W $B -nln bariery_bdot -dialect SQLite -nlt MULTIPOLYGON \
  -sql "SELECT ST_Union(g) AS geom FROM (
          SELECT ST_Buffer(geometria, MAX(COALESCE(szerokosc,0)/2.0, 3.0)) AS g FROM OT_SWRS_L WHERE rodzaj='rzeka'
          UNION ALL SELECT geometria FROM OT_PTWP_A
          UNION ALL SELECT ST_Buffer(geometria, 4.0) FROM OT_SKTR_L)"
echo "OK: $(for l in powiat gminy siec_osm siec_bdot_v2 siec_bdot_v3 bariery_bdot; do printf '%s=%s ' $l $(ogrinfo -q $W -sql "SELECT count(*) FROM $l" 2>/dev/null | grep -o '= [0-9]*' | tr -d '= '); done)"
