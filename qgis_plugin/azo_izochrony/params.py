# -*- coding: utf-8 -*-
"""
Parametry domyślne AZO — wartości „do celów planistycznych" (KG PSP) + reżimy prędkości.

Pojedyncze źródło prawdy dla wszystkich algorytmów wtyczki. Wartości zgodne z manuskryptem
(ZN SGSP / Akademia Pożarnicza). Edytowalne w UI każdego algorytmu; tu są tylko domyślne.
"""

# --- Reżimy prędkości (SPEED_MODE) ----------------------------------------------------
# planistyczny  — prędkość z KATEGORII drogi (A/S=75, DK/DW=60, DP=50, gminna=30). DOMYŚLNY,
#                 zgodny z KG PSP/artykułem, porównywalny między komendami.
# operacyjny    — prędkość = współczynnik × vmax (docelowo kalibracja na czasach SWD-ST).
#                 Bardziej realistyczny/konserwatywny; jawnie udokumentowana opcja.
# dopuszczalny  — vmax wprost. TYLKO do porównania / reżim „naiwny" — zawyża pokrycie
#                 (w artykule błąd „stosowania prędkości dopuszczalnych", ~+9–10 p.p.).
SPEED_MODES = ['planistyczny', 'operacyjny', 'dopuszczalny']
DEFAULT_SPEED_MODE = 0          # indeks w SPEED_MODES → 'planistyczny'
OPERATIONAL_FACTOR = 0.85       # operacyjny: v = OPERATIONAL_FACTOR × vmax

# --- Prędkości planistyczne wg KLASY drogi [km/h] -------------------------------------
# Klucze OSM `highway` (dane demonstracyjne). Mapują na kategorie: motorway/trunk = A/S = 75,
# primary = DK/DW = 60, secondary = DP = 50, tertiary/niżej = gminna/pozostałe = 30.
DEF_SPEEDS = [
    'motorway', 75, 'trunk', 75, 'primary', 60, 'secondary', 50,
    'tertiary', 30, 'unclassified', 30, 'residential', 30, 'living_street', 30,
    'motorway_link', 75, 'trunk_link', 75, 'primary_link', 60,
    'secondary_link', 50, 'tertiary_link', 30,
]
# Prędkości planistyczne wg KATEGORII drogi PL [km/h] (sieć operacyjna/BDOT10k, pole `ref`/kategoria).
DEF_SPEEDS_CAT = [
    'A', 75, 'S', 75, 'DK', 60, 'DW', 60, 'DP', 50, 'DG', 30, 'gminna', 30,
]
DEFAULT_SPEED = 30.0            # klasa/kategoria spoza tabeli → najniższa

# --- Czas alarmowania [min] wg typu jednostki (TURNOUT) -------------------------------
# JRG/PSP = 3 min (180 s), OSP w KSRG = 10 min (600 s).
DEF_ALARM = ['JRG', 3, 'PSP', 3, 'OSP-KSRG', 10, 'OSP', 10]
DEFAULT_ALARM = 10.0           # typ spoza tabeli → traktuj jak OSP

# --- Ostatni odcinek dojścia (malejący bufor) ----------------------------------------
DEFAULT_OFFROAD_KMH = 3.0      # v_poza (artykuł): pieszo/teren = 3 km/h
DEFAULT_RMAX_M = 300.0         # R_max: maks. dojście poza drogą

# Drogi o OGRANICZONYM DOSTĘPIE (autostrady/ekspresówki). Nadal przewożą czas jazdy,
# ale NIE generują „dojścia poza drogą" (R_max=0) — z jezdni nie zejdziesz do zdarzenia
# poza węzłem, więc 300 m pasa wzdłuż A/S byłoby fikcją obszaru obsłużonego.
DEF_NO_OFFROAD_CLASSES = 'motorway,trunk,motorway_link,trunk_link,A,S'

# --- Progi czasu dotarcia [min] ------------------------------------------------------
# 15 min — projekt rozporządzenia, jedyny wiążący próg (DOMYŚLNY).
# 8 min  — pomocniczy (obowiązujący §8, wycofywany; przy alarmowaniu OSP 10 min osiągalny tylko dla JRG).
THRESHOLD_PRESETS = ['15', '8', '8,15']
DEFAULT_THRESHOLDS = '15'

# --- Bufor naiwny (do porównania Δ z artykułem) --------------------------------------
DEFAULT_NAIVE_BUFFER_M = 250.0  # stały bufor bez barier — wariant „naiwny"

# --- CRS -----------------------------------------------------------------------------
CRS_COMPUTE = 'EPSG:32634'      # licz w metrycznym (UTM 34N)
CRS_DISPLAY = 'EPSG:2180'       # wyświetlaj w PUWG 1992
