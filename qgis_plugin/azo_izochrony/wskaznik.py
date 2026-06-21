# -*- coding: utf-8 -*-
"""
Algorytm Processing: Wskaźnik pokrycia ludności (punkty popytu).

LICZBA do AZO (nie mapa): % ludności w zasięgu T, liczony na PUNKTACH POPYTU, nie z przecięcia
powierzchni. Dla każdego punktu popytu:
    czas = min po osiągniętych węzłach drogi p w promieniu R_max [ t_drogi(p) + dist(p,punkt)/v_off ]
    pokryty, jeśli czas <= T  (i odcinek dojścia nie przecina bariery)
Wynik = Σ ludności pokrytych / Σ ludności. Czasy dojazdu liczone superwęzłem (1 Dijkstra, alarmowanie
wbudowane w koszt krawędzi superwęzeł->jednostka). Dokładniejsze i tańsze niż przecięcie z powierzchnią,
odporne na bariery. W pełni offline.
"""
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingException,
    QgsProcessingParameterVectorLayer, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField, QgsProcessingParameterNumber, QgsProcessingParameterString,
    QgsProcessingParameterMatrix, QgsProcessingParameterFeatureSink,
    QgsProcessingParameterDefinition, QgsProcessingOutputNumber,
    QgsFields, QgsField, QgsFeature, QgsGeometry, QgsPointXY, QgsWkbTypes,
    QgsVectorLayer, QgsCoordinateTransform, QgsProject, QgsFeatureRequest,
    QgsSpatialIndex, QgsRectangle, QgsProcessingUtils,
    QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsMarkerSymbol,
)
from qgis.analysis import (
    QgsVectorLayerDirector, QgsNetworkSpeedStrategy, QgsGraphBuilder, QgsGraphAnalyzer,
)
from .algorithm import DEF_SPEEDS, DEF_ALARM


