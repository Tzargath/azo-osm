"""Warstwy `popyt` i `jednostki_ksrg` w dane/wejscie.gpkg (uruchamiać po 01_przygotuj_dane.sh):
    narzedzia/pyqgis.sh 01b_popyt_i_jednostki.py
popyt — centroidy budynków mieszkalnych BDOT10k (OT_BUBD_A); ludność miejscowości (OT_ADMS_P, wieś/miasto,
        liczbaMieszkancow) rozdzielona na budynki proporcjonalnie do powierzchni, budynek → najbliższy punkt miejscowości.
jednostki_ksrg — JRG Żywiec + OSP z wykazu KSRG (KG PSP, 05.2026) przypisane do budynków straży z BDOT10k
        (dane/jednostki_ksrg.csv: kolumna „remiza BDOT10k nr” → dane/jednostki_kandydaci.csv)."""
import csv, os
from osgeo import ogr, osr
ogr.UseExceptions()
R = os.path.dirname(os.path.abspath(__file__)); D = f"{R}/dane"
src = ogr.Open(f"{D}/bdot_2417.gpkg")
wsie = [(f.GetGeometryRef().GetX(), f.GetGeometryRef().GetY(), f["nazwa"], f["liczbaMieszkancow"] or 0)
        for f in src.ExecuteSQL("SELECT nazwa, liczbaMieszkancow, geometria FROM OT_ADMS_P WHERE rodzaj IN ('wieś','miasto')")]
bud = []
for f in src.ExecuteSQL("SELECT ST_Area(geometria) AS pow, ST_Centroid(geometria) AS g FROM OT_BUBD_A "
                        "WHERE funkcjaOgolnaBudynku='budynki mieszkalne'", dialect="SQLite"):
    g = f.GetGeometryRef(); x, y = g.GetX(), g.GetY()
    j = min(range(len(wsie)), key=lambda i: (wsie[i][0] - x) ** 2 + (wsie[i][1] - y) ** 2)
    bud.append((x, y, f["pow"] or 0, j))
suma = {}
for *_, a, j in [(b[0], b[1], b[2], b[3]) for b in bud]:
    suma[j] = suma.get(j, 0) + a
kand = {r["nr"]: r for r in csv.DictReader(open(f"{D}/jednostki_kandydaci.csv", encoding="utf-8"))}
jedn = list(csv.DictReader(open(f"{D}/jednostki_ksrg.csv", encoding="utf-8")))

out = ogr.Open(f"{D}/wejscie.gpkg", 1); srs = osr.SpatialReference(); srs.ImportFromEPSG(2180)
for nazwa in ("popyt", "jednostki_ksrg"):
    if out.GetLayerByName(nazwa): out.DeleteLayer(nazwa)
L = out.CreateLayer("popyt", srs, ogr.wkbPoint)
L.CreateField(ogr.FieldDefn("lud", ogr.OFTReal)); L.CreateField(ogr.FieldDefn("wies", ogr.OFTString))
L.StartTransaction()
for x, y, a, j in bud:
    f = ogr.Feature(L.GetLayerDefn()); f["lud"] = round(wsie[j][3] * a / suma[j], 4) if suma[j] else 0
    f["wies"] = wsie[j][2]; f.SetGeometry(ogr.CreateGeometryFromWkt(f"POINT ({x} {y})")); L.CreateFeature(f)
L.CommitTransaction()
J = out.CreateLayer("jednostki_ksrg", srs, ogr.wkbPoint)
for n, t in (("nr", ogr.OFTInteger), ("nazwa", ogr.OFTString), ("typ", ogr.OFTString)):
    J.CreateField(ogr.FieldDefn(n, t))
for r in jedn:
    k = kand[r["remiza BDOT10k nr"]]
    f = ogr.Feature(J.GetLayerDefn()); f["nr"] = int(k["nr"]); f["nazwa"] = r["jednostka (wykaz KG PSP 05.2026)"]; f["typ"] = r["typ"]
    f.SetGeometry(ogr.CreateGeometryFromWkt(f"POINT ({k['x_2180']} {k['y_2180']})")); J.CreateFeature(f)
print(f"popyt: {L.GetFeatureCount()} budynków, {sum(f['lud'] for f in L):.0f} os. | jednostki: {J.GetFeatureCount()}")
