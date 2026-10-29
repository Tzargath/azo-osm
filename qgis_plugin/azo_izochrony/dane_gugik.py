# -*- coding: utf-8 -*-
"""
Algorytm Processing: Dane GUGiK dla powiatu (BDOT10k + NMT).

PO CO. Dotąd wtyczka LICZYŁA, ale dane trzeba było przygotować samemu — a to jest
w praktyce największa bariera wejścia: zanim ktokolwiek policzy zasięg ratownictwa dla
swojego powiatu, musi znaleźć BDOT10k, rozpakować GML, wybrać właściwe klasy obiektów
i zrozumieć, które pole niesie kategorię drogi. Ten algorytm robi to jednym wywołaniem:
podajesz TERYT powiatu, dostajesz gotowy GeoPackage i (opcjonalnie) NMT.

ŹRÓDŁA — wyłącznie publiczne dane i usługi GUGiK:
  • BDOT10k  — opendata.geoportal.gov.pl, paczka GML per powiat (bezpłatna, bez logowania)
  • NMT 1 m / siatka — usługa **WCS** Geoportalu (DTM_PL-EVRF2007-NH)

CO WYCHODZI (warstwy w GeoPackage, nazwy jak w BDOT10k):
  OT_SKJZ_L  jezdnie            → sieć drogowa; pole `kategoriaZarzadzania` niesie
                                  kategorię URZĘDOWĄ (krajowa/wojewódzka/powiatowa/
                                  gminna/wewnętrzna) — to ona zastępuje zgadywanie
  OT_BUBD_A  budynki            → punkty popytu (budynki mieszkalne)
  OT_ADMS_P  miejscowości       → ludność do rozłożenia na budynki
  OT_ADJA_A  granice gmin       → agregacja wyniku
  OT_SWRS_L  cieki              ⎫
  OT_PTWP_A  wody powierzchniowe⎬ bariery
  OT_SKTR_L  tory               ⎭

⛔⛔ PUŁAPKI USŁUG GEOPORTALU — ZMIERZONE, NIE WYCZYTANE:
 1. WCS oczekuje osi x = WSCHODNIA, y = PÓŁNOCNA (odwrotnie niż sugeruje kolejność
    w EPSG:2180). Zamiana osi NIE daje błędu HTTP — daje poprawnie wyglądający,
    pusty raster.
 2. Poza granicą Polski usługa zwraca 0 zamiast braku danych ⇒ ustawiamy nodata 0.
 3. Serwis bywa przeciążony i na TO SAMO żądanie oddaje raz obraz, raz pustkę, raz 404.
    ⇒ każdy kafel jest sprawdzany i ponawiany; 404 traktujemy jak „zwolnij", nie „nie ma".
 4. ⛔ GDAL zapisuje policzone statystyki rastra w pliku obok (`.aux.xml`) i przy
    kolejnym otwarciu CZYTA JE ZAMIAST LICZYĆ. Jeden pusty kafel zostawia sidecar,
    który skazuje tę nazwę pliku na zawsze — sprawdzanie „czy kafel ma dane" ocenia
    wtedy nie ten plik, co trzeba. ⇒ sidecar kasowany PRZED każdą oceną.

W pełni offline po pobraniu: dalsze algorytmy nie wymagają sieci.
"""
import math
import os
import shutil
import tempfile
import ssl
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessingAlgorithm, QgsProcessingException,
    QgsProcessingParameterString, QgsProcessingParameterBoolean,
    QgsProcessingParameterNumber, QgsProcessingParameterFileDestination,
    QgsProcessingParameterFolderDestination, QgsProcessingOutputString,
    QgsVectorLayer, QgsVectorFileWriter, QgsCoordinateTransformContext,
)

EPSG = 2180
OPENDATA = "https://opendata.geoportal.gov.pl/bdot10k/schemat2021/{woj}/{teryt}_GML.zip"
WCS_NMT = ("https://mapy.geoportal.gov.pl/wss/service/PZGIK/NMT/GRID1/WCS/"
           "DigitalTerrainModel")
WARSTWA_NMT = "DTM_PL-EVRF2007-NH"

