"""Mapa A3 „15 minut” — powiat żywiecki, BDOT10k vs OpenStreetMap. PyQGIS bez GUI:
    ../narzedzia/pyqgis.sh mapa_a3.py            # → mapa_a3.pdf + mapa_a3.png (300 dpi)
Wszystko z plików w ~/gugik_konkurs; liczby w legendzie liczone z warstwy, nie wpisane ręcznie."""
import os, sys
from qgis.core import (QgsApplication, QgsProject, QgsVectorLayer, QgsRasterLayer, QgsCoordinateReferenceSystem,
    QgsRectangle, QgsLayout, QgsLayoutItemMap, QgsLayoutItemLabel, QgsLayoutItemPicture, QgsLayoutItemScaleBar,
    QgsLayoutItemShape, QgsLayoutPoint, QgsLayoutSize, QgsUnitTypes, QgsLayoutExporter, QgsMarkerSymbol,
    QgsFillSymbol, QgsLineSymbol, QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsInvertedPolygonRenderer,
    QgsSingleSymbolRenderer, QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings, QgsVectorLayerSimpleLabeling,
    QgsLayoutItemMapGrid, QgsBrightnessContrastFilter, QgsHueSaturationFilter, QgsLayoutMeasurement,
    QgsLayoutItemLegend, QgsLegendStyle, QgsLayoutItemPage, QgsSimpleFillSymbolLayer, QgsTextBackgroundSettings, Qgis)
from qgis.PyQt.QtGui import QColor, QFont, QPainter
from qgis.PyQt.QtCore import Qt, QSizeF

C = "/Applications/QGIS-final-4_2_2.app/Contents"
QgsApplication.setPrefixPath(f"{C}/MacOS", True)
app = QgsApplication([], False); app.initQgis()

K = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f"{K}/mapy"
W = f"{K}/dane/wejscie.gpkg"
P = QgsProject.instance(); P.setCrs(QgsCoordinateReferenceSystem("EPSG:2180"))
FONT = "Helvetica Neue"
INK, MUTED, AMBER, RED, BLUE = "#1d232a", "#5d6670", "#ffb000", "#e5484d", "#3fa9f5"


def warstwa(sciezka, nazwa, prov="ogr"):
    l = QgsVectorLayer(sciezka, nazwa, prov)
    assert l.isValid(), sciezka
    P.addMapLayer(l, False); return l


def raster(sciezka, nazwa):
    l = QgsRasterLayer(sciezka, nazwa)
    assert l.isValid(), sciezka
    P.addMapLayer(l, False); return l


def fmt(n):  # 15090 → „15 090”
    return f"{n:,.0f}".replace(",", " ")


def tekst(size, bold=False, color=INK, bufor=None):
    f = QgsTextFormat(); q = QFont(FONT); q.setBold(bold); f.setFont(q); f.setSize(size)
    f.setSizeUnit(Qgis.RenderUnit.Points); f.setColor(QColor(color))
    if bufor:
        b = QgsTextBufferSettings(); b.setEnabled(True); b.setSize(0.8); b.setColor(QColor(bufor)); b.setOpacity(0.85)
        f.setBuffer(b)
    return f


# ---------- warstwy mapy głównej ----------
lay = []
orto_p = f"{K}/dane/orto/orto_10m_2417.tif"
hill = raster(f"{K}/dane/nmt/hillshade_10m.tif", "cień")
hill.renderer().setOpacity(0.42 if os.path.exists(orto_p) else 0.9)
hill.setBlendMode(QPainter.CompositionMode.CompositionMode_Multiply)
if os.path.exists(orto_p):
    orto = raster(orto_p, "Ortofotomapa")
    hs = orto.hueSaturationFilter(); hs.setSaturation(-55)
    bc = orto.brightnessFilter(); bc.setBrightness(-18); bc.setContrast(-10)

powiat = warstwa(f"{W}|layername=powiat", "powiat")
gminy = warstwa(f"{W}|layername=gminy", "gminy")
por = warstwa(f"{K}/wyniki/porownanie_osm_bdot.gpkg|layername=porownanie", "porownanie")
jedn = warstwa(f"{W}|layername=jednostki_ksrg", "jednostki")

