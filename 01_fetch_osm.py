# -*- coding: utf-8 -*-
# KROK 1 — pobranie danych z OpenStreetMap i zbudowanie warstw roboczych.
# Uruchom w Konsoli Pythona QGIS:  exec(open('/sciezka/01_fetch_osm.py').read())
#
# Buduje w katalogu data/:
#   wojewodztwo.gpkg, gminy.gpkg (z gęstością), gzm.gpkg, fire_stations.gpkg (klasyfikacja),
#   roads_main.gpkg, tunnels.gpkg, industrial.gpkg, network34.gpkg (+speed), jrg34.gpkg, jrgksrg34.gpkg
# oraz kopie w EPSG:3857 w data3857/ (warstwy do wyświetlania).
#
# Zmienne do dostosowania pod inne województwo: WOJ_NAZWA, GZM_REL (relacja OSM metropolii/aglomeracji,
# można pominąć), UTM_EPSG (strefa UTM dla analiz metrycznych — PL: 33N=32633 zach., 34N=32634 wsch.).

import os, re, time, urllib.request, urllib.parse
from collections import Counter
from qgis.core import *
from qgis.PyQt.QtCore import QVariant

BASE = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else '/Users/tomasz/azo_gzm'
D   = os.path.join(BASE, 'data');     os.makedirs(D, exist_ok=True)
D38 = os.path.join(BASE, 'data3857'); os.makedirs(D38, exist_ok=True)

WOJ_NAZWA = 'województwo śląskie'      # dokładna nazwa OSM (admin_level=4)
GZM_REL   = 8269826                    # relacja OSM GZM (None jeśli brak metropolii)
UTM_EPSG  = 'EPSG:32634'               # UTM 34N — metryczny, ten sam datum WGS84
SERVER    = 'https://overpass-api.de/api/interpreter'
UA        = 'AZO-OSM/1.0 (analiza zabezpieczenia operacyjnego; kontakt: tomasz.zuchlke@ultraflow.run)'

crs4326 = QgsCoordinateReferenceSystem('EPSG:4326')
crs38   = QgsCoordinateReferenceSystem('EPSG:3857')
crsU    = QgsCoordinateReferenceSystem(UTM_EPSG)
ctx     = QgsProject.instance().transformContext()

def overpass(query, out):
    data = urllib.parse.urlencode({'data': query}).encode()
    req = urllib.request.Request(SERVER, data=data, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=600) as r:
        open(out, 'wb').write(r.read())
    return os.path.getsize(out)

def tag(ot, key):
    if not ot: return None
    m = re.search(r'"'+key+r'"=>"([^"]*)"', ot); return m.group(1) if m else None

def writer(path, fields, wkb, crs):
    o = QgsVectorFileWriter.SaveVectorOptions(); o.driverName = 'GPKG'
    return QgsVectorFileWriter.create(path, fields, wkb, crs, ctx, o)

AREA = f'area["boundary"="administrative"]["admin_level"="4"]["name"="{WOJ_NAZWA}"]->.woj;'

# ---------------------------------------------------------------- 1. granice
print('1/7 granice (województwo + gminy)…')
overpass(f'''[out:xml][timeout:300];
{AREA}
( relation(pivot.woj);
  relation["boundary"="administrative"]["admin_level"="7"](area.woj); );
(._;>;); out body;''', D+'/admin.osm')
mp = QgsVectorLayer(D+'/admin.osm|layername=multipolygons','mp','ogr')
da = QgsDistanceArea(); da.setEllipsoid('GRS80'); da.setSourceCrs(crs4326, ctx)
gf = QgsFields()
for n,t in [('osm_id',QVariant.String),('name',QVariant.String),('population',QVariant.Int),
            ('area_km2',QVariant.Double),('dens',QVariant.Double)]: gf.append(QgsField(n,t))
wf = QgsFields(); wf.append(QgsField('name',QVariant.String))
wg = writer(D+'/gminy.gpkg', gf, QgsWkbTypes.MultiPolygon, crs4326)
ww = writer(D+'/wojewodztwo.gpkg', wf, QgsWkbTypes.MultiPolygon, crs4326)
ng=nw=0
for ft in mp.getFeatures():
    al=str(ft['admin_level']); g=ft.geometry()
    if al=='7':
        a=da.measureArea(g)/1e6; pop=tag(ft['other_tags'],'population'); pop=int(pop) if pop else None
        dens=round(pop/a,1) if (pop and a>0) else None
        f=QgsFeature(gf); f.setGeometry(g); f.setAttributes([str(ft['osm_id']),ft['name'],pop,round(a,3),dens]); wg.addFeature(f); ng+=1
    elif al=='4':
        f=QgsFeature(wf); f.setGeometry(g); f.setAttributes([ft['name']]); ww.addFeature(f); nw+=1
