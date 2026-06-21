# -*- coding: utf-8 -*-
"""
Algorytm Processing: Izochrony dojazdu (AZO) — wersja z malejącym buforem.

Model czasu (od zgłoszenia do dotarcia na miejsce):
    T_dotarcia = czas_alarmowania(typ) + czas_jazdy_po_drogach + dojście_poza_drogą

Kluczowe rozwiązanie problemu "droga to linia, a zdarzenie bywa X m od drogi":
zamiast STAŁEGO bufora, promień wokół każdego punktu drogi MALEJE z czasem —
  promień = (próg − czas_dojazdu_do_tego_punktu) × prędkość_dojścia
Przy jednostce promień duży, na granicy zasięgu maleje do zera (bufor sam się domyka).
Dzięki temu punkt 500 m od drogi „łapie się" tylko, jeśli dojazd do drogi był odpowiednio szybszy.

Prędkości pojazdu liczone wg KLASY drogi (pole w warstwie — np. OSM `highway`), z tabeli w oknie
algorytmu — BEZ przygotowywania sieci. Różnicę PSP/OSP daje czas alarmowania (a nie prędkość).
W pełni offline.
"""
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingException, QgsProcessingUtils,
    QgsProcessingParameterVectorLayer, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField, QgsProcessingParameterNumber, QgsProcessingParameterString,
    QgsProcessingParameterMatrix, QgsProcessingParameterFeatureSink,
    QgsProcessingParameterBoolean, QgsProcessingParameterEnum,
    QgsProcessingParameterDefinition, QgsProperty,
    QgsFields, QgsField, QgsFeature, QgsGeometry, QgsPointXY, QgsWkbTypes,
    QgsVectorLayer, QgsCoordinateTransform, QgsProject, QgsFeatureRequest,
    QgsFillSymbol, QgsCategorizedSymbolRenderer, QgsRendererCategory,
)
import math
from qgis.analysis import (
    QgsVectorLayerDirector, QgsNetworkSpeedStrategy, QgsNetworkStrategy,
    QgsGraphBuilder, QgsGraphAnalyzer,
)


class _OffroadFlagStrategy(QgsNetworkStrategy):
    """Druga „miara" krawędzi = flaga 1/0: czy z tej drogi liczymy dojście poza drogą.
    0 = droga o ograniczonym dostępie (A/S) — przewozi czas, ale bez bufora dojścia."""

    def __init__(self, field_idx):
        super().__init__()
        self._fi = field_idx

    def cost(self, distance, edge):
        try:
            return 1.0 if int(edge.attribute(self._fi)) else 0.0
        except (TypeError, ValueError):
            return 1.0

    def requiredAttributes(self):
        return [self._fi]

# Parametry domyślne — pojedyncze źródło prawdy w params.py (re-eksport dla zgodności:
# jednostki.py / wskaznik.py importują DEF_SPEEDS, DEF_ALARM z tego modułu).
from .params import (
    DEF_SPEEDS, DEF_SPEEDS_CAT, DEF_ALARM, DEFAULT_SPEED, DEFAULT_ALARM,
    SPEED_MODES, DEFAULT_SPEED_MODE, OPERATIONAL_FACTOR,
    DEFAULT_OFFROAD_KMH, DEFAULT_RMAX_M, DEFAULT_THRESHOLDS, DEF_NO_OFFROAD_CLASSES,
)