# maska poza powiatem — rozjaśnia i wycisza otoczenie
maska = warstwa(f"{W}|layername=powiat", "maska")
fs = QgsFillSymbol.createSimple({"color": "246,247,248,215", "outline_style": "no"})
maska.setRenderer(QgsInvertedPolygonRenderer(QgsSingleSymbolRenderer(fs)))

gminy.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
    {"color": "0,0,0,0", "outline_color": "255,255,255,200", "outline_width": "0.35", "outline_style": "dash"})))
pl = QgsPalLayerSettings(); pl.fieldName = "nazwa"; pl.setFormat(tekst(7.2, True, "#ffffff", bufor="#1d232a"))
pl.placement = Qgis.LabelPlacement.OverPoint
gminy.setLabeling(QgsVectorLayerSimpleLabeling(pl)); gminy.setLabelsEnabled(True)

ps = QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": "29,35,42,255", "outline_width": "1.6"})
ps.appendSymbolLayer(QgsSimpleFillSymbolLayer.create({"color": "0,0,0,0", "outline_color": "255,255,255,255", "outline_width": "0.6"}))
powiat.setRenderer(QgsSingleSymbolRenderer(ps))

# sieć dróg BDOT10k (V3) — hierarchia kategorii zarządzania; pod punktami, nad terenem
drogi = warstwa(f"{W}|layername=siec_bdot_v3", "Sieć dróg BDOT10k")
def linia(kolor, w, obrys=None, ow=0, kreska=False):
    sym = QgsLineSymbol.createSimple({"color": kolor, "width": str(w), "capstyle": "round", "joinstyle": "round",
                                      "line_style": "dash" if kreska else "solid"})
    if obrys:
        tmp = QgsLineSymbol.createSimple({"color": obrys, "width": str(w + ow), "capstyle": "round"})
        sym.insertSymbolLayer(0, tmp.symbolLayer(0).clone())   # ⚠ tmp musi żyć do clone(), inaczej SIGSEGV
    return sym
drogi.setRenderer(QgsCategorizedSymbolRenderer("CASE WHEN kat = 'S' THEN 'DK' ELSE kat END", [
    QgsRendererCategory("DK", linia("255,214,102,255", 0.85, "40,30,10,220", 0.5), "krajowa i ekspresowa"),
    QgsRendererCategory("DW", linia("255,236,170,255", 0.6, "40,30,10,200", 0.4), "wojewódzka"),
    QgsRendererCategory("DP", linia("255,255,255,240", 0.42, "29,35,42,190", 0.3), "powiatowa"),
    QgsRendererCategory("DG", linia("255,255,255,190", 0.22), "gminna / wewnętrzna"),
    QgsRendererCategory("GR", linia("255,255,255,150", 0.16, kreska=True), "gruntowa (nieutwardzona)"),
]))
drogi.renderer().setUsingSymbolLevels(True)

# liczby do legendy — z warstwy
sumy = {}
for f in por.getFeatures():
    s = sumy.setdefault(f["klasa"], [0, 0.0]); s[0] += 1; s[1] += f["lud"]
LUD = sum(v[1] for v in sumy.values())
pct_bdot = 100 * (sumy["oba"][1] + sumy["tylko_bdot"][1]) / LUD
pct_osm = 100 * (sumy["oba"][1] + sumy["tylko_osm"][1]) / LUD


def pkt(kolor, size, obrys="29,35,42,160", ow="0.12"):
    return QgsMarkerSymbol.createSimple({"name": "circle", "color": kolor, "size": str(size),
                                         "outline_color": obrys, "outline_width": ow})


kat = [
    QgsRendererCategory("oba", pkt("120,200,120,200", 0.6, "30,90,40,150", "0.06"),
                        f"w zasięgu w obu sieciach — {fmt(sumy['oba'][1])} os."),
    QgsRendererCategory("zaden", pkt("229,72,77,230", 0.85, "120,20,25,180"),
                        f"poza 15 min w obu sieciach — {fmt(sumy['zaden'][1])} os."),
    QgsRendererCategory("tylko_osm", pkt("63,169,245,255", 1.0),
                        f"tylko według OSM — {fmt(sumy['tylko_osm'][1])} os."),
    QgsRendererCategory("tylko_bdot", pkt("255,176,0,255", 1.25, "60,35,0,230", "0.18"),
                        f"tylko według BDOT10k — {fmt(sumy['tylko_bdot'][1])} os. ({fmt(sumy['tylko_bdot'][0])} bud.)"),
]
r = QgsCategorizedSymbolRenderer("klasa", kat)
por.setRenderer(r)

