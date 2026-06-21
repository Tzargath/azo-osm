# Izochrony w QGIS bez skryptów — wtyczka QNEAT3 (instrukcja dla PSP)

Alternatywa dla skryptów `02_isochrones.py` + `03_run_buffers.sh`: ten sam efekt (strefy czasu
dojazdu po sieci dróg), ale **klikalnie**, z interpolacją dającą gładsze poligony. Działa
**w 100 % offline** na Twojej sieci dróg — bez wysyłania danych do zewnętrznego serwera.

> [!NOTE]
> QNEAT3 = *Qgis Network Analysis Toolbox 3*. Liczy izochrony na **Twojej** warstwie dróg
> (OSM lub urzędowy **BDOT10k** z GUGiK). Dla zastosowań służbowych zalecany BDOT10k + dane
> jednostek z KW/KP PSP.

---

## 1. Instalacja

`Wtyczki → Zarządzaj wtyczkami i nimi… → wyszukaj „QNEAT3" → Zainstaluj wtyczkę`.

Po instalacji w panelu **Processing** (Przetwarzanie) pojawia się grupa **QNEAT3** z podgrupą
**Iso-Areas**.

## 2. Dane wejściowe

| warstwa | wymóg |
|---|---|
| **Sieć dróg** (linie) | pole z **prędkością** [km/h]; układ **metryczny** (UTM/EPSG:2180 — **nie** 4326!) |
| **Punkty jednostek** | lokalizacje JRG (i/lub OSP-KSRG); ten sam układ co sieć |

Możesz użyć gotowych warstw z repo:
- sieć: `data/network34.gpkg` (pole `speed`, EPSG:32634),
- jednostki: `data/jrg34.gpkg` albo `data/jrgksrg34.gpkg`.

> ⚠️ **Układ metryczny jest kluczowy.** Na danych w EPSG:4326 (stopnie) odległości i czasy wyjdą błędne.
> Jeśli masz dane w 4326 — najpierw `Wektor → Narzędzia zarządzania danymi → Zmień odwzorowanie warstwy`
> na EPSG:2180 (PUWG 1992) lub odpowiednią strefę UTM (32633 zach. / 32634 wsch. Polska).

## 3. Obliczenie izochron

`Processing → QNEAT3 → Iso-Areas →` **„Iso-Area as Polygons (from Layer)"**

| pole | wartość / opis |
|---|---|
| **Network Layer** | warstwa sieci dróg (`network34`) |
| **Start-Points Layer** | punkty jednostek (`jrg34`) |
| **Unique Point ID Field** | dowolne pole identyfikatora (np. `fid`) |
| **Optimization Criterion** | **Fastest Path (time)** — liczymy *czas*, nie odległość |
| **Speed Field** *(sekcja Advanced)* | `speed` (km/h) |
| **Default Speed** *(Advanced)* | np. 50 — dla odcinków bez prędkości |
| **Size of Iso-Area** | maksymalny koszt = **900** (s = 15 min) |
| **Size of Cell** | rozdzielczość rastra interpolacji, **100–150 m** (mniej = gładsze, wolniej) |
| **Tolerance** *(Advanced)* | **25** m — sklejanie węzłów sieci |

**Pasma 8 i 15 min:** najprościej uruchomić algorytm **dwa razy** — z `Size of Iso-Area = 480`
oraz `= 900` — i nałożyć (8 min ciemniejsze na 15 min jaśniejszym), jak w gotowym projekcie.
Jeśli wersja wtyczki ma pole **interwału konturów**, ustaw je tak, by uzyskać progi 480 i 900 s.

Wynik: **warstwa poligonów** stref dojazdu — gotowa do stylizacji (zieleń 8/15 min) i nałożenia na
podkład OSM, dokładnie jak figury w tym repo.

## 4. Jazda alarmowa (sygnały uprzywiejowania)

Izochrona „cywilna" zaniża realny zasięg wozu na sygnale. Podnieś prędkości projektowe:

- **Kalkulator pól** na warstwie sieci: nowe pole `speed_alarm` = `"speed" * 1.25` (np. +25 %),
  i wskaż je jako *Speed Field*; **albo**
- wpisz **własne wartości** z analiz czasów dojazdu Twojej KW/KP (różne dla terenu miejskiego/zamiejskiego).

## 5. Weryfikacja i pułapki

- **Jednostka kosztu:** przy „Fastest + Speed Field" QNEAT3 zwraca koszt w **sekundach** —
  sprawdź na znanym odcinku (1 km autostrady ≈ 30 s przy 120 km/h). Jeśli wyjdą minuty/godziny,
  skoryguj `Size of Iso-Area` odpowiednio.
- **Spójność sieci:** dziury w sieci (rozjazdy bez węzła) ucinają zasięg — pomaga większa *Tolerance*
  oraz narzędzie `Wektor → Geometria → Sprawdź ważność` / dociągnięcie warstwy.
- **Wydajność:** mała *Size of Cell* + dużo punktów = długo. Zacznij od 150 m, zagęszczaj w razie potrzeby.

## QNEAT3 vs skrypty z repo

| | QNEAT3 (wtyczka) | Skrypty `02`/`03` |
|---|---|---|
| Obsługa | klikalna, w oknie | Python + terminal |
| Strefy | interpolowane (gładsze) | bufor sieci 250 m |
| Wiele źródeł naraz | wolniej | szybko (graf budowany raz) |
| Powtarzalność / automat | ręcznie | pełna, skryptowa |
| Próg wejścia dla strażaka | **niski** | wyższy |

**Wniosek:** do pojedynczych analiz i osób unikających Pythona — **QNEAT3**. Do masowych,
powtarzalnych przeliczeń (całe województwo, wiele wariantów) — skrypty z repo.

---

*Dane © OpenStreetMap (ODbL) lub BDOT10k (GUGiK). Materiał poglądowy — patrz zastrzeżenia w głównym README.*
