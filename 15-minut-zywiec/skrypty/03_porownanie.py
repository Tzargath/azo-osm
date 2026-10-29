#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""03_porownanie.py — zestawia dwa pokrycia (OSM i BDOT10k) w jedna warstwe punktowa.

Wejscie : wyniki/pokrycie_<wariant_osm>_<jednostki>.gpkg i ...<wariant_bdot>...
          (obie z 02_licz_warianty.sh — ta sama warstwa popytu, ta sama kolejnosc)
Wyjscie : wyniki/porownanie_osm_bdot.gpkg, warstwa `porownanie`
          lud, t_osm, t_bdot (min; NULL = nieosiagalne), klasa:
          oba | tylko_bdot | tylko_osm | zaden  (wzgledem progu 15 min)

    python3 03_porownanie.py [wariant_osm=v1p] [wariant_bdot=v3] [jednostki=jednostki_ksrg]

⚠ Laczenie idzie PO KOLEJNOSCI obiektow, nie po FID — dlatego skrypt sprawdza,
  czy punkty z obu warstw leza w tym samym miejscu (tolerancja 0,001 m). Rozjazd
  = ktores pokrycie liczone na innym popycie; wtedy przerywa.

⛔⛔ O osiagalnosci rozstrzyga POLE `pokr_15min` z wtyczki, a NIE `czas_min <= 15`.
  `czas_min` jest zapisany z zaokragleniem do 0,01 min (wskaznik.py: round(best/60,2)),
  wiec na samej granicy progu zaokraglenie przerzuca punkty w obie strony: przeliczenie
  z `czas_min` dalo 109 519 zamiast 109 460 os. (OSM) i 124 295 zamiast 124 256 (BDOT10k).
  Roznica jest mala, ale to byloby DRUGIE ZRODLO tej samej liczby.
"""
import os, sys
from osgeo import ogr, osr

ogr.UseExceptions()
K = os.path.dirname(os.path.abspath(__file__))
PROG = 15.0
POLE = "pokr_15min"   # flaga osiagalnosci z wtyczki — jedyne zrodlo prawdy, patrz docstring
w_osm = sys.argv[1] if len(sys.argv) > 1 else "v1p"
w_bdot = sys.argv[2] if len(sys.argv) > 2 else "v3"
jedn = sys.argv[3] if len(sys.argv) > 3 else "jednostki_ksrg"


def otworz(w):
    nazwa = f"pokrycie_{w}_{jedn}"
    sciezka = f"{K}/wyniki/{nazwa}.gpkg"
    ds = ogr.Open(sciezka)
    if ds is None:
        sys.exit(f"⛔ brak {sciezka} — policz wariant: ./02_licz_warianty.sh {w} {jedn}")
    L = ds.GetLayerByName(nazwa)
    if L.GetLayerDefn().GetFieldIndex(POLE) < 0:
        sys.exit(f"⛔ {nazwa} bez pola {POLE} — pokrycie z innego progu niz {PROG:g} min")
    return ds, L


ds_o, L_osm = otworz(w_osm)
ds_b, L_bdot = otworz(w_bdot)
if L_osm.GetFeatureCount() != L_bdot.GetFeatureCount():
    sys.exit("⛔ rozna liczba punktow popytu w pokryciach")

wyj = f"{K}/wyniki/porownanie_osm_bdot.gpkg"
if os.path.exists(wyj):
    ogr.GetDriverByName("GPKG").DeleteDataSource(wyj)
srs = osr.SpatialReference(); srs.ImportFromEPSG(2180)
ds_w = ogr.GetDriverByName("GPKG").CreateDataSource(wyj)
L = ds_w.CreateLayer("porownanie", srs, ogr.wkbPoint)
for p in ("lud", "t_bdot", "t_osm"):
    L.CreateField(ogr.FieldDefn(p, ogr.OFTReal))
L.CreateField(ogr.FieldDefn("klasa", ogr.OFTString))
dfn = L.GetLayerDefn()

sumy = {k: [0, 0.0] for k in ("oba", "tylko_bdot", "tylko_osm", "zaden")}
L.StartTransaction()
for f_o, f_b in zip(L_osm, L_bdot):
    g_o, g_b = f_o.GetGeometryRef(), f_b.GetGeometryRef()
    if abs(g_o.GetX() - g_b.GetX()) > 1e-3 or abs(g_o.GetY() - g_b.GetY()) > 1e-3:
        sys.exit("⛔ punkty popytu nie pokrywaja sie — pokrycia z roznych wejsc")
    t_o, t_b = f_o.GetField("czas_min"), f_b.GetField("czas_min")
    ok_o = f_o.GetField(POLE) == 1
    ok_b = f_b.GetField(POLE) == 1
    klasa = "oba" if (ok_o and ok_b) else "tylko_bdot" if ok_b else "tylko_osm" if ok_o else "zaden"
    lud = f_o.GetField("lud")
    sumy[klasa][0] += 1; sumy[klasa][1] += lud
    n = ogr.Feature(dfn)
    n.SetField("lud", lud)
    if t_b is not None: n.SetField("t_bdot", t_b)
    if t_o is not None: n.SetField("t_osm", t_o)
    n.SetField("klasa", klasa)
    n.SetGeometry(g_o.Clone())
    L.CreateFeature(n); n = None
L.CommitTransaction()
ds_w = None

LUD = sum(v[1] for v in sumy.values())
print(f"{wyj}\n  popyt: {sum(v[0] for v in sumy.values())} bud., {LUD:.0f} os.")
for k, (n, l) in sumy.items():
    print(f"  {k:<11} {n:>6} bud.  {l:>9.0f} os.")
for nazwa, kl in (("BDOT10k", ("oba", "tylko_bdot")), ("OSM", ("oba", "tylko_osm"))):
    s = sum(sumy[k][1] for k in kl)
    print(f"  ≤{PROG:.0f} min {nazwa:<8} {100*s/LUD:5.1f}%  ({s:.0f} os.)")