jr = QgsCategorizedSymbolRenderer("typ", [
    QgsRendererCategory("JRG", QgsMarkerSymbol.createSimple({"name": "square", "color": "200,30,40,255", "size": "4.2",
                        "outline_color": "255,255,255,255", "outline_width": "0.6"}), "JRG PSP Żywiec"),
    QgsRendererCategory("OSP-KSRG", QgsMarkerSymbol.createSimple({"name": "triangle", "color": "200,30,40,255", "size": "3.3",
                        "outline_color": "255,255,255,255", "outline_width": "0.5"}), "OSP włączona do KSRG (33)"),
])
jedn.setRenderer(jr)

MAP_LAYERS = [jedn, por, powiat, gminy, maska, drogi, hill] + ([orto] if os.path.exists(orto_p) else [])
for l in MAP_LAYERS:
    QgsProject.instance().layerTreeRoot().addLayer(l)

# ---------- kompozycja A3 pionowo ----------
L = QgsLayout(P); L.initializeDefaults()
pg = L.pageCollection().page(0); pg.setPageSize("A3", QgsLayoutItemPage.Orientation.Portrait)
MM = Qgis.LayoutUnit.Millimeters


def etykieta(txt, x, y, w, h, size, bold=False, color=INK, html=False, align=Qt.AlignmentFlag.AlignLeft):
    it = QgsLayoutItemLabel(L); it.setText(txt); it.setTextFormat(tekst(size, bold, color))
    if html: it.setMode(QgsLayoutItemLabel.Mode.ModeHtml)
    it.setHAlign(align); it.setVAlign(Qt.AlignmentFlag.AlignTop)
    it.attemptMove(QgsLayoutPoint(x, y, MM)); it.attemptResize(QgsLayoutSize(w, h, MM)); L.addLayoutItem(it); return it


def ramka(x, y, w, h, fill="#f4f5f7", stroke=None):
    s = QgsLayoutItemShape(L); s.setShapeType(QgsLayoutItemShape.Shape.Rectangle)
    s.setSymbol(QgsFillSymbol.createSimple({"color": fill, "outline_style": "no" if not stroke else "solid",
                                            "outline_color": stroke or fill, "outline_width": "0.2"}))
    s.attemptMove(QgsLayoutPoint(x, y, MM)); s.attemptResize(QgsLayoutSize(w, h, MM)); L.addLayoutItem(s); return s


# pas tytułowy
ramka(0, 0, 297, 34, fill=INK)
etykieta("15 MINUT", 14, 6.5, 120, 12, 27, True, "#ffffff")
etykieta("Kto czeka dłużej na straż pożarną, zależy od mapy, na której to policzysz.", 14, 19.5, 200, 8, 12.5, False, "#d5dae0")
etykieta("POWIAT ŻYWIECKI · ZASIĘG 15 MIN JEDNOSTEK KSRG", 160, 8, 123, 6, 8.5, True, AMBER, align=Qt.AlignmentFlag.AlignRight)
etykieta("BDOT10k (GUGiK) vs OpenStreetMap — te same jednostki, popyt i parametry", 140, 13.5, 143, 6, 8, False, "#aab2bb",
         align=Qt.AlignmentFlag.AlignRight)

