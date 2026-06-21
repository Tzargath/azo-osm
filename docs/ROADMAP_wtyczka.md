# Roadmap poprawek wtyczki „Izochrony AZO (PSP)"

Rekon na bazie walidacji v1.1.0 i lekcji z generowania rycin do artykułu (2026-06).
Główny wniosek: pure-Python network analysis w wątku GUI **zamraża QGIS** na minuty przy skali
województwa (130 tys. krawędzi × 280 jednostek) — ta sama ściana, przez którą użytkownicy
przechodzą na ORS. Większość bólu usuwają dwie tanie zmiany (P0).

## ✅ P0 — ZROBIONE w v1.2.0 (2026-06-20)

- **P0.1 superźródło — WDROŻONE** w `algorithm.py`: pętla N-Dijkstr → 1 Dijkstra od sztucznego węzła
  (krawędzie cost=alarmowanie). Zwalidowane: identyczny wynik co v1.1.0 (15 min 1559,3 km², 8 min 252,2 km²),
  tylko szybciej. `nE` zapamiętane przed dodaniem superźródła (krawędzie superźródła pominięte w buforowaniu).
- **P0.2 QgsTask — NIEPOTRZEBNE:** Processing sam uruchamia algorytm w wątku w tle (`QgsProcessingAlgRunnerTask`)
  przy odpaleniu z toolboxa — GUI nie zamarza, `feedback.setProgress`/`isCanceled` (już są) obsługują pasek
  i anulowanie. Zamrażanie z sesji brało się z wywołania w wątku głównym (MCP/`alg.run`), nie z toolboxa.
- **Pozostały koszt = bufor** (zagęszczony malejący, ~1 mln ognisk) — to już P3.11 (wygładzanie/redukcja).

## P0 — Wydajność (oryginalny opis, dla kontekstu)

1. **Superźródło zamiast pętli per jednostka** ⭐ największy zysk.
   - Teraz `algorithm.py` robi `for tp in tied: QgsGraphAnalyzer.dijkstra(...)` → N Dijkstr + pythonowa akumulacja `min` (110 mln iteracji).
   - Zamiast: dodać sztuczny węzeł `sv = graph.addVertex(...)`, dla każdej jednostki `graph.addEdge(sv, tied_v, [alarmowanie_s])`, policzyć **1 Dijkstrę** od `sv`. `cost[v]` = min po jednostkach (alarmowanie + dojazd) = dokładnie to, co liczymy.
   - Zmierzone: **>10 min → 42 s**. Alarmowanie wchodzi „za darmo" jako koszt krawędzi superźródła.
2. **Liczenie w `QgsTask` (osobny wątek)** — dziś blokuje wątek GUI; `QgsTask` → QGIS używalny, pasek postępu realny, anulowanie działa.
3. **Nie konwertować wyniku Dijkstry sip→numpy element po elemencie** — `np.array(cost)` na sekwencji sip iteruje przez granicę C++/Python (wolniejsze niż pętla). Po superźródle to i tak jeden `cost`-array (raz, nieistotne).

## ✅ P1.4 — ZROBIONE w v1.3.0 (2026-06-20)

Drugi algorytm **„Wskaźnik pokrycia ludności (punkty popytu)"** (`wskaznik.py`): % ludności w zasięgu T
liczony na punktach popytu (nie z przecięcia powierzchni), superwęzłem, **barrier-aware** (odcinek dojścia
przecinający barierę odrzucany; bariery eksplodowane na części + indeks przestrzenny). Wyjście: punkty
popytu z polami `lud`/`czas_min`/`pokr_<T>min` + zestawienie %% w logu. **Zwalidowane: 8,8% / 48,3%** —
identycznie jak niezależna analiza. Pozostaje P1.5 (barrier-aware też w buforze mapy) i P1.6 (profile).

## P1 — Metodyka (obronność AZO)

4. **Rozdzielić MAPĘ od LICZBY** — dodać drugi algorytm „Wskaźnik pokrycia (punkty popytu)":
   % ludności **ważony**, liczony na punktach popytu (najbliższy dostęp drogowy + dojście w bok ≤ T),
   nie z przecięcia powierzchni. Implementacja referencyjna: `params.py::pokrycie_punkty_popytu`.
   Dziś wtyczka daje tylko poligon (mapę).
5. **Barrier-aware off-road** — odrzucać dojście, którego odcinek przecina barierę (rzeka/tory);
   euklidesowe `dist/v_off` nadal „przeskakuje rzekę". Dotyczy bufora i wskaźnika; istotne w GZM.
6. **Profile PSP/OSP/specjalist** z jawnymi `v_offroad` + `r_max` per profil (w `params.py`).
   Prędkości pojazdu wspólne; różnica PSP↔OSP = **czas alarmowania** (3 / 10 min), nie prędkość.

## P2 — Funkcje

7. **Backend ORS/Valhalla (self-hosted)** jako opcja dla dużej skali/produkcji — szybki,
   wielordzeniowy, nie zamraża, natywnie omija rzeki (routing po realnej sieci). Wymaga klucza/URL.
8. **Profil helikoptera SGRW** (radialny: prędkość przelotowa + czas gotowości startu) — parked,
   `params.py::SGRW_HELI` (wartości None).
9. **Opcjonalne wyjście „węzły drogi z czasem"** — do wskaźnika i dalszych analiz.
10. **Mapowanie klas BDOT10k** — dziś `highway` OSM; dla danych urzędowych dodać tablicę BDOT→prędkość.

## P3 — Polish / odporność

11. ✅ **ZROBIONE w v1.3.1** — filtr min. powierzchni wysepek [ha] (param `MIN_AREA`, dom. 1 ha)
    + wygładzanie krawędzi (`SMOOTH`, geom.smooth). Walidacja: 7826→63 części (8 min) i 5058→41 (15 min)
    przy stracie pola <2,5% — mapa publikacyjnie czysta.
12. **Postęp w budowie grafu** — `makeGraph` nie raportuje (wygląda jak zawieszenie).
13. **Tryb rastrowy `r.walk`** (nachylenie — Beskidy; bariery) jako zaawansowany; hybryda
    wektor (szybka sieć) → raster tylko ostatni odcinek.
14. **Rejestracja providera** — w realnej instalacji OK; w skryptach trzeba trzymać referencję
    (GC zjadał provider → trzeba było `alg.run` bezpośrednio).

## Kolejność wdrożenia

**P0.1 + P0.2** (superźródło + QgsTask) — 90% bólu, tanie, **najpierw**.
Potem **P1.4 + P1.5** (liczba + barrier-aware) — rdzeń obronności AZO.
Reszta wg potrzeb.