# klasy BDOT10k, których potrzebują algorytmy tej wtyczki
KLASY = ["OT_SKJZ_L", "OT_SWRS_L", "OT_PTWP_A", "OT_SKTR_L",
         "OT_BUBD_A", "OT_ADJA_A", "OT_ADMS_P"]

PONOWIENIA = 6
LIMIT_S = 180


class _BladHTTP(RuntimeError):
    """Odpowiedź 4xx/5xx z usługi. ⚠ Rozróżniamy ją od błędu sieci, bo 404 z opendata
    znaczy zwykle ZŁY TERYT, a 404 z WCS bywa przejściowe („zwolnij")."""

    def __init__(self, kod):
        super().__init__(f'HTTP {kod}')
        self.kod = kod


class DaneGugikAlgorithm(QgsProcessingAlgorithm):
    TERYT = 'TERYT'
    OUTPUT = 'OUTPUT'
    NMT = 'NMT'
    NMT_RES = 'NMT_RES'
    NMT_KAT = 'NMT_KAT'

    def tr(self, s):
        return QCoreApplication.translate('DaneGugik', s)

    def createInstance(self):
        return DaneGugikAlgorithm()

    def name(self):
        return 'dane_gugik'

    def displayName(self):
        return self.tr('Dane GUGiK dla powiatu (BDOT10k + NMT)')

    def group(self):
        return self.tr('AZO')

    def groupId(self):
        return 'azo'

    def shortHelpString(self):
        return self.tr(
            'Pobiera komplet danych wejściowych dla WSKAZANEGO POWIATU prosto z publicznych '
            'zasobów GUGiK i przygotowuje je do analizy zasięgu ratownictwa.\n\n'
            '• BDOT10k (opendata GUGiK) → GeoPackage: jezdnie z KATEGORIĄ ZARZĄDZANIA '
            '(krajowa/wojewódzka/powiatowa/gminna/wewnętrzna) i nawierzchnią, budynki, '
            'miejscowości z ludnością, granice gmin, cieki, wody i tory jako bariery.\n'
            '• NMT z usługi WCS Geoportalu (opcjonalnie) → model dojścia pieszego zależnego '
            'od nachylenia.\n\n'
            'TERYT powiatu to 4 cyfry, np. 2417 (żywiecki), 1465 (m.st. Warszawa).\n\n'
            'Po pobraniu dalsze algorytmy działają w pełni offline. '
            'Dane GUGiK są bezpłatne i nie wymagają logowania.')

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterString(
            self.TERYT, self.tr('TERYT powiatu (4 cyfry, np. 2417)'), defaultValue=''))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT, self.tr('GeoPackage wyjściowy'),
            fileFilter='GeoPackage (*.gpkg)'))
        self.addParameter(QgsProcessingParameterBoolean(
            self.NMT, self.tr('Pobierz także NMT (usługa WCS) — dla dojścia zależnego od nachylenia'),
            defaultValue=False))
        self.addParameter(QgsProcessingParameterNumber(
            self.NMT_RES, self.tr('Rozdzielczość NMT [m]'),
            QgsProcessingParameterNumber.Double, defaultValue=10.0, minValue=1.0, maxValue=100.0))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.NMT_KAT, self.tr('Katalog na NMT (gdy pobierany)'), optional=True))

    # ── pomocnicze ───────────────────────────────────────────────────────────
    @staticmethod
    def _kontekst_ssl():
        """Zestaw certyfikatów do HTTPS.

        ⛔⛔ DOMYŚLNY KONTEKST NIE WYSTARCZA. Python z pakietu QGIS na macOS wywala się
        na `CERTIFICATE_VERIFY_FAILED` przy opendata.geoportal.gov.pl — zmierzone,
        mimo 128 CA w domyślnym magazynie. `certifi` (dołączany do QGIS) przechodzi.
        ⚠ Gdy `certifi` nie ma, próbujemy domyślnego — lepiej spróbować i dostać czytelny
        błąd niż odmówić z góry.
        ⚠ Rozważany był `QgsBlockingNetworkRequest` (znałby proxy z QGIS-a), ale wymaga
        działającej pętli zdarzeń — w teście poza GUI oddawał 0 bajtów i „device not open".
        Nie wysyłam kodu, którego nie umiem sprawdzić.
        """
        try:
            import certifi
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:  # noqa: BLE001
            return ssl.create_default_context()

    def _pobierz_do_pliku(self, url, cel, feedback, etykieta=''):
        """Pobiera STRUMIENIOWO, z postępem i możliwością przerwania.

        ⚠ Paczka BDOT10k powiatu to kilkanaście–sto kilkadziesiąt MB. Wczytanie całości
        do pamięci działa, ale nie daje ani postępu, ani szansy na anulowanie —
        a użytkownik przy wolnym łączu nie wie wtedy, czy wtyczka pracuje, czy zawisła.
        """
        req = urllib.request.Request(url, headers={'User-Agent': 'QGIS-AZO/1.8'})
        with urllib.request.urlopen(req, timeout=LIMIT_S, context=self._kontekst_ssl()) as r:
            calosc = int(r.headers.get('Content-Length') or 0)
            pobrane = 0
            with open(cel, 'wb') as f:
                while True:
                    if feedback.isCanceled():
                        return 0
                    kawalek = r.read(1 << 18)
                    if not kawalek:
                        break
                    f.write(kawalek)
                    pobrane += len(kawalek)
                    if calosc:
                        feedback.setProgress(int(45 * pobrane / calosc))
        return pobrane

    @staticmethod
    def _pobierz(url, limit=90):
        """Małe żądanie (kafel NMT) — w całości do pamięci."""
        req = urllib.request.Request(url, headers={'User-Agent': 'QGIS-AZO/1.8'})
        try:
            with urllib.request.urlopen(
                    req, timeout=limit,
                    context=DaneGugikAlgorithm._kontekst_ssl()) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            raise _BladHTTP(e.code)

    def processAlgorithm(self, parameters, context, feedback):
        teryt = (self.parameterAsString(parameters, self.TERYT, context) or '').strip()
        if not (teryt.isdigit() and len(teryt) == 4):
            raise QgsProcessingException(
                self.tr('TERYT powiatu musi mieć dokładnie 4 cyfry (np. 2417). Podano: ') + repr(teryt))
        wyjscie = self.parameterAsFileOutput(parameters, self.OUTPUT, context)
        chce_nmt = self.parameterAsBool(parameters, self.NMT, context)
        res = self.parameterAsDouble(parameters, self.NMT_RES, context)
        kat_nmt = self.parameterAsString(parameters, self.NMT_KAT, context) or os.path.dirname(wyjscie)

        # ── 1. BDOT10k ───────────────────────────────────────────────────────
        url = OPENDATA.format(woj=teryt[:2], teryt=teryt)
        feedback.pushInfo(self.tr('Pobieram BDOT10k: ') + url)
        tmp = tempfile.mkdtemp(prefix='azo_bdot_')
        zipek = os.path.join(tmp, 'bdot.zip')
        try:
            rozmiar = self._pobierz_do_pliku(url, zipek, feedback)
        except urllib.error.HTTPError as e:
            # ⚠ 404 znaczy tu zwykle BŁĘDNY TERYT, a nie awarię — mów to wprost,
            #   zamiast zostawiać użytkownika z surowym kodem HTTP.
            raise QgsProcessingException(
                self.tr('GUGiK nie ma paczki dla TERYT {0} (HTTP {1}). Sprawdź numer powiatu.')
                .format(teryt, e.code))
        except Exception as e:  # noqa: BLE001
            shutil.rmtree(tmp, ignore_errors=True)
            raise QgsProcessingException(self.tr('Nie udało się pobrać BDOT10k: ') + str(e))
        if feedback.isCanceled():
            shutil.rmtree(tmp, ignore_errors=True)
            return {}
        feedback.pushInfo(self.tr('Pobrano {0:.1f} MB').format(rozmiar / 1e6))

        try:
            with zipfile.ZipFile(zipek) as z:
                z.extractall(tmp)

            if os.path.exists(wyjscie):
                os.remove(wyjscie)
            opcje_ctx = QgsCoordinateTransformContext()
            zapisane, puste = [], []
            for i, klasa in enumerate(KLASY):
                if feedback.isCanceled():
                    return {}
                feedback.setProgress(int(60 * i / len(KLASY)))
                plik = self._znajdz(tmp, klasa)
                if not plik:
                    # ⚠ LICZYMY BRAKI. Niektóre powiaty nie mają np. torów — i to jest
                    #   normalne — ale użytkownik ma to ZOBACZYĆ, a nie domyślać się,
                    #   czemu bariery wyszły inaczej, niż się spodziewał.
                    puste.append(klasa)
                    continue
                warstwa = QgsVectorLayer(plik, klasa, 'ogr')
                if not warstwa.isValid() or warstwa.featureCount() == 0:
                    puste.append(klasa)
                    continue
                opcje = QgsVectorFileWriter.SaveVectorOptions()
                opcje.driverName = 'GPKG'
                opcje.layerName = klasa
                opcje.actionOnExistingFile = (
                    QgsVectorFileWriter.CreateOrOverwriteFile if not zapisane
                    else QgsVectorFileWriter.CreateOrOverwriteLayer)
                err = QgsVectorFileWriter.writeAsVectorFormatV3(warstwa, wyjscie, opcje_ctx, opcje)
                if err[0] != QgsVectorFileWriter.NoError:
                    raise QgsProcessingException(
                        self.tr('Zapis warstwy {0} nie powiódł się: {1}').format(klasa, err[1]))
                zapisane.append(klasa)
                feedback.pushInfo(f'  {klasa}: {warstwa.featureCount()} obiektów')

            if not zapisane:
                raise QgsProcessingException(
                    self.tr('Paczka BDOT10k nie zawierała żadnej z potrzebnych klas obiektów.'))
            if puste:
                feedback.pushWarning(
                    self.tr('Brak w paczce (pomijam): ') + ', '.join(puste))

            # ── 2. NMT z usługi WCS ──────────────────────────────────────────
            nmt_plik = ''
            if chce_nmt:
                zakres = self._zakres(wyjscie, zapisane)
                if not zakres:
                    feedback.pushWarning(self.tr('Nie ustaliłem zasięgu powiatu — pomijam NMT.'))
                else:
                    nmt_plik = self._nmt(zakres, res, kat_nmt, teryt, feedback)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        feedback.pushInfo(self.tr('\nGotowe. Warstwy: ') + ', '.join(zapisane))
        feedback.pushInfo(self.tr(
            'Sieć drogowa: OT_SKJZ_L, pole kategorii = `kategoriaZarzadzania`.'))
        return {self.OUTPUT: wyjscie, 'NMT': nmt_plik}

    @staticmethod
    def _znajdz(katalog, klasa):
        for korzen, _, pliki in os.walk(katalog):
            for p in pliki:
                if p.endswith(f'_{klasa}.xml'):
                    return os.path.join(korzen, p)
        return None

    @staticmethod
    def _zakres(gpkg, zapisane):
        """Zasięg powiatu z granic gmin (albo z dowolnej zapisanej warstwy)."""
        for klasa in (['OT_ADJA_A'] + zapisane):
            w = QgsVectorLayer(f'{gpkg}|layername={klasa}', klasa, 'ogr')
            if w.isValid() and w.featureCount():
                e = w.extent()
                return e.xMinimum(), e.yMinimum(), e.xMaximum(), e.yMaximum()
        return None

    def _nmt(self, zakres, res, katalog, teryt, feedback):
        """NMT z usługi WCS, kafelkami. Zwraca ścieżkę scalonego pliku (albo '')."""
        from osgeo import gdal
        gdal.UseExceptions()
        os.makedirs(katalog, exist_ok=True)
        w0, p0, w1, p1 = zakres
        margines = 200.0                      # ⚠ zapas, żeby dojście przy granicy miało teren
        w0 -= margines; p0 -= margines; w1 += margines; p1 += margines

        # kafel ~4,5 km — kompromis zmierzony: większe żądania usługa częściej odrzuca
        bok = 4500.0
        kol = max(1, int(math.ceil((w1 - w0) / bok)))
        wier = max(1, int(math.ceil((p1 - p0) / bok)))
        dw, dp = (w1 - w0) / kol, (p1 - p0) / wier
        kafelki, pominiete = [], 0
        razem = kol * wier
        feedback.pushInfo(self.tr('NMT z usługi WCS: {0} kafli').format(razem))

        for k in range(kol):
            for w in range(wier):
                if feedback.isCanceled():
                    return ''
                nr = k * wier + w
                feedback.setProgress(60 + int(38 * nr / razem))
                x0, x1 = w0 + k * dw, w0 + (k + 1) * dw
                y0, y1 = p0 + w * dp, p0 + (w + 1) * dp
                px, py = int(round((x1 - x0) / res)), int(round((y1 - y0) / res))
                cel = os.path.join(katalog, f'_nmt_{teryt}_{k:03d}_{w:03d}.asc')
                if self._kafel(x0, y0, x1, y1, px, py, cel, feedback):
                    kafelki.append(cel)
                else:
                    pominiete += 1

        if not kafelki:
            feedback.pushWarning(self.tr('Usługa WCS nie oddała żadnego kafla NMT.'))
            return ''
        # ⚠ Mów, ILE POMINIĘTO. „Pobrano NMT" bez tej liczby nie odróżnia kompletu od dziury.
        if pominiete:
            feedback.pushWarning(
                self.tr('NMT: {0} z {1} kafli bez danych (poza granicą kraju albo usługa '
                        'odmówiła) — raster ma w tych miejscach nodata.').format(pominiete, razem))

        wynik = os.path.join(katalog, f'nmt_{teryt}.tif')
        vrt = os.path.join(katalog, f'_nmt_{teryt}.vrt')
        gdal.BuildVRT(vrt, kafelki)
        gdal.Translate(wynik, vrt, creationOptions=['COMPRESS=DEFLATE', 'TILED=YES'],
                       noData=0)            # ⛔ poza Polską usługa zwraca 0, nie brak danych
        for p in kafelki + [vrt]:
            try:
                os.remove(p)
            except OSError:
                pass
        feedback.pushInfo(self.tr('NMT zapisany: ') + wynik)
        return wynik

    def _kafel(self, x0, y0, x1, y1, px, py, cel, feedback):
        """Jeden kafel NMT. True = zapisany i ma dane."""
        q = (f'SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage&COVERAGEID={WARSTWA_NMT}'
             # ⛔ x = WSCHODNIA, y = PÓŁNOCNA. Zamiana osi nie daje błędu, daje pustkę.
             f'&SUBSET=x({x0:.3f},{x1:.3f})&SUBSET=y({y0:.3f},{y1:.3f})'
             f'&SUBSETTINGCRS=http://www.opengis.net/def/crs/EPSG/0/{EPSG}'
             f'&FORMAT={urllib.parse.quote("image/x-aaigrid")}'
             f'&SCALESIZE=x({px}),y({py})')
        url = f'{WCS_NMT}?{q}'
        for proba in range(1, PONOWIENIA + 1):
            if feedback.isCanceled():
                return False
            try:
                tresc = self._pobierz(url, limit=90)
                with open(cel, 'wb') as f:
                    f.write(tresc)
                if self._ma_dane(cel):
                    return True
            except Exception as e:  # noqa: BLE001 — 404/timeout traktujemy jak „zwolnij"
                feedback.pushDebugInfo(f'{os.path.basename(cel)} próba {proba}: {e}')
            import time
            time.sleep(min(2 + proba, 8))
        try:
            os.remove(cel)
        except OSError:
            pass
        return False

    @staticmethod
    def _ma_dane(plik):
        """Czy raster niesie cokolwiek poza jedną wartością.

        ⛔⛔ SIDECAR `.aux.xml` KASOWANY PRZED OCENĄ. GDAL zapisuje tam policzone
        statystyki i przy kolejnym otwarciu czyta je ZAMIAST liczyć — jeden pusty kafel
        zostawia wtedy plik, który skazuje tę nazwę na zawsze, a ponowienia oceniają
        nie ten obraz, co trzeba. Zmierzone: cztery kafle przetrwały tak trzy pełne
        przebiegi pobierania.
        """
        from osgeo import gdal
        gdal.UseExceptions()
        for ext in ('.aux.xml',):
            try:
                os.remove(plik + ext)
            except OSError:
                pass
        try:
            ds = gdal.Open(plik)
            if ds is None:
                return False
            b = ds.GetRasterBand(1)
            _, _, _, odch = b.ComputeStatistics(False)
            ds = None
            return odch and odch > 0
        except Exception:  # noqa: BLE001
            return False