# mapa główna
MX, MY, MW, MH = 12, 42, 196, 262
m = QgsLayoutItemMap(L); m.attemptMove(QgsLayoutPoint(MX, MY, MM)); m.attemptResize(QgsLayoutSize(MW, MH, MM))
m.setCrs(QgsCoordinateReferenceSystem("EPSG:2180")); m.setLayers(MAP_LAYERS); m.setKeepLayerSet(True)
e = powiat.extent(); cx, cy = e.center().x(), e.center().y()
hw, hh = MW * 200 / 2, MH * 200 / 2   # 1:200 000 → 1 mm = 200 m
m.zoomToExtent(QgsRectangle(cx - hw, cy - hh, cx + hw, cy + hh)); m.setScale(200000)
m.setFrameEnabled(True); m.setFrameStrokeColor(QColor(INK)); m.setFrameStrokeWidth(QgsLayoutMeasurement(0.3))
m.setBackgroundColor(QColor("#f6f7f8"))
L.addLayoutItem(m)
g = QgsLayoutItemMapGrid("PL-1992", m); m.grids().addGrid(g)
g.setIntervalX(10000); g.setIntervalY(10000); g.setStyle(QgsLayoutItemMapGrid.GridStyle.FrameAnnotationsOnly)
g.setFrameStyle(QgsLayoutItemMapGrid.FrameStyle.Zebra); g.setFrameWidth(1.4)
g.setFrameFillColor1(QColor(INK)); g.setFrameFillColor2(QColor("#ffffff"))
g.setAnnotationEnabled(True); g.setAnnotationFormat(QgsLayoutItemMapGrid.AnnotationFormat.CustomFormat)
g.setAnnotationExpression("format_number(@grid_number/1000, 0) || ' km'")
g.setAnnotationTextFormat(tekst(6, False, MUTED)); g.setAnnotationFrameDistance(1.2)
for side in (QgsLayoutItemMapGrid.BorderSide.Left, QgsLayoutItemMapGrid.BorderSide.Right):
    g.setAnnotationDirection(QgsLayoutItemMapGrid.AnnotationDirection.Vertical, side)
g.setAnnotationDisplay(QgsLayoutItemMapGrid.DisplayMode.HideAll, QgsLayoutItemMapGrid.BorderSide.Right)
g.setAnnotationDisplay(QgsLayoutItemMapGrid.DisplayMode.HideAll, QgsLayoutItemMapGrid.BorderSide.Top)
g2 = QgsLayoutItemMapGrid("siatka", m); m.grids().addGrid(g2)
g2.setIntervalX(10000); g2.setIntervalY(10000); g2.setStyle(QgsLayoutItemMapGrid.GridStyle.Cross); g2.setCrossLength(2.2)
g2.setLineSymbol(QgsLineSymbol.createSimple({"color": "255,255,255,170", "width": "0.25"}))

# strzałka północy + skala na mapie
ramka(MX + 4, MY + 4, 15, 19, fill="255,255,255,225")
na = QgsLayoutItemPicture(L); na.setPicturePath(f"{C}/Resources/qgis/svg/arrows/NorthArrow_02.svg")
na.attemptMove(QgsLayoutPoint(MX + 6.5, MY + 5.5, MM)); na.attemptResize(QgsLayoutSize(10, 13, MM)); L.addLayoutItem(na)
na.setLinkedMap(m)
etykieta("N", MX + 4, MY + 18.2, 15, 4, 6.5, True, INK, align=Qt.AlignmentFlag.AlignHCenter)

SBX = MX + MW - 66   # prawy dolny róg — poza powiatem (pusta maska), nie zasłania danych
ramka(SBX, MY + MH - 18, 62, 14, fill="255,255,255,230")
sb = QgsLayoutItemScaleBar(L); sb.setStyle("Single Box"); sb.setLinkedMap(m)
sb.setUnits(Qgis.DistanceUnit.Kilometers); sb.setUnitLabel("km"); sb.setUnitsPerSegment(2.5)
sb.setNumberOfSegments(4); sb.setNumberOfSegmentsLeft(0); sb.setHeight(1.4); sb.setLabelBarSpace(1.0)
sb.setTextFormat(tekst(6, False, INK)); sb.setFillColor(QColor(INK)); sb.setFillColor2(QColor("#ffffff"))
sb.attemptMove(QgsLayoutPoint(SBX + 4, MY + MH - 16.5, MM)); L.addLayoutItem(sb); sb.update()
etykieta("skala 1:200 000 · układ PL-1992 (EPSG:2180)", SBX + 4, MY + MH - 8.6, 56, 4, 5.6, False, MUTED)

# ---------- kolumna prawa ----------
RX, RW = 214, 71
# mapa lokalizacyjna
prg = f"{K}/dane/prg/prg_uogolnione.gpkg"
woj = warstwa(f"{prg}|layername=woj", "województwa")
woj.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
    {"color": "#e3e6ea", "outline_color": "#ffffff", "outline_width": "0.25"})))