del wg, ww
print(f'   gminy={ng}, woj={nw}')

# ---------------------------------------------------------------- 2. GZM
if GZM_REL:
    print('2/7 granica metropolii (GZM)…')
    overpass(f'[out:xml][timeout:120];relation({GZM_REL});(._;>;);out body;', D+'/gzm.osm')
    src=QgsVectorLayer(D+'/gzm.osm|layername=multipolygons','g','ogr')
    f0=QgsFields(); f0.append(QgsField('name',QVariant.String))
    w=writer(D+'/gzm.gpkg', f0, QgsWkbTypes.MultiPolygon, crs4326)
    for f in src.getFeatures():
        nf=QgsFeature(f0); nf.setGeometry(f.geometry()); nf.setAttributes([f['name'] or 'metropolia']); w.addFeature(nf)
    del w

# ---------------------------------------------------------------- 3. straże
print('3/7 straże pożarne (amenity=fire_station)…')
overpass(f'''[out:xml][timeout:180];
{AREA}
( node["amenity"="fire_station"](area.woj);
  way["amenity"="fire_station"](area.woj);
  relation["amenity"="fire_station"](area.woj); );
(._;>;); out body;''', D+'/fire.osm')
def classify(name, ot):
    name=name or ''; op=tag(ot,'operator') or ''; ksrg=tag(ot,'ksrg')
    if 'Państwowa Straż Pożarna' in op or 'Jednostka Ratowniczo' in name or re.search(r'\bJRG\b',name): return 'JRG'
    if ksrg=='yes': return 'OSP-KSRG'
    return 'OSP'
cands=[]
for src,centroid in [(QgsVectorLayer(D+'/fire.osm|layername=points','p','ogr'), False),
                     (QgsVectorLayer(D+'/fire.osm|layername=multipolygons','m','ogr'), True)]:
    for f in src.getFeatures():
        g=f.geometry().centroid() if centroid else f.geometry()
        if g.isEmpty(): continue
        cands.append((g.asPoint(), f['name'], classify(f['name'], f['other_tags'])))
# deduplikacja w promieniu 50 m (priorytet JRG > KSRG > OSP)
xf=QgsCoordinateTransform(crs4326, crsU, QgsProject.instance())
pri={'JRG':0,'OSP-KSRG':1,'OSP':2}; cands.sort(key=lambda c: pri[c[2]])
mpts=[(xf.transform(QgsPointXY(p[0])), p) for p in cands]; used=[False]*len(mpts); kept=[]
for i,(mi,ci) in enumerate(mpts):
    if used[i]: continue
    kept.append(ci); used[i]=True
    for j in range(i+1,len(mpts)):
        if not used[j] and (mi.x()-mpts[j][0].x())**2+(mi.y()-mpts[j][0].y())**2 < 2500: used[j]=True
ff=QgsFields(); ff.append(QgsField('name',QVariant.String)); ff.append(QgsField('kategoria',QVariant.String))
w=writer(D+'/fire_stations.gpkg', ff, QgsWkbTypes.Point, crs4326); cc=Counter()
for pt,name,cat in kept:
    f=QgsFeature(ff); f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(pt))); f.setAttributes([name,cat]); w.addFeature(f); cc[cat]+=1
del w
print('   ', dict(cc))

# ---------------------------------------------------------------- 4. drogi/tunele/przemysł
print('4/7 drogi główne, tunele, przemysł…')
overpass(f'[out:xml][timeout:200];{AREA}(way["highway"~"^(motorway|trunk|primary)$"](area.woj););(._;>;);out body;', D+'/roads_main.osm')
overpass(f'[out:xml][timeout:180];{AREA}(way["tunnel"="yes"]["highway"~"^(motorway|trunk|primary|secondary|tertiary)$"](area.woj););(._;>;);out body;', D+'/tunnels.osm')
overpass(f'[out:xml][timeout:200];{AREA}(way["landuse"="industrial"](area.woj);relation["landuse"="industrial"](area.woj););(._;>;);out body;', D+'/industrial.osm')
def lines_gpkg(src,dst):
    lyr=QgsVectorLayer(src+'|layername=lines','l','ogr')
    fld=QgsFields()
    for n in ['highway','ref','name']: fld.append(QgsField(n,QVariant.String))
    w=writer(dst,fld,QgsWkbTypes.LineString,crs4326)
    for f in lyr.getFeatures():
        nf=QgsFeature(fld); nf.setGeometry(f.geometry()); nf.setAttributes([f['highway'],tag(f['other_tags'],'ref'),f['name']]); w.addFeature(nf)
    del w