class WskaznikPokryciaAlgorithm(QgsProcessingAlgorithm):
    NETWORK = 'NETWORK'
    CLASS_FIELD = 'CLASS_FIELD'
    SPEEDS = 'SPEEDS'
    DEFAULT_SPEED = 'DEFAULT_SPEED'
    POINTS = 'POINTS'
    TYPE_FIELD = 'TYPE_FIELD'
    ALARMS = 'ALARMS'
    DEFAULT_ALARM = 'DEFAULT_ALARM'
    DEMAND = 'DEMAND'
    POP_FIELD = 'POP_FIELD'
    THRESHOLDS = 'THRESHOLDS'
    OFFROAD_SPEED = 'OFFROAD_SPEED'
    OFFROAD_MAX = 'OFFROAD_MAX'
    BARRIERS = 'BARRIERS'
    TOLERANCE = 'TOLERANCE'
    OUTPUT = 'OUTPUT'

    def tr(self, s):
        return QCoreApplication.translate('WskaznikPokrycia', s)

    def createInstance(self):
        return WskaznikPokryciaAlgorithm()

    def name(self):
        return 'wskaznik_pokrycia'

    def displayName(self):
        return self.tr('Wskaźnik pokrycia ludności (punkty popytu)')

    def group(self):
        return self.tr('Analiza sieciowa')

    def groupId(self):
        return 'analiza'

    def shortHelpString(self):
        return self.tr(
            'Zwraca LICZBĘ do AZO: % ludności w zasięgu T, liczony na PUNKTACH POPYTU (nie z przecięcia '
            'powierzchni). Czas dotarcia = alarmowanie (wg typu) + jazda po drogach + dojście poza drogą; '
            'czasy liczone superwęzłem (1 Dijkstra). Odporny na bariery (odcinek dojścia przecinający '
            'barierę jest odrzucany).\n\n'
            '• Sieć, jednostki i punkty popytu w układzie METRYCZNYM (UTM/EPSG:2180).\n'
            '• Punkty popytu: pole ludności (waga); bez niego liczone są punkty (=1 każdy).\n'
            '• Progi w MINUTACH, np. "8,15".\n\n'
            'Wynik: warstwa punktów popytu z polami czas_min i pokr_<T>min (0/1) oraz zestawienie %% w logu.\n'
            'Materiał poglądowy; do celów urzędowych: sieć BDOT10k, ludność GUS, dane KW/KP PSP.'
        )

    def _adv(self, p):
        p.setFlags(p.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        return p

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.NETWORK, self.tr('Sieć dróg (linie, układ metryczny)'), [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterField(
            self.CLASS_FIELD, self.tr('Pole klasy drogi (np. highway)'),
            parentLayerParameterName=self.NETWORK, defaultValue='highway', optional=True))
        self.addParameter(QgsProcessingParameterMatrix(
            self.SPEEDS, self.tr('Prędkości pojazdu [km/h] wg klasy drogi'),
            numberRows=len(DEF_SPEEDS) // 2, hasFixedNumberRows=False,
            headers=[self.tr('Klasa drogi'), self.tr('km/h')], defaultValue=DEF_SPEEDS))
        self.addParameter(self._adv(QgsProcessingParameterNumber(
            self.DEFAULT_SPEED, self.tr('Prędkość domyślna [km/h]'),
            QgsProcessingParameterNumber.Double, defaultValue=30.0, minValue=1)))
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
            self.DEFAULT_ALARM, self.tr('Alarmowanie domyślne [min]'),
            QgsProcessingParameterNumber.Double, defaultValue=10.0, minValue=0)))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.DEMAND, self.tr('Punkty popytu (ludność)'), [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(
            self.POP_FIELD, self.tr('Pole ludności (waga); puste = punkty liczone po 1'),
            parentLayerParameterName=self.DEMAND, type=QgsProcessingParameterField.Numeric, optional=True))
        self.addParameter(QgsProcessingParameterString(
            self.THRESHOLDS, self.tr('Progi czasu dotarcia [min]'), defaultValue='8,15'))
        self.addParameter(QgsProcessingParameterNumber(
            self.OFFROAD_SPEED, self.tr('Prędkość dojścia/ostatniego odcinka [km/h]'),
            QgsProcessingParameterNumber.Double, defaultValue=10.0, minValue=1))
        self.addParameter(QgsProcessingParameterNumber(
            self.OFFROAD_MAX, self.tr('Maks. dojście poza drogą R_max [m]'),
            QgsProcessingParameterNumber.Double, defaultValue=300.0, minValue=0))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.BARRIERS, self.tr('Bariery (rzeki, tory, tereny zamknięte) — opcjonalne'),
            [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorLine], optional=True))
        self.addParameter(self._adv(QgsProcessingParameterNumber(
            self.TOLERANCE, self.tr('Tolerancja sklejania węzłów [m]'),
            QgsProcessingParameterNumber.Double, defaultValue=25.0, minValue=0)))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr('Punkty popytu z pokryciem'), QgsProcessing.TypeVectorPoint))

    @staticmethod
    def _matrix_to_map(values):
        m = {}
        for i in range(0, len(values) - 1, 2):
            try:
                m[str(values[i]).strip()] = float(values[i + 1])
            except (TypeError, ValueError):
                continue
        return m

    def processAlgorithm(self, parameters, context, feedback):
        net = self.parameterAsVectorLayer(parameters, self.NETWORK, context)
        if net is None:
            raise QgsProcessingException(self.tr('Brak warstwy sieci dróg.'))
        crs = net.crs()
        if crs.isGeographic():
            raise QgsProcessingException(self.tr(
                'Dane są w układzie geograficznym (stopnie). Przerzuć do układu metrycznego '
                '(EPSG:2180 lub strefa UTM).'))
        class_field = self.parameterAsString(parameters, self.CLASS_FIELD, context)
        speed_kmh = self._matrix_to_map(self.parameterAsMatrix(parameters, self.SPEEDS, context))
        default_speed = self.parameterAsDouble(parameters, self.DEFAULT_SPEED, context)
        type_field = self.parameterAsString(parameters, self.TYPE_FIELD, context)
        alarm_min = self._matrix_to_map(self.parameterAsMatrix(parameters, self.ALARMS, context))
        default_alarm = self.parameterAsDouble(parameters, self.DEFAULT_ALARM, context)
        pop_field = self.parameterAsString(parameters, self.POP_FIELD, context)
        thr_str = self.parameterAsString(parameters, self.THRESHOLDS, context)
        off_ms = self.parameterAsDouble(parameters, self.OFFROAD_SPEED, context) / 3.6
        rmax = self.parameterAsDouble(parameters, self.OFFROAD_MAX, context)
        tol = self.parameterAsDouble(parameters, self.TOLERANCE, context)

        try:
            thresholds = sorted({float(x) for x in thr_str.replace(';', ',').split(',') if x.strip()})
        except ValueError:
            raise QgsProcessingException(self.tr('Progi czasu muszą być liczbami, np. "8,15".'))
        if not thresholds:
            raise QgsProcessingException(self.tr('Podaj co najmniej jeden próg czasu.'))
        t_max_s = max(thresholds) * 60.0

        # --- sieć z prędkością wg klasy (w pamięci) ---
        feedback.pushInfo(self.tr('Przygotowanie sieci…'))
        authid = crs.authid() or crs.toWkt()
        mem = QgsVectorLayer('LineString?crs=' + authid, 'net_v', 'memory')
        pr = mem.dataProvider(); pr.addAttributes([QgsField('vkmh', QVariant.Double)]); mem.updateFields()
        cidx = net.fields().lookupField(class_field) if class_field else -1
        feats = []
        for f in net.getFeatures():
            g = f.geometry()
            if g.isEmpty():
                continue
            cls = f[cidx] if cidx >= 0 else None
            vk = speed_kmh.get(str(cls).strip() if cls is not None else None, default_speed)
            nf = QgsFeature(); nf.setGeometry(g)
            nf.setAttributes([float(vk) if vk and vk > 0 else default_speed]); feats.append(nf)
        pr.addFeatures(feats)
        if mem.featureCount() == 0:
            raise QgsProcessingException(self.tr('Sieć dróg jest pusta.'))

        # --- jednostki + alarmowanie ---
        pts_src = self.parameterAsSource(parameters, self.POINTS, context)
        xf = None
        if pts_src.sourceCrs() != crs:
            xf = QgsCoordinateTransform(pts_src.sourceCrs(), crs, context.project() or QgsProject.instance())
        points, alarms = [], []
        has_type = bool(type_field) and type_field in [fl.name() for fl in pts_src.fields()]
        for f in pts_src.getFeatures():
            g = f.geometry()
            if g.isEmpty():
                continue
            if xf:
                g = QgsGeometry(g); g.transform(xf)
            points.append(g.asPoint())
            a = alarm_min.get(str(f[type_field]).strip(), default_alarm) if has_type else default_alarm
            alarms.append(a * 60.0)
        if not points:
            raise QgsProcessingException(self.tr('Brak punktów jednostek.'))

        # --- superwęzeł: 1 Dijkstra -> czas dotarcia w każdym węźle ---
        feedback.pushInfo(self.tr('Analiza dojazdu (superwęzeł, 1 Dijkstra)…'))
        director = QgsVectorLayerDirector(mem, -1, '', '', '', QgsVectorLayerDirector.DirectionBoth)
        director.addStrategy(QgsNetworkSpeedStrategy(mem.fields().lookupField('vkmh'), float(default_speed), 1000.0 / 3600.0))
        builder = QgsGraphBuilder(crs, False, tol)
        tied = director.makeGraph(builder, points)
        graph = builder.graph()
        nV = graph.vertexCount()
        sv = graph.addVertex(QgsPointXY(0.0, 0.0))
        for i, tp in enumerate(tied):
            tv = graph.findVertex(tp)
            if tv >= 0:
                graph.addEdge(sv, tv, [alarms[i]])
        _, cost = QgsGraphAnalyzer.dijkstra(graph, sv, 0)
        feedback.setProgress(40)
        if feedback.isCanceled():
            return {}

        # --- indeks przestrzenny osiągalnych węzłów (gmin <= t_max) ---
        feedback.pushInfo(self.tr('Indeksowanie osiągalnych węzłów sieci…'))
        idx = QgsSpatialIndex()
        node_t = {}
        node_pt = {}
        fid = 0
        for v in range(nV):
            c = cost[v]
            if 0 <= c <= t_max_s:
                p = graph.vertex(v).point()
                ft = QgsFeature(fid); ft.setGeometry(QgsGeometry.fromPointXY(p))
                idx.addFeature(ft); node_t[fid] = c; node_pt[fid] = p; fid += 1
        feedback.pushInfo(self.tr('Osiągalnych węzłów: %d') % fid)
        feedback.setProgress(60)

        # --- bariery: indeks + geometrie ---
        bar_src = self.parameterAsSource(parameters, self.BARRIERS, context)
        bar_idx = None; bar_geom = {}
        if bar_src is not None:
            bar_idx = QgsSpatialIndex()
            bxf = None
            if bar_src.sourceCrs() != crs:
                bxf = QgsCoordinateTransform(bar_src.sourceCrs(), crs, context.project() or QgsProject.instance())
            bfid = 0
            for bf in bar_src.getFeatures():
                bg = bf.geometry()
                if bg.isEmpty():
                    continue
                if bxf:
                    bg = QgsGeometry(bg); bg.transform(bxf)
                # EKSPLODUJ na pojedyncze części — inaczej indeks nie filtruje (1 zdissolve'owana
                # bariera = 1 wpis pokrywający wszystko -> każdy odcinek testowany przeciw całości).
                for part in bg.asGeometryCollection():
                    if part.isEmpty():
                        continue
                    nf = QgsFeature(bfid); nf.setGeometry(part)
                    bar_idx.addFeature(nf); bar_geom[bfid] = part; bfid += 1

        def blocked(p0, p1):
            if bar_idx is None:
                return False
            seg = QgsGeometry.fromPolylineXY([p0, p1])
            for bid in bar_idx.intersects(seg.boundingBox()):
                if seg.intersects(bar_geom[bid]):
                    return True
            return False

        # --- punkty popytu ---
        dem_src = self.parameterAsSource(parameters, self.DEMAND, context)
        dxf = None
        if dem_src.sourceCrs() != crs:
            dxf = QgsCoordinateTransform(dem_src.sourceCrs(), crs, context.project() or QgsProject.instance())
        has_pop = bool(pop_field) and pop_field in [fl.name() for fl in dem_src.fields()]

        out_fields = QgsFields()
        out_fields.append(QgsField('lud', QVariant.Double))
        out_fields.append(QgsField('czas_min', QVariant.Double))
        for T in thresholds:
            out_fields.append(QgsField('pokr_%dmin' % int(round(T)), QVariant.Int))
        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context, out_fields,
                                               QgsWkbTypes.Point, crs)
        if sink is None:
            raise QgsProcessingException(self.tr('Nie udało się utworzyć warstwy wynikowej.'))

        total = 0.0
        cov = {T: 0.0 for T in thresholds}
        n_dem = dem_src.featureCount() or 0
        done = 0
        for f in dem_src.getFeatures():
            if feedback.isCanceled():
                return {}
            g = f.geometry()
            if g.isEmpty():
                continue
            if dxf:
                g = QgsGeometry(g); g.transform(dxf)
            p = g.asPoint()
            pop = float(f[pop_field]) if (has_pop and f[pop_field] is not None) else 1.0
            total += pop
            rect = QgsRectangle(p.x() - rmax, p.y() - rmax, p.x() + rmax, p.y() + rmax)
            best = None
            for cid in idx.intersects(rect):
                rp = node_pt[cid]
                d = ((p.x() - rp.x()) ** 2 + (p.y() - rp.y()) ** 2) ** 0.5
                if d > rmax:
                    continue
                arr = node_t[cid] + d / off_ms
                if best is not None and arr >= best:
                    continue
                if blocked(p, QgsPointXY(rp)):
                    continue
                best = arr
            of = QgsFeature(out_fields); of.setGeometry(QgsGeometry.fromPointXY(p))
            attrs = [pop, round(best / 60.0, 2) if best is not None else None]
            for T in thresholds:
                hit = 1 if (best is not None and best <= T * 60.0) else 0
                attrs.append(hit)
                if hit:
                    cov[T] += pop
            of.setAttributes(attrs); sink.addFeature(of)
            done += 1
            if n_dem:
                feedback.setProgress(60 + 40.0 * done / n_dem)

        feedback.pushInfo('—' * 30)
        feedback.pushInfo(self.tr('POKRYCIE LUDNOŚCI (suma wag = %.0f):') % total)
        for T in thresholds:
            frac = (100.0 * cov[T] / total) if total else 0.0
            feedback.pushInfo('  ≤ %g min:  %.1f%%  (%.0f)' % (T, frac, cov[T]))
        # do automatycznej stylizacji wyniku (postProcess)
        self._dest_id = dest_id
        self._style_field = 'pokr_%dmin' % int(round(max(thresholds)))
        self._style_T = max(thresholds)
        return {self.OUTPUT: dest_id}

    def postProcessAlgorithm(self, context, feedback):
        # zielony = pokryty, czerwony = poza zasięgiem (dla najwyższego progu)
        try:
            layer = QgsProcessingUtils.mapLayerFromString(self._dest_id, context)
            if layer is None:
                return {self.OUTPUT: self._dest_id}

            def mk(color):
                return QgsMarkerSymbol.createSimple(
                    {'name': 'circle', 'color': color, 'size': '1.8',
                     'outline_color': 'white', 'outline_width': '0.2'})
            cats = [
                QgsRendererCategory(1, mk('40,160,70'), self.tr('w zasięgu ≤ %g min') % self._style_T),
                QgsRendererCategory(0, mk('210,50,50'), self.tr('poza zasięgiem')),
            ]
            layer.setRenderer(QgsCategorizedSymbolRenderer(self._style_field, cats))
            layer.setName(self.tr('Pokrycie ludności (%g min)') % self._style_T)
            layer.triggerRepaint()
        except Exception:
            pass
        return {self.OUTPUT: self._dest_id}