pz = warstwa(f"{prg}|layername=pow|subset=\"JPT_KOD_JE\"='2417'", "pow2417")
pz.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
    {"color": "#e5484d", "outline_color": "#8a1c20", "outline_width": "0.2"})))
im = QgsLayoutItemMap(L); im.attemptMove(QgsLayoutPoint(RX, MY, MM)); im.attemptResize(QgsLayoutSize(RW, 64, MM))
im.setCrs(QgsCoordinateReferenceSystem("EPSG:2180")); im.setLayers([pz, woj]); im.setKeepLayerSet(True)
we = woj.extent(); we.grow(15000); im.setExtent(we); im.setBackgroundEnabled(False); im.setFrameEnabled(False)
L.addLayoutItem(im)
etykieta("powiat żywiecki (2417)<br><span style='color:#5d6670'>woj. śląskie · granice z usługi WFS PRG</span>",
         RX, MY + 64, RW, 9, 6.6, True, INK, html=True)

# liczby kluczowe
Y = MY + 77
ramka(RX, Y, RW, 46, fill="#fff6e0")
etykieta(f"{pct_bdot:.1f}%".replace(".", ","), RX + 4, Y + 3, 40, 14, 24, True, "#b36b00")
etykieta("mieszkańców<br>w zasięgu 15 min<br>według <b>BDOT10k</b>", RX + 38, Y + 4.5, RW - 40, 13, 7, html=True)
etykieta(f"{pct_osm:.1f}%".replace(".", ","), RX + 4, Y + 18, 40, 12, 18, True, "#6b7480")
etykieta("według <b>OpenStreetMap</b><br>(z drogami service/track)", RX + 38, Y + 19.5, RW - 38, 10, 7, html=True)
etykieta(f"<b>+{fmt(sumy['tylko_bdot'][1])} osób</b> w {fmt(sumy['tylko_bdot'][0])} budynkach mieszkalnych, "
         "których OSM nie „widzi” w 15 minutach.", RX + 4, Y + 32, RW - 8, 12, 7, html=True)

# legenda (ręczna lista z symbolami z warstw)
Y = MY + 128
ramka(RX, Y + 6, RW, 61.5, fill="#aab2bb")   # szare tło: białe linie i drobne punkty widoczne
etykieta("LEGENDA", RX, Y, RW, 5, 7.5, True, INK)
lg = QgsLayoutItemLegend(L); lg.setLinkedMap(m); lg.setAutoUpdateModel(False)
root = lg.model().rootGroup(); root.removeAllChildren()
for l in (por, jedn, drogi):
    root.addLayer(l)
for n in root.findLayers():
    n.setCustomProperty("legend/title-style", "subgroup" if n.layer() is drogi else "hidden")
lg.setTitle(""); lg.setSymbolWidth(5); lg.setSymbolHeight(3.0); lg.setWrapString("|"); lg.setMinimumSymbolSize(2.0)
lg.rstyle(QgsLegendStyle.Style.SymbolLabel).setTextFormat(tekst(6.5, False, INK))
lg.rstyle(QgsLegendStyle.Style.Subgroup).setTextFormat(tekst(6.8, True, INK))
lg.rstyle(QgsLegendStyle.Style.Subgroup).setMargin(QgsLegendStyle.Side.Top, 3)
lg.rstyle(QgsLegendStyle.Style.Symbol).setMargin(QgsLegendStyle.Side.Top, 1.0)
lg.setBackgroundEnabled(False); lg.setFrameEnabled(False)
lg.attemptMove(QgsLayoutPoint(RX + 1, Y + 5, MM)); lg.setResizeToContents(True); L.addLayoutItem(lg)
lg.updateLegend()