lines_gpkg(D+'/roads_main.osm', D+'/roads_main.gpkg')
lines_gpkg(D+'/tunnels.osm', D+'/tunnels.gpkg')
ind=QgsVectorLayer(D+'/industrial.osm|layername=multipolygons','i','ogr')
fi=QgsFields(); fi.append(QgsField('name',QVariant.String)); w=writer(D+'/industrial.gpkg',fi,QgsWkbTypes.MultiPolygon,crs4326)
for f in ind.getFeatures():
    if not f.geometry().isEmpty():
        nf=QgsFeature(fi); nf.setGeometry(f.geometry()); nf.setAttributes([f['name']]); w.addFeature(nf)
del w

# ---------------------------------------------------------------- 5. sieć drogowa do routingu (UTM)
print('5/7 sieć przejezdna + prędkości (do izochron)…')
overpass(f'''[out:xml][timeout:600];
{AREA}
( way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link)$"](area.woj); );
(._;>;); out body;''', D+'/network.osm')
SPEED={'motorway':120,'trunk':90,'primary':70,'secondary':60,'tertiary':50,'unclassified':45,
 'residential':30,'living_street':20,'motorway_link':60,'trunk_link':50,'primary_link':45,'secondary_link':40,'tertiary_link':35}
ln=QgsVectorLayer(D+'/network.osm|layername=lines','n','ogr')
xfu=QgsCoordinateTransform(crs4326,crsU,ctx)
nf=QgsFields(); nf.append(QgsField('highway',QVariant.String)); nf.append(QgsField('speed',QVariant.Int))
w=writer(D+'/network34.gpkg', nf, QgsWkbTypes.LineString, crsU); ne=0
for f in ln.getFeatures():
    hw=f['highway']; sp=SPEED.get(hw)
    if sp is None: continue
    ms=tag(f['other_tags'],'maxspeed'); ms=int(ms) if (ms and ms.isdigit()) else None
    if ms and 5<=ms<=140: sp=ms
    g=QgsGeometry(f.geometry())
    if g.isEmpty(): continue
    g.transform(xfu); o=QgsFeature(nf); o.setGeometry(g); o.setAttributes([hw,sp]); w.addFeature(o); ne+=1
del w
print(f'   krawędzi sieci: {ne}')

# ---------------------------------------------------------------- 6. punkty źródłowe izochron (UTM)
print('6/7 punkty JRG i JRG+KSRG (UTM)…')
fs=QgsVectorLayer(D+'/fire_stations.gpkg','f','ogr')
def points_subset(cats, dst):
    fld=QgsFields(); fld.append(QgsField('kat',QVariant.String))
    w=writer(dst,fld,QgsWkbTypes.Point,crsU); n=0
    for f in fs.getFeatures():
        if f['kategoria'] in cats:
            g=QgsGeometry(f.geometry()); g.transform(xfu)
            o=QgsFeature(fld); o.setGeometry(g); o.setAttributes([f['kategoria']]); w.addFeature(o); n+=1
    del w; return n
print('   JRG=', points_subset({'JRG'}, D+'/jrg34.gpkg'), ' JRG+KSRG=', points_subset({'JRG','OSP-KSRG'}, D+'/jrgksrg34.gpkg'))

# ---------------------------------------------------------------- 7. kopie do wyświetlania (3857)
print('7/7 reprojekcja warstw wyświetlania do EPSG:3857…')
import processing
for fn in ['gminy.gpkg','industrial.gpkg','wojewodztwo.gpkg','gzm.gpkg','roads_main.gpkg','tunnels.gpkg','fire_stations.gpkg']:
    if os.path.exists(D+'/'+fn):
        processing.run('native:reprojectlayer', {'INPUT':D+'/'+fn,'TARGET_CRS':'EPSG:3857','OUTPUT':D38+'/'+fn})
for f in os.listdir(D):              # sprzątanie surowych .osm
    if f.endswith('.osm'): os.remove(D+'/'+f)
print('GOTOWE. Dalej: 02_isochrones_analysis.py → 03_run_buffers.sh → 04_build_map.py')
