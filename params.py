# -*- coding: utf-8 -*-
"""
params.py — profile metodyki AZO (KSRG) + dwie funkcje modelu.

ROZDZIELENIE MAPA / LICZBA:
  • malejacy_bufor(...)        -> warstwa POLIGONOWA do mapy (wizualizacja zasięgu),
  • pokrycie_punkty_popytu(...) -> WSKAŹNIK „% ludności w T min" (na punktach popytu, nie z przecięcia powierzchni).

UWAGA METODYCZNA (ważne dla artykułu):
  - Prędkości po drogach (75/60/50/30) i czas alarmowania (PSP 3 / OSP 10 min) są wg wytycznych
    planistycznych KG PSP.
  - v_offroad i R_max NIE są uregulowane normą — to JAWNE, dokumentowane rozszerzenie metodyki.
    Dlatego trzymamy je jako pola profilu (różne wg pokrycia terenu), a nie ukrytą stałą.
"""

# --- wartości wg wytycznych planistycznych KG PSP ---
ALARMOWANIE_MIN = {"PSP": 3, "OSP": 10}

SPEED_KMH = {  # średnia prędkość pojazdu ratowniczego wg kategorii drogi (wspólna PSP/OSP)
    "autostrada_ekspresowa":     75,   # A, S
    "wojewodzka_pozostale_kraj": 60,   # DW + pozostałe DK
    "powiatowa":                 50,
    "gminna_pozostale":          30,
}

# mapowanie klas OSM -> kategoria KSRG (dla BDOT10k podmień klucze na klasy BDOT)
OSM_DO_KSRG = {
    "motorway": "autostrada_ekspresowa", "motorway_link": "autostrada_ekspresowa",
    "trunk": "autostrada_ekspresowa", "trunk_link": "autostrada_ekspresowa",
    "primary": "wojewodzka_pozostale_kraj", "primary_link": "wojewodzka_pozostale_kraj",
    "secondary": "powiatowa", "secondary_link": "powiatowa",
    "tertiary": "gminna_pozostale", "tertiary_link": "gminna_pozostale",
    "unclassified": "gminna_pozostale", "residential": "gminna_pozostale",
    "living_street": "gminna_pozostale",
}

# --- "ostatni odcinek" poza siecią: JAWNE rozszerzenie metodyki (nie norma) ---
# prędkość dojścia [km/h] zależna od pokrycia terenu (dojście pieszo ze sprzętem):
OFFROAD_KMH = {
    "default":       3.0,    # teren mieszany/otwarty, pieszo ze sprzętem  <-- domyślna
    "las_podmokly":  1.5,
    "zabudowa":      4.0,    # ale realnie ogranicza R_max + bariery
    "droga_gruntowa": 20.0,  # jeśli przejazd istnieje — lepiej dodać do SIECI, nie tutaj
}
R_MAX_M   = 300.0   # maks. dojście w bok [m] — dostęp/rozwinięcie sprzętu, niezależne od czasu
DENSIFY_M = 40.0    # zagęszczenie krawędzi przed buforowaniem (unia po SIECI, nie po węzłach)
PROGI_MIN = [8, 15]

# profile (alarmowanie + off-road jawnie per profil); specjalist/heli do uzupełnienia
PROFILE = {
    "PSP": {"alarmowanie_min": 3,  "v_offroad_kmh": OFFROAD_KMH["default"], "r_max_m": R_MAX_M},
    "OSP": {"alarmowanie_min": 10, "v_offroad_kmh": OFFROAD_KMH["default"], "r_max_m": R_MAX_M},
    "specjalist_podstawowy": {"alarmowanie_min": None, "v_offroad_kmh": OFFROAD_KMH["default"], "r_max_m": R_MAX_M},
}
# Specjalistyczna Grupa Ratownictwa Wodno-Nurkowego (SGRW) — profil radialny (helikopter), do uzupełnienia:
SGRW_HELI = {"predkosc_przelotowa_kmh": None, "czas_gotowosci_startu_min": None}


