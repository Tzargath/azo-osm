# -*- coding: utf-8 -*-
# KROK 2 — izochrony dojazdu (analiza sieciowa). Uruchom w Konsoli Pythona QGIS:
#   exec(open('/sciezka/02_isochrones.py').read())
#
# Metoda: graf drogowy budowany RAZ, Dijkstra z każdej jednostki, dla każdego węzła zapamiętujemy
# minimalny czas dojazdu DO NAJBLIŻSZEJ jednostki -> naturalna unia zasięgów (małe wyjście).
# Dlaczego nie processing 'serviceareafromlayer': przy wielu źródłach zapisuje on osiągalne krawędzie
# OSOBNO dla każdego punktu -> wynik rzędu GB. Tu liczymy w pamięci.
#
# Dwa przebiegi (zmień SRC/PREFIX i uruchom ponownie):
#   SRC='jrg34.gpkg',     PREFIX=''   -> edges480.gpkg / edges900.gpkg   (same JRG)
#   SRC='jrgksrg34.gpkg', PREFIX='k'  -> edges480k.gpkg / edges900k.gpkg  (JRG + OSP-KSRG)

import os, time
from qgis.core import *
from qgis.PyQt.QtCore import QVariant
from qgis.analysis import (QgsVectorLayerDirector, QgsNetworkSpeedStrategy,
    QgsGraphBuilder, QgsGraphAnalyzer)

BASE = '/Users/tomasz/azo_gzm'          # !!! ZMIEŃ na ścieżkę swojego repozytorium
D = os.path.join(BASE, 'data')
SRC    = 'jrg34.gpkg'          # <-- 'jrg34.gpkg' albo 'jrgksrg34.gpkg'
PREFIX = ''                    # <-- '' dla JRG, 'k' dla JRG+KSRG
BANDS  = {480: 'edges480'+PREFIX+'.gpkg', 900: 'edges900'+PREFIX+'.gpkg'}   # 8 i 15 min [s]
UTM_EPSG = 'EPSG:32634'
crsU = QgsCoordinateReferenceSystem(UTM_EPSG); ctx = QgsProject.instance().transformContext()

net = QgsVectorLayer(D+'/network34.gpkg','net','ogr')
src = QgsVectorLayer(D+'/'+SRC,'src','ogr')
spd = net.fields().indexFromName('speed')

director = QgsVectorLayerDirector(net, -1, '', '', '', QgsVectorLayerDirector.DirectionBoth)
director.addStrategy(QgsNetworkSpeedStrategy(spd, 50.0, 1000.0/3600.0))   # koszt = czas [s]
builder = QgsGraphBuilder(crsU, False, 25.0)
pts = [f.geometry().asPoint() for f in src.getFeatures()]
tied = director.makeGraph(builder, pts); graph = builder.graph()
nV = graph.vertexCount()
print(f'graf: {nV} węzłów, {graph.edgeCount()} krawędzi, {len(tied)} jednostek')

INF=float('inf'); gmin=[INF]*nV; t=time.time()
for tp in tied:
    _, cost = QgsGraphAnalyzer.dijkstra(graph, graph.findVertex(tp), 0)
    for v in range(nV):
        c=cost[v]
        if 0<=c<gmin[v]: gmin[v]=c
print(f'Dijkstra x{len(tied)}: {time.time()-t:.0f}s')

vp=[graph.vertex(v).point() for v in range(nV)]
for band, fn in BANDS.items():
    fld=QgsFields(); fld.append(QgsField('b',QVariant.Int))
    o=QgsVectorFileWriter.SaveVectorOptions(); o.driverName='GPKG'
    w=QgsVectorFileWriter.create(D+'/'+fn, fld, QgsWkbTypes.LineString, crsU, ctx, o)
    for e in range(graph.edgeCount()):
        ed=graph.edge(e); a=ed.fromVertex(); b=ed.toVertex()
        if gmin[a]<=band and gmin[b]<=band:
            f=QgsFeature(fld); f.setGeometry(QgsGeometry.fromPolylineXY([vp[a],vp[b]])); f.setAttributes([band]); w.addFeature(f)
    del w
    print(f'pasmo {band}s: {sum(1 for c in gmin if c<=band)} węzłów w zasięgu -> {fn}')
print('Dalej: 03_run_buffers.sh '+(PREFIX or '(bez argumentu = JRG)'))
