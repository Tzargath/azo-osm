# -*- coding: utf-8 -*-
# AZO GZM — budowa mapy rekonesansowej (warstwy + symbolika + kolejnosc)
# Uruchamiac w konsoli Pythona QGIS lub przez MCP execute_code: exec(open('.../build_map.py').read())
from qgis.core import *
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import Qt
import json, os

D = '/Users/tomasz/azo_gzm/data3857/'   # !!! ZMIEŃ na ścieżkę swojego repozytorium (katalog data3857/)
proj = QgsProject.instance()
proj.setCrs(QgsCoordinateReferenceSystem('EPSG:3857'))
# clean reload: drop all existing layers
proj.removeAllMapLayers()
proj.layerTreeRoot().removeAllChildren()
NOPEN = Qt.PenStyle.NoPen; DASH = Qt.PenStyle.DashLine
RCAP = Qt.PenCapStyle.RoundCap; RJOIN = Qt.PenJoinStyle.RoundJoin

def qcol(s):
    """Accept 'r,g,b' or 'r,g,b,a' strings (and #hex / names)."""
    if isinstance(s, str) and ',' in s:
        p = [int(x) for x in s.split(',')]
        return QColor(*p)
    return QColor(s)

def simple_fill(rgba):
    s = QgsFillSymbol.createSimple({'color': rgba, 'style': 'solid'})
    s.symbolLayer(0).setStrokeStyle(NOPEN); return s
def outline(color, w, dash=False):
    s = QgsFillSymbol.createSimple({'color': '255,255,255,0', 'style': 'no'})
    sl = s.symbolLayer(0); sl.setStrokeColor(qcol(color)); sl.setStrokeWidth(w)
    if dash: sl.setStrokeStyle(DASH)
    return s
def line_sym(color, w):
    s = QgsLineSymbol.createSimple({'line_color': color, 'line_width': str(w)})
    s.symbolLayer(0).setPenCapStyle(RCAP); s.symbolLayer(0).setPenJoinStyle(RJOIN); return s
def marker(shape, color, size, stroke='white', sw=0.3):
    return QgsMarkerSymbol.createSimple({'name': shape, 'color': color, 'size': str(size),
        'outline_color': stroke, 'outline_width': str(sw)})

# --- load layers (no auto-legend; we order manually) ---
defs = [
 ('gminy.gpkg', 'Gminy — gęstość zaludnienia'),
 ('industrial.gpkg', 'Tereny przemysłowe'),
 ('wojewodztwo.gpkg', 'Województwo śląskie'),
 ('gzm.gpkg', 'GZM (granica)'),
 ('roads_main.gpkg', 'Drogi: autostrady / ekspresowe / krajowe'),
 ('tunnels.gpkg', 'Tunele drogowe'),
 ('fire_stations.gpkg', 'Straże pożarne (JRG / OSP-KSRG / OSP)'),
 ('cov900_3857.gpkg', 'Zasięg JRG ≤ 15 min'),
 ('cov480_3857.gpkg', 'Zasięg JRG ≤ 8 min'),
]
lyr = {}
for fn, name in defs:
    path = D + fn
    if not os.path.exists(path):
        continue
    l = QgsVectorLayer(path, name, 'ogr')
    if not l.isValid():
        print('INVALID', fn); continue
    proj.addMapLayer(l, False)
    lyr[fn] = l

# --- styling ---
lyr['wojewodztwo.gpkg'].setRenderer(QgsSingleSymbolRenderer(outline('60,60,60', 0.7)))
lyr['gzm.gpkg'].setRenderer(QgsSingleSymbolRenderer(outline('230,90,15', 1.3)))
lyr['industrial.gpkg'].setRenderer(QgsSingleSymbolRenderer(simple_fill('150,110,160,140')))

gm = lyr['gminy.gpkg']
ramp = QgsStyle.defaultStyle().colorRamp('Reds')
ren = QgsGraduatedSymbolRenderer.createRenderer(gm, 'dens', 5, QgsGraduatedSymbolRenderer.Jenks,
        QgsFillSymbol.createSimple({'color': '220,220,220'}), ramp)
for r in ren.ranges():
    sym = r.symbol(); sym.setOpacity(0.78)
    sym.symbolLayer(0).setStrokeColor(qcol('255,255,255')); sym.symbolLayer(0).setStrokeWidth(0.06)
gm.setRenderer(ren)

rd = lyr['roads_main.gpkg']
rcats = [
 QgsRendererCategory('motorway', line_sym('200,30,30', 0.9), 'Autostrada (A1, A4)'),
 QgsRendererCategory('trunk', line_sym('235,120,20', 0.7), 'Ekspresowa / GP (S1, DK)'),
 QgsRendererCategory('primary', line_sym('245,200,40', 0.45), 'Główna (DK/DW)'),
]
rd.setRenderer(QgsCategorizedSymbolRenderer('highway', rcats))

ts = line_sym('10,140,200', 1.6)
lyr['tunnels.gpkg'].setRenderer(QgsSingleSymbolRenderer(ts))

fs = lyr['fire_stations.gpkg']
fcats = [
 QgsRendererCategory('JRG', marker('star', '215,25,25', 4.6, 'white', 0.5), 'JRG / PSP (zawodowe)'),
 QgsRendererCategory('OSP-KSRG', marker('triangle', '30,90,200', 2.8, 'white', 0.3), 'OSP w KSRG'),
 QgsRendererCategory('OSP', marker('circle', '120,120,120', 1.5, 'white', 0.15), 'OSP (poza KSRG)'),
]
fs.setRenderer(QgsCategorizedSymbolRenderer('kategoria', fcats))

# isochrones: 15-min lighter (below), 8-min stronger (above)
if 'cov900_3857.gpkg' in lyr:
    lyr['cov900_3857.gpkg'].setRenderer(QgsSingleSymbolRenderer(simple_fill('90,195,120,85')))
if 'cov480_3857.gpkg' in lyr:
    lyr['cov480_3857.gpkg'].setRenderer(QgsSingleSymbolRenderer(simple_fill('20,120,70,120')))

# --- layer order: top -> bottom ---
order = ['fire_stations.gpkg', 'tunnels.gpkg', 'roads_main.gpkg',
         'gzm.gpkg', 'wojewodztwo.gpkg',
         'cov480_3857.gpkg', 'cov900_3857.gpkg',
         'industrial.gpkg', 'gminy.gpkg']
root = proj.layerTreeRoot()
for fn in reversed(order):
    if fn in lyr:
        root.insertLayer(0, lyr[fn])

# persist layer ids
ids = {fn: l.id() for fn, l in lyr.items()}
json.dump(ids, open('/Users/tomasz/azo_gzm/layer_ids.json', 'w'))
print('LOADED:', [proj.mapLayer(n.layerId()).name() for n in root.findLayers()])