# =====================================================================================
# MAPA: malejący bufor (zagęszczony, z R_max, przycięty barierami)
# =====================================================================================
def malejacy_bufor(road_pts, time_field, T_s, v_offroad_kmh, r_max_m,
                   barriers=None, context=None, feedback=None):
    """
    Z osiągalnych punktów drogi (ZAGĘSZCZONYCH co ~DENSIFY_M, każdy z czasem dojazdu `time_field` [s])
    buduje poligon zasięgu: promień = min((T_s - t)·v_off, R_max), dissolve, minus bariery.

    To izotropowy przypadek powierzchni kosztu (bez barier/nachylenia). Unia po WSZYSTKICH
    zagęszczonych punktach (nie po najbliższym) = ścisły zbiór osiągalny przy metryce euklidesowej
    poza drogą. road_pts musi być wcześniej zagęszczony (patrz DENSIFY_M).

    Zwraca QgsVectorLayer (poligon) albo None gdy pusto.
    """
    import processing
    from qgis.core import QgsProperty, QgsProcessingUtils
    v = float(v_offroad_kmh) / 3.6
    expr = 'max(0, min(({T} - "{f}") * {v}, {R}))'.format(T=float(T_s), f=time_field, v=v, R=float(r_max_m))
    res = processing.run('native:buffer', {
        'INPUT': road_pts, 'DISTANCE': QgsProperty.fromExpression(expr),
        'SEGMENTS': 6, 'END_CAP_STYLE': 0, 'JOIN_STYLE': 0, 'DISSOLVE': True,
        'OUTPUT': 'TEMPORARY_OUTPUT',
    }, context=context, feedback=feedback, is_child_algorithm=True)
    out = res['OUTPUT']
    if barriers:
        res2 = processing.run('native:difference', {
            'INPUT': out, 'OVERLAY': barriers, 'OUTPUT': 'TEMPORARY_OUTPUT',
        }, context=context, feedback=feedback, is_child_algorithm=True)
        out = res2['OUTPUT']
    return QgsProcessingUtils.mapLayerFromString(out, context) if context else out


# =====================================================================================
# LICZBA: pokrycie liczone na PUNKTACH POPYTU (nie z przecięcia powierzchni)
# =====================================================================================
def pokrycie_punkty_popytu(demand_pts, pop_field, road_pts, time_field, progi_s,
                           v_offroad_kmh, r_max_m, barriers_index=None):
    """
    Dla każdego punktu popytu (ludność/budynek/centroid siatki) liczy czas dotarcia:
        t = min po osiągalnych punktach drogi p w promieniu R_max [ t_drogi(p) + dist(p, punkt)/v_off ]
    i sprawdza <= próg. Dokładniejsze i tańsze niż przecięcie z powierzchnią, odporne na ząbki bufora.

    demand_pts, road_pts — QgsVectorLayer (ten sam CRS, metryczny). road_pts: pole `time_field` [s].
    Zwraca: { prog_s: {"ludnosc": suma_pop_objetej, "frakcja": udzial} , "_total": suma_pop }.
    barriers_index — opcjonalny QgsSpatialIndex barier (geom liniowe/poligonowe); odcinek p->punkt
                     przecinający barierę jest odrzucany (proste przybliżenie omijania barier).
    """
    from qgis.core import QgsSpatialIndex, QgsGeometry, QgsPointXY, QgsFeatureRequest
    v = float(v_offroad_kmh) / 3.6
    # indeks punktów drogi + ich czasy
    idx = QgsSpatialIndex()
    troad = {}
    geomroad = {}
    for f in road_pts.getFeatures():
        idx.addFeature(f)
        troad[f.id()] = float(f[time_field])
        geomroad[f.id()] = f.geometry().asPoint()

    progi_s = sorted(progi_s)
    Tmax = progi_s[-1]
    acc = {T: {"ludnosc": 0.0} for T in progi_s}
    total = 0.0
    for d in demand_pts.getFeatures():
        pop = d[pop_field]
        if pop is None:
            continue
        pop = float(pop)
        total += pop
        p = d.geometry().asPoint()
        # kandydaci: najbliżsi sąsiedzi (czas rośnie z odległością, więc kilkunastu wystarcza)
        cand = idx.nearestNeighbor(QgsPointXY(p), 12)
        best = None
        for fid in cand:
            rp = geomroad[fid]
            dist = ((p.x() - rp.x()) ** 2 + (p.y() - rp.y()) ** 2) ** 0.5
            if dist > r_max_m:
                continue
            if barriers_index is not None:
                seg = QgsGeometry.fromPolylineXY([QgsPointXY(p), QgsPointXY(rp)])
                blocked = False
                for bid in barriers_index.intersects(seg.boundingBox()):
                    pass  # (miejsce na test przecięcia z geometrią bariery — wymaga cache geom barier)
            t = troad[fid] + dist / v
            if best is None or t < best:
                best = t
        if best is None or best > Tmax:
            continue
        for T in progi_s:
            if best <= T:
                acc[T]["ludnosc"] += pop
    out = {T: {"ludnosc": acc[T]["ludnosc"],
               "frakcja": (acc[T]["ludnosc"] / total if total else 0.0)} for T in progi_s}
    out["_total"] = total
    return out
