"""Wykres hantlowy: pokrycie 15 min per gmina, OSM (V1+) → BDOT10k (V3). Dane liczone z
wyniki/porownanie_osm_bdot.gpkg (przecięcie z gminami BDOT10k ADJA). Wyjście: SVG do kompozycji."""
import os, sqlite3, sys
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from osgeo import ogr

K = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ds = ogr.Open(f"{K}/wyniki/porownanie_osm_bdot.gpkg")
ogr.UseExceptions()
we = ogr.Open(f"{K}/dane/wejscie.gpkg"); gm = we.GetLayerByName("gminy")
pts = ds.GetLayer(0)
rows = []
for g in gm:
    geom = g.GetGeometryRef().Clone()
    pts.SetSpatialFilter(geom)
    lud = osm = bdot = 0.0
    for p in pts:
        l = p["lud"]; k = p["klasa"]; lud += l
        if k in ("oba", "tylko_osm"): osm += l
        if k in ("oba", "tylko_bdot"): bdot += l
    nazwa = g["nazwa"]
    rows.append((nazwa, 100 * osm / lud, 100 * bdot / lud, lud))
rows.sort(key=lambda r: r[2] - r[1])          # największy zysk na górze (ostatni rysowany wyżej)

plt.rcParams.update({"font.family": "Helvetica Neue", "font.size": 8.5, "svg.fonttype": "none"})
fig, ax = plt.subplots(figsize=(10.6, 3.15))
INK, MUTED, OSM, BDOT = "#1d232a", "#6b7480", "#8f9aa6", "#e08a00"
for i, (n, o, b, l) in enumerate(rows):
    ax.plot([o, b], [i, i], color="#d9dde2", lw=3.2, solid_capstyle="round", zorder=1)
    ax.scatter([o], [i], s=26, color=OSM, zorder=2, edgecolor="white", lw=0.8)
    ax.scatter([b], [i], s=34, color=BDOT, zorder=3, edgecolor="white", lw=0.8)
    if abs(b - o) < 0.5:
        ax.text(b - 1.6, i, "bez różnicy (miasto)", va="center", ha="right", fontsize=7.6, color=MUTED)
    elif b - o >= 0.5:
        ax.text(b + 1.2, i, "+" + f"{b - o:.1f}".replace(".", ",") + " p.p.", va="center", fontsize=7.6, color=INK)
ax.set_yticks(range(len(rows)), [r[0] for r in rows], color=INK)
ax.set_xlim(30, 104); ax.set_xticks(range(30, 101, 10), [f"{x}%" for x in range(30, 101, 10)], color=MUTED)
ax.grid(axis="x", color="#eceef1", lw=0.8); ax.set_axisbelow(True)
for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color("#c9ced4"); ax.tick_params(length=0)
ax.set_xlabel("odsetek mieszkańców gminy w zasięgu 15 min", color=MUTED, fontsize=8)
ax.scatter([], [], s=26, color=OSM, label="OpenStreetMap"); ax.scatter([], [], s=34, color=BDOT, label="BDOT10k (GUGiK)")
ax.legend(loc="lower left", bbox_to_anchor=(0.0, 0.0), frameon=False, ncol=2, fontsize=8, handletextpad=0.3)
fig.tight_layout(pad=0.4)
fig.savefig(f"{K}/mapy/wykres_gmin.svg", transparent=True, metadata={"Creator": None, "Date": None, "Format": None, "Type": None})
fig.savefig(f"{K}/mapy/wykres_gmin.png", dpi=200, transparent=False, facecolor="white", metadata={"Software": None})
for r in rows[::-1]: print(f"{r[0]:22s} OSM {r[1]:5.1f}  BDOT {r[2]:5.1f}  lud {r[3]:7.0f}")