class IzochronyAZOAlgorithm(QgsProcessingAlgorithm):
    NETWORK = 'NETWORK'
    SPEED_MODE = 'SPEED_MODE'
    CLASS_FIELD = 'CLASS_FIELD'
    SPEEDS = 'SPEEDS'
    VMAX_FIELD = 'VMAX_FIELD'
    OP_FACTOR = 'OP_FACTOR'
    DEFAULT_SPEED = 'DEFAULT_SPEED'
    POINTS = 'POINTS'
    TYPE_FIELD = 'TYPE_FIELD'
    ALARMS = 'ALARMS'
    DEFAULT_ALARM = 'DEFAULT_ALARM'
    THRESHOLDS = 'THRESHOLDS'
    OFFROAD_SPEED = 'OFFROAD_SPEED'
    OFFROAD_MAX = 'OFFROAD_MAX'
    NO_OFFROAD_CLASSES = 'NO_OFFROAD_CLASSES'
    DENSIFY = 'DENSIFY'
    BARRIERS = 'BARRIERS'
    MIN_AREA = 'MIN_AREA'
    SMOOTH = 'SMOOTH'
    TOLERANCE = 'TOLERANCE'
    OUTPUT = 'OUTPUT'

    def tr(self, s):
        return QCoreApplication.translate('IzochronyAZO', s)

    def createInstance(self):
        return IzochronyAZOAlgorithm()

    def name(self):
        return 'izochrony_azo'

    def displayName(self):
        return self.tr('Izochrony dojazdu (AZO) — malejący bufor')

    def group(self):
        return self.tr('Analiza sieciowa')

    def groupId(self):
        return 'analiza'

    def shortHelpString(self):
        return self.tr(
            'Strefy czasu dotarcia jednostek straży na miejsce zdarzenia.\n\n'
            'CZAS = alarmowanie (wg typu) + jazda po drogach (prędkość wg klasy drogi) + '
            'dojście poza drogą.\n\n'
            '• Sieć i punkty w układzie METRYCZNYM (UTM/EPSG:2180), nie 4326.\n'
            '• Prędkości pojazdu wpisujesz w tabeli (klasa drogi → km/h) — BEZ przygotowywania sieci.\n'
            '• Czas alarmowania per typ jednostki (PSP 3 min, OSP 10 min) z tabeli.\n'
            '• MALEJĄCY BUFOR: promień wokół drogi = (próg − czas dojazdu) × prędkość dojścia — '
            'maleje do zera na granicy zasięgu (uwzględnia, że zdarzenie bywa X m od drogi).\n'
            '• Progi czasu w MINUTACH, np. "8,15".\n\n'
            'Profil helikoptera SGRW (radialny, prędkość przelotowa + gotowość startu) — w planach.\n'
            'Materiał poglądowy; do celów służbowych: sieć BDOT10k i dane KW/KP PSP.'
        )

    def _adv(self, p):
        p.setFlags(p.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        return p

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.NETWORK, self.tr('Sieć dróg (linie, układ metryczny)'),
            [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterEnum(
            self.SPEED_MODE, self.tr('Reżim prędkości'),
            options=[self.tr('planistyczny (wg kategorii drogi) — domyślny KG PSP'),
                     self.tr('operacyjny (współczynnik × vmax)'),
                     self.tr('dopuszczalny (vmax wprost) — wariant naiwny, zawyża')],
            defaultValue=DEFAULT_SPEED_MODE))
        self.addParameter(QgsProcessingParameterField(
            self.CLASS_FIELD, self.tr('Pole klasy/kategorii drogi (planistyczny; np. highway / ref)'),
            parentLayerParameterName=self.NETWORK, defaultValue='highway', optional=True))
        self.addParameter(QgsProcessingParameterMatrix(
            self.SPEEDS, self.tr('Prędkości planistyczne [km/h] wg klasy/kategorii drogi'),
            numberRows=len(DEF_SPEEDS) // 2, hasFixedNumberRows=False,
            headers=[self.tr('Klasa/kategoria drogi'), self.tr('km/h')], defaultValue=DEF_SPEEDS))
        self.addParameter(self._adv(QgsProcessingParameterField(
            self.VMAX_FIELD, self.tr('Pole prędkości dopuszczalnej vmax (operacyjny/dopuszczalny)'),
            parentLayerParameterName=self.NETWORK, type=QgsProcessingParameterField.Numeric,
            optional=True)))
        self.addParameter(self._adv(QgsProcessingParameterNumber(
            self.OP_FACTOR, self.tr('Współczynnik operacyjny (× vmax)'),
            QgsProcessingParameterNumber.Double, defaultValue=OPERATIONAL_FACTOR, minValue=0.1, maxValue=1.5)))
        self.addParameter(self._adv(QgsProcessingParameterNumber(
            self.DEFAULT_SPEED, self.tr('Prędkość domyślna [km/h] (klasa/vmax spoza tabeli/brak)'),
            QgsProcessingParameterNumber.Double, defaultValue=DEFAULT_SPEED, minValue=1)))

        self.addParameter(QgsProcessingParameterFeatureSource(
            self.POINTS, self.tr('Jednostki (punkty)'), [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(
            self.TYPE_FIELD, self.tr('Pole typu jednostki (do czasu alarmowania)'),
            parentLayerParameterName=self.POINTS, optional=True))
        self.addParameter(QgsProcessingParameterMatrix(
            self.ALARMS, self.tr('Czas alarmowania [min] wg typu jednostki'),
            numberRows=len(DEF_ALARM) // 2, hasFixedNumberRows=False,
            headers=[self.tr('Wartość pola typu'), self.tr('min')], defaultValue=DEF_ALARM))
        self.addParameter(self._adv(QgsProcessingParameterNumber(
            self.DEFAULT_ALARM, self.tr('Alarmowanie domyślne [min] (typ spoza tabeli)'),
            QgsProcessingParameterNumber.Double, defaultValue=DEFAULT_ALARM, minValue=0)))

        self.addParameter(QgsProcessingParameterString(
            self.THRESHOLDS, self.tr('Progi czasu dotarcia [min] (15 = wiążący; np. "8,15")'),
            defaultValue=DEFAULT_THRESHOLDS))
        self.addParameter(QgsProcessingParameterNumber(
            self.OFFROAD_SPEED, self.tr('Prędkość dojścia/ostatniego odcinka v_poza [km/h]'),
            QgsProcessingParameterNumber.Double, defaultValue=DEFAULT_OFFROAD_KMH, minValue=1,
            ))
        self.addParameter(QgsProcessingParameterNumber(
            self.OFFROAD_MAX, self.tr('Maks. dojście poza drogą R_max [m]'),
            QgsProcessingParameterNumber.Double, defaultValue=DEFAULT_RMAX_M, minValue=0))
        self.addParameter(self._adv(QgsProcessingParameterString(
            self.NO_OFFROAD_CLASSES,
            self.tr('Klasy bez dojścia poza drogą (ograniczony dostęp A/S), po przecinku'),
            defaultValue=DEF_NO_OFFROAD_CLASSES, optional=True)))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.BARRIERS, self.tr('Bariery do odjęcia (rzeki, tory, tereny zamknięte) — opcjonalne'),
            [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorLine], optional=True))
        self.addParameter(self._adv(QgsProcessingParameterNumber(
            self.DENSIFY, self.tr('Zagęszczenie krawędzi [m]'),
            QgsProcessingParameterNumber.Double, defaultValue=40.0, minValue=5)))
        self.addParameter(QgsProcessingParameterNumber(
            self.MIN_AREA, self.tr('Usuń wysepki mniejsze niż [ha] (0 = bez filtra)'),
            QgsProcessingParameterNumber.Double, defaultValue=1.0, minValue=0))
        self.addParameter(self._adv(QgsProcessingParameterBoolean(
            self.SMOOTH, self.tr('Wygładź krawędzie stref'), defaultValue=True)))
        self.addParameter(self._adv(QgsProcessingParameterNumber(
            self.TOLERANCE, self.tr('Tolerancja sklejania węzłów [m]'),
            QgsProcessingParameterNumber.Double, defaultValue=25.0, minValue=0)))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr('Izochrony (poligony)'), QgsProcessing.TypeVectorPolygon))

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _matrix_to_map(values):
        m = {}
        for i in range(0, len(values) - 1, 2):
            try:
                m[str(values[i]).strip()] = float(values[i + 1])
            except (TypeError, ValueError):
                continue
        return m

    # ------------------------------------------------------------------ run
    def processAlgorithm(self, parameters, context, feedback):
        net = self.parameterAsVectorLayer(parameters, self.NETWORK, context)
        if net is None:
            raise QgsProcessingException(self.tr('Brak warstwy sieci dróg.'))
        crs = net.crs()
        if crs.isGeographic():
            raise QgsProcessingException(self.tr(
                'Sieć jest w układzie geograficznym (stopnie). Przerzuć dane do układu metrycznego '
                '(EPSG:2180 lub strefa UTM) — inaczej czasy będą błędne.'))

        class_field = self.parameterAsString(parameters, self.CLASS_FIELD, context)
        speed_kmh = self._matrix_to_map(self.parameterAsMatrix(parameters, self.SPEEDS, context))
        default_speed = self.parameterAsDouble(parameters, self.DEFAULT_SPEED, context)
        speed_mode = self.parameterAsEnum(parameters, self.SPEED_MODE, context)
        mode = SPEED_MODES[speed_mode] if 0 <= speed_mode < len(SPEED_MODES) else SPEED_MODES[0]
        vmax_field = self.parameterAsString(parameters, self.VMAX_FIELD, context)
        op_factor = self.parameterAsDouble(parameters, self.OP_FACTOR, context)
        type_field = self.parameterAsString(parameters, self.TYPE_FIELD, context)
        alarm_min = self._matrix_to_map(self.parameterAsMatrix(parameters, self.ALARMS, context))
        default_alarm = self.parameterAsDouble(parameters, self.DEFAULT_ALARM, context)
        thr_str = self.parameterAsString(parameters, self.THRESHOLDS, context)
        off_kmh = self.parameterAsDouble(parameters, self.OFFROAD_SPEED, context)
        off_max = self.parameterAsDouble(parameters, self.OFFROAD_MAX, context)
        no_off_str = self.parameterAsString(parameters, self.NO_OFFROAD_CLASSES, context) or ''
        no_off_set = {s.strip() for s in no_off_str.replace(';', ',').split(',') if s.strip()}
        densify = self.parameterAsDouble(parameters, self.DENSIFY, context)
        tol = self.parameterAsDouble(parameters, self.TOLERANCE, context)
        barriers_src = self.parameterAsSource(parameters, self.BARRIERS, context)
        barriers_layer = barriers_src.materialize(QgsFeatureRequest()) if barriers_src else None
        min_area_m2 = self.parameterAsDouble(parameters, self.MIN_AREA, context) * 10000.0  # ha -> m2
        smooth = self.parameterAsBool(parameters, self.SMOOTH, context)
        if densify < 5:
            densify = 5.0

        try:
            thresholds = sorted({float(x) for x in thr_str.replace(';', ',').split(',') if x.strip()})
        except ValueError:
            raise QgsProcessingException(self.tr('Progi czasu muszą być liczbami, np. "8,15".'))
        if not thresholds:
            raise QgsProcessingException(self.tr('Podaj co najmniej jeden próg czasu.'))
        off_ms = off_kmh / 3.6

        # --- sieć z prędkością wg klasy (w pamięci — bez ingerencji w dane wejściowe) ---
        feedback.pushInfo(self.tr('Przygotowanie sieci (prędkości wg klasy drogi)…'))
        authid = crs.authid() or crs.toWkt()
        mem = QgsVectorLayer('LineString?crs=' + authid, 'net_v', 'memory')
        pr = mem.dataProvider()
        pr.addAttributes([QgsField('vkmh', QVariant.Double), QgsField('offroad', QVariant.Int)])
        mem.updateFields()
        cidx = net.fields().lookupField(class_field) if class_field else -1
        vidx = net.fields().lookupField(vmax_field) if vmax_field else -1
        if mode in ('operacyjny', 'dopuszczalny') and vidx < 0:
            raise QgsProcessingException(self.tr(
                'Reżim „%s" wymaga pola prędkości dopuszczalnej vmax — wskaż je w parametrach.') % mode)
        feedback.pushInfo(self.tr('Reżim prędkości: %s') % mode)
        feats = []
        for f in net.getFeatures():
            g = f.geometry()
            if g.isEmpty():
                continue
            cls = f[cidx] if cidx >= 0 else None
            cls_s = str(cls).strip() if cls is not None else None
            if mode == 'planistyczny':
                vk = speed_kmh.get(cls_s, default_speed)
            else:
                try:
                    vmax = float(f[vidx]) if vidx >= 0 else None
                except (TypeError, ValueError):
                    vmax = None
                if vmax and vmax > 0:
                    vk = vmax * op_factor if mode == 'operacyjny' else vmax
                else:
                    vk = default_speed
            # ograniczony dostęp (A/S): przewozi czas, ale bez dojścia poza drogą
            offroad = 0 if (cls_s in no_off_set) else 1
            nf = QgsFeature()
            nf.setGeometry(g)
            nf.setAttributes([float(vk) if vk and vk > 0 else default_speed, offroad])
            feats.append(nf)
        pr.addFeatures(feats)
        if mem.featureCount() == 0:
            raise QgsProcessingException(self.tr('Sieć dróg jest pusta.'))

        # --- punkty jednostek + czas alarmowania per jednostka ---
        pts_src = self.parameterAsSource(parameters, self.POINTS, context)
        xform = None
        if pts_src.sourceCrs() != crs:
            xform = QgsCoordinateTransform(pts_src.sourceCrs(), crs,
                                           context.project() or QgsProject.instance())
        points, alarms = [], []
        tidx_names = [fld.name() for fld in pts_src.fields()]
        has_type = bool(type_field) and type_field in tidx_names
        for f in pts_src.getFeatures():
            g = f.geometry()
            if g.isEmpty():
                continue
            if xform:
                g = QgsGeometry(g)
                g.transform(xform)
            points.append(g.asPoint())
            a = default_alarm
            if has_type:
                a = alarm_min.get(str(f[type_field]).strip(), default_alarm)
            alarms.append(a * 60.0)  # sekundy
        if not points:
            raise QgsProcessingException(self.tr('Brak punktów jednostek.'))

        # --- graf + 1 Dijkstra od SUPERŹRÓDŁA (zamiast N Dijkstr per jednostka) ---
        # Sztuczny węzeł z krawędziami do każdej jednostki o koszcie = czas alarmowania.
        # Wtedy cost[v] = min po jednostkach (alarmowanie + dojazd) = czas dotarcia z najszybszej
        # jednostki, z automatycznym wyborem najbliższej. Skala województwa: minuty -> ~kilkadziesiąt s.
        feedback.pushInfo(self.tr('Budowa grafu i analiza dojazdu (superźródło, 1 Dijkstra)…'))
        director = QgsVectorLayerDirector(mem, -1, '', '', '', QgsVectorLayerDirector.DirectionBoth)
        director.addStrategy(QgsNetworkSpeedStrategy(
            mem.fields().lookupField('vkmh'), float(default_speed), 1000.0 / 3600.0))
        director.addStrategy(_OffroadFlagStrategy(mem.fields().lookupField('offroad')))
        builder = QgsGraphBuilder(crs, False, tol)
        tied = director.makeGraph(builder, points)
        graph = builder.graph()
        nV = graph.vertexCount()
        nE = graph.edgeCount()          # krawędzie sieci PRZED superźródłem (do buforowania)
        if feedback.isCanceled():
            return {}

        sv = graph.addVertex(QgsPointXY(0.0, 0.0))
        for i, tp in enumerate(tied):
            tv = graph.findVertex(tp)
            if tv >= 0:
                graph.addEdge(sv, tv, [alarms[i], 0.0])   # [czas alarmowania s, flaga off-road]
        feedback.setProgress(35)
        _, cost = QgsGraphAnalyzer.dijkstra(graph, sv, 0)
        INF = float('inf')
        gmin = [INF] * nV
        for v in range(nV):
            c = cost[v]
            if c >= 0:
                gmin[v] = c
        feedback.pushInfo(self.tr('Graf: %d węzłów, %d krawędzi sieci, %d jednostek (1 Dijkstra).')
                          % (nV, nE, len(tied)))
        feedback.setProgress(55)
        if feedback.isCanceled():
            return {}

        vp = [graph.vertex(v).point() for v in range(nV)]
        edges = []
        for e in range(nE):              # tylko krawędzie sieci (krawędzie superźródła pominięte)
            ed = graph.edge(e)
            edges.append((ed.fromVertex(), ed.toVertex(), ed.cost(0), ed.cost(1)))

        # --- warstwa wynikowa ---
        out_fields = QgsFields()
        out_fields.append(QgsField('prog_min', QVariant.Double))
        out_fields.append(QgsField('rezim', QVariant.String))
        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields, QgsWkbTypes.MultiPolygon, crs)
        if sink is None:
            raise QgsProcessingException(self.tr('Nie udało się utworzyć warstwy wynikowej.'))

        import processing
        # napraw geometrie barier raz (realne wody/BDOT10k bywają niepoprawne →
        # native:difference inaczej przerywa „invalid geometry")
        barriers_overlay = None
        if barriers_layer is not None and barriers_layer.featureCount() > 0:
            barriers_overlay = processing.run(
                'native:fixgeometries', {'INPUT': barriers_layer, 'OUTPUT': 'TEMPORARY_OUTPUT'},
                context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
        thr_sorted = sorted(thresholds, reverse=True)
        for bi, T_min in enumerate(thr_sorted):
            if feedback.isCanceled():
                return {}
            T_s = T_min * 60.0
            # ZAGĘSZCZONE punkty wzdłuż osiągalnych krawędzi, z MALEJĄCYM promieniem dojścia
            # (unia po SIECI, nie po węzłach: czas w punkcie na krawędzi = interpolacja z obu końców)
            rmem = QgsVectorLayer('Point?crs=' + authid, 'r', 'memory')
            rpr = rmem.dataProvider()
            rpr.addAttributes([QgsField('r', QVariant.Double)])
            rmem.updateFields()
            rfeats = []
            for (a, b, et, offr) in edges:
                if offr <= 0:            # A/S: przewozi czas, ale bez dojścia poza drogą
                    continue
                ta = gmin[a]
                tb = gmin[b]
                if min(ta, tb) > T_s:
                    continue
                pa = vp[a]
                pb = vp[b]
                dx = pb.x() - pa.x()
                dy = pb.y() - pa.y()
                seglen = math.hypot(dx, dy)
                nseg = max(1, int(math.ceil(seglen / densify)))
                for k in range(nseg + 1):
                    fr = k / float(nseg)
                    t = min(ta + fr * et, tb + (1.0 - fr) * et)   # dojazd z bliższego końca
                    if t <= T_s:
                        r = (T_s - t) * off_ms
                        if off_max > 0:
                            r = min(r, off_max)
                        if r > 1.0:
                            nf = QgsFeature()
                            nf.setGeometry(QgsGeometry.fromPointXY(
                                QgsPointXY(pa.x() + fr * dx, pa.y() + fr * dy)))
                            nf.setAttributes([r])
                            rfeats.append(nf)
            feedback.pushInfo(self.tr('Próg %.0f min: %d ognisk malejącego bufora.')
                              % (T_min, len(rfeats)))
            if not rfeats:
                continue
            rpr.addFeatures(rfeats)
            res = processing.run('native:buffer', {
                'INPUT': rmem, 'DISTANCE': QgsProperty.fromExpression('"r"'),
                'SEGMENTS': 6, 'END_CAP_STYLE': 0, 'JOIN_STYLE': 0, 'DISSOLVE': True,
                'OUTPUT': 'TEMPORARY_OUTPUT',
            }, context=context, feedback=None, is_child_algorithm=True)
            out_id = res['OUTPUT']
            if barriers_overlay is not None:
                res2 = processing.run('native:difference', {
                    'INPUT': out_id, 'OVERLAY': barriers_overlay, 'OUTPUT': 'TEMPORARY_OUTPUT',
                }, context=context, feedback=None, is_child_algorithm=True)
                out_id = res2['OUTPUT']
            buf = QgsProcessingUtils.mapLayerFromString(out_id, context)
            for bf in buf.getFeatures():
                g = bf.geometry()
                # P3.11 — czyszczenie: usuń drobne wysepki + wygładź krawędzie
                if min_area_m2 > 0 and g.isMultipart():
                    parts = [p for p in g.asGeometryCollection() if p.area() >= min_area_m2]
                    if parts:
                        g = QgsGeometry.unaryUnion(parts)
                    elif g.area() < min_area_m2:
                        continue
                if smooth and not g.isEmpty():
                    sm = g.smooth(2, 0.25)
                    if sm and not sm.isEmpty():
                        g = sm
                of = QgsFeature(out_fields)
                of.setGeometry(g)
                of.setAttributes([round(T_min, 1), mode])
                sink.addFeature(of)
            feedback.setProgress(55.0 + 45.0 * (bi + 1) / len(thr_sorted))

        feedback.pushInfo(self.tr('Gotowe.'))
        self._dest_id = dest_id
        self._bands = sorted(thresholds)
        return {self.OUTPUT: dest_id}

    def postProcessAlgorithm(self, context, feedback):
        # transparentne niebieskie strefy; mniejszy próg ciemniejszy (rysowany na wierzchu)
        try:
            layer = QgsProcessingUtils.mapLayerFromString(self._dest_id, context)
            if layer is None:
                return {self.OUTPUT: self._dest_id}
            blues = ['8,48,107', '8,81,156', '33,113,181', '66,146,198', '107,174,214', '158,202,225']
            bands = self._bands
            n = len(bands)

            def fill(rgb):
                s = QgsFillSymbol.createSimple({'color': rgb + ',120', 'outline_style': 'no'})
                return s
            cats = []
            for i, T in enumerate(bands):                 # rosnąco: mniejszy = ciemniejszy
                idx = 0 if n == 1 else int(round(i * (len(blues) - 1) / (n - 1)))
                cats.append(QgsRendererCategory(round(T, 1), fill(blues[idx]),
                                                self.tr('≤ %g min') % T))
            layer.setRenderer(QgsCategorizedSymbolRenderer('prog_min', cats))
            layer.setName(self.tr('Strefy dojazdu (izochrony)'))
            layer.triggerRepaint()
        except Exception:
            pass
        return {self.OUTPUT: self._dest_id}