# uzasadnienie — dlaczego różnica jest ważna i dlaczego BDOT10k
Y = MY + 195.5
ramka(RX, Y, RW, 66.5, fill="#f4f5f7")
etykieta("DLACZEGO TA RÓŻNICA JEST WAŻNA", RX + 4, Y + 3.5, RW - 8, 5, 7, True, INK)
etykieta(
    f"<b>{fmt(sumy['tylko_bdot'][1]).replace(chr(0x202f), '&nbsp;')}&nbsp;osób to więcej niż cała gmina Węgierska Górka</b> (15&nbsp;044). "
    "Z zasięgu „wypadają” domy w górskich dolinach — tam, gdzie pomoc i tak jedzie najdłużej.<br><br>"
    "<b>To nie efekt „więcej dróg”.</b> OSM z drogami leśnymi ma ich więcej kilometrów niż BDOT10k, "
    "a i tak wypada słabiej. Decyduje <b>kategoria zarządzania</b>: w OSM analityk musi zgadnąć, "
    "czy „tertiary” to droga powiatowa czy gminna — i od tego jednego założenia ten sam powiat ma "
    "<b>74,1% albo 82,1%</b>.<br><br>"
    "<b>BDOT10k daje jedną odpowiedź: 84,1%.</b> Kategoria i nawierzchnia każdej drogi są atrybutem "
    "urzędowym, jednolitym w całym kraju i bezpłatnym. Ta sama metoda da porównywalny wynik "
    "w każdym z 380 powiatów — i w kolejnych latach.<br><br>"
    "<span style='color:#5d6670'>Nachylenie terenu (NMT, funkcja Toblera): −0,8 p.p. "
    "O zasięgu w górach decyduje sieć, nie stok.</span>",
    RX + 4, Y + 9.5, RW - 8, 57, 6.15, html=True)

# ---------- pas dolny: wykres gmin ----------
Y = 313
etykieta("GMINY: ODSETEK MIESZKAŃCÓW W ZASIĘGU 15 MIN — OSM → BDOT10k", 12, Y, 200, 5, 7.5, True, INK)
wy = QgsLayoutItemPicture(L); wy.setPicturePath(f"{OUT}/wykres_gmin.svg")
wy.attemptMove(QgsLayoutPoint(12, Y + 5, MM)); wy.attemptResize(QgsLayoutSize(273, 79, MM)); L.addLayoutItem(wy)

# stopka
ramka(0, 398, 297, 22, fill="#eef0f2")
etykieta(
    "<b>Dane i usługi GUGiK (PZGiK):</b> BDOT10k (sieć dróg SKJZ, budynki BUBD, wody SWRS/PTWP, tory SKTR, ludność ADMS, granice ADJA) · "
    "NMT 10 m z usługi WCS · Ortofotomapa z usługi WMS · granice PRG z usługi WFS. "
    "<b>Porównanie:</b> © współtwórcy OpenStreetMap (ODbL), Overpass API, 28.10.2026. "
    "<b>Jednostki:</b> wykaz OSP włączonych do KSRG, KG PSP, maj 2026 + JRG Żywiec. "
    "<b>Model:</b> wtyczka QGIS „Izochrony AZO” 1.7 — czas alarmowania JRG 3 min, OSP 10 min, dojście poza drogą 3 km/h do 300 m, "
    "bariery: rzeki, wody, tory (BDOT10k); prędkości planistyczne wg kategorii drogi. "
    "Metoda: Zuchlke T., Zeszyty Naukowe SGSP, doi:10.5604/01.3001.0055.9211.",
    12, 400.5, 220, 16, 5.6, html=True, color=MUTED)
etykieta("Opracowanie: Tomasz Zuchlke<br>Tomasz Zuchlke Labs · 10.2026<br>"
         "<span style='color:#8a929b'>Opracowanie prywatne, nie stanowisko PSP.</span>",
         236, 400.5, 50, 16, 5.8, html=True, color=INK, align=Qt.AlignmentFlag.AlignRight)

ex = QgsLayoutExporter(L)
ps = QgsLayoutExporter.PdfExportSettings(); ps.dpi = 300; ps.rasterizeWholeImage = False; ps.exportMetadata = False  # bez Author=<konto systemowe>
print("pdf", ex.exportToPdf(f"{OUT}/mapa_a3.pdf", ps))
im_s = QgsLayoutExporter.ImageExportSettings(); im_s.exportMetadata = False; im_s.dpi = int(sys.argv[1]) if len(sys.argv) > 1 else 300
print("png", ex.exportToImage(f"{OUT}/mapa_a3.png", im_s))
print(f"BDOT {pct_bdot:.2f}%  OSM {pct_osm:.2f}%  LUD {LUD:.0f}", {k: (v[0], round(v[1])) for k, v in sumy.items()})
app.exitQgis()
