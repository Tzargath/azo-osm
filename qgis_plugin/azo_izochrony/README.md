# Izochrony AZO (PSP) — wtyczka QGIS (v1.3.0)

Analiza zabezpieczenia operacyjnego straży: **jak szybko jednostki docierają na miejsce zdarzenia
i ile osób mieści się w tym zasięgu.** Dodaje do panelu **Processing** dwa narzędzia (grupa
*AZO — zabezpieczenie operacyjne → Analiza sieciowa*). W pełni **offline, bez kluczy API** —
odpowiednie dla danych służbowych.

## Instalacja
- **Z pliku ZIP:** `Wtyczki → Zarządzaj wtyczkami → Zainstaluj z ZIP →` wskaż `azo_izochrony.zip`.
- **Ręcznie:** skopiuj katalog `azo_izochrony/` do `…/QGIS3/profiles/default/python/plugins/`,
  uruchom ponownie QGIS i włącz wtyczkę.

---

## Narzędzie 1 — „Izochrony dojazdu (AZO)" → MAPA
Tworzy **warstwę poligonową stref czasu dotarcia** (np. 8 i 15 min) od jednostek.

Model czasu: **czas dotarcia = alarmowanie (wg typu) + jazda po drogach + dojście poza drogą.**
- **Alarmowanie** per typ jednostki (np. JRG/PSP 3 min, OSP 10 min) — przy 8 min OSP automatycznie
  „odpada" (nie zmobilizuje się w czasie), więc próg 8-min staje się de facto „tylko-JRG".
- **Jazda po drogach** z prędkościami wg klasy drogi (np. planistyczne KG PSP 75/60/50/30 km/h) —
  wpisywane w tabeli w oknie, **bez przygotowywania sieci** (czyta surowe drogi OSM/BDOT10k).
- **Dojście poza drogą = MALEJĄCY BUFOR:** promień wokół drogi maleje z budżetem czasu
  `(T − czas dojazdu)·v_dojścia`, z twardym limitem `R_max`. Zdarzenie X m od drogi „łapie się"
  tylko, jeśli dojazd był odpowiednio szybki; strefa zwęża się ku granicy zasięgu zamiast być
  wszędzie równej szerokości.
- **Bariery** (rzeki, tory) opcjonalnie przycinają strefę, żeby nie „przeskakiwała" cieku bez mostu.

## Narzędzie 2 — „Wskaźnik pokrycia ludności (punkty popytu)" → LICZBA
Zwraca **% ludności w zasięgu T** (wskaźnik do AZO), liczony **na punktach popytu**, nie z przecięcia
powierzchni: dla każdego punktu sprawdza `czas_dojazdu_do_najbliższej_drogi + dojście ≤ T`, odrzucając
dojścia przecinające barierę. Wynik: warstwa punktów (pole `lud`, `czas_min`, `pokr_<T>min`) oraz
zestawienie %% w logu. Dokładniejsze i tańsze niż liczenie z mapy, odporne na bariery.

---

## Silnik
- **Superwęzeł:** zamiast Dijkstry osobno z każdej z N jednostek — jeden sztuczny węzeł z krawędziami
  do wszystkich jednostek o koszcie = czas alarmowania → **1 Dijkstra**. `cost[v]` = czas dotarcia
  najszybszej dostępnej jednostki, z automatycznym wyborem najbliższej. Skala województwa:
  minuty → kilkadziesiąt sekund.
- **Wątek w tle** (Processing) — QGIS nie zamarza, działa pasek postępu i anulowanie.

## Parametry (wspólne dla obu narzędzi)
| parametr | opis |
|---|---|
| Sieć dróg | linie w układzie **metrycznym** (UTM/EPSG:2180, nie 4326) |
| Pole klasy drogi | np. `highway` (OSM) lub klasa BDOT10k |
| Prędkości [km/h] | tabela klasa drogi → km/h (w oknie) |
| Jednostki + pole typu | punkty + pole do czasu alarmowania |
| Czas alarmowania [min] | tabela typ → min (np. JRG 3, OSP-KSRG 10) |
| Progi czasu [min] | np. `8,15` |
| Prędkość dojścia [km/h], `R_max` [m] | „ostatni odcinek" poza drogą |
| Bariery | opcjonalne (rzeki, tory) |
| *(Narz. 2)* Punkty popytu + pole ludności | siatka/budynki z wagą; puste = po 1 |

## Cechy
- **Offline, bez API** — bezpieczne dla danych służbowych.
- **Bez przygotowywania sieci** — prędkości z tabeli, keyed na klasie drogi.
- **Jawne, dokumentowane parametry off-road** (`v_dojścia`, `R_max`) — KG PSP reguluje tylko prędkości
  po drogach; off-road to rozszerzenie metodyki.

## Czego NIE robi / zastrzeżenia
- Model „dojazd od najbliższej jednostki przy swobodnym ruchu" — **nie uwzględnia** gotowości i obsad,
  jednoczesnych zdarzeń, korków, pory doby, pogody.
- Prędkości **planistyczne, nie operacyjne** → wynik to raczej **górna granica** pokrycia.
- **Materiał poglądowy.** Do celów urzędowych: sieć **BDOT10k**, ludność **GUS**, lokalizacje i gotowość
  jednostek z **KW/KP PSP**.

## Roadmap
Patrz `docs/ROADMAP_wtyczka.md`: P0 (superwęzeł) ✅, P1.4 (wskaźnik) ✅; dalej P1.5 (barrier-aware
w buforze mapy), P1.6 (profile PSP/OSP/specjalist), P2 (backend ORS/Valhalla, SGRW-heli, BDOT10k),
P3 (wygładzanie fragmentacji bufora, r.walk).
