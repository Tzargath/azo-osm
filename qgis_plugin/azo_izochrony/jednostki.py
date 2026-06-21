# -*- coding: utf-8 -*-
"""
Algorytm Processing: Pokrycie ludności wg jednostek (powiaty / gminy / obręby).

Dla każdego wskazanego poligonu administracyjnego liczy % mieszkańców w zasięgu T (na punktach
popytu, superwęzłem, barrier-aware) i wpisuje go do tabeli atrybutów. Wynik auto-stylizowany
(gradient zielony wg %) i podpisany na środku poligonu: „nazwa — XX%".
"""
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingException,
    QgsProcessingParameterVectorLayer, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField, QgsProcessingParameterNumber, QgsProcessingParameterString,
    QgsProcessingParameterMatrix, QgsProcessingParameterFeatureSink,
    QgsProcessingParameterDefinition, QgsProcessingUtils,
    QgsFields, QgsField, QgsFeature, QgsGeometry, QgsPointXY, QgsWkbTypes,
    QgsVectorLayer, QgsCoordinateTransform, QgsProject, QgsFeatureRequest,
    QgsSpatialIndex, QgsRectangle, QgsFillSymbol, QgsStyle,
    QgsGraduatedSymbolRenderer, QgsPalLayerSettings, QgsTextFormat,
    QgsTextBufferSettings, QgsVectorLayerSimpleLabeling,
)
from qgis.analysis import (
    QgsVectorLayerDirector, QgsNetworkSpeedStrategy, QgsGraphBuilder, QgsGraphAnalyzer,
)
from .algorithm import DEF_SPEEDS, DEF_ALARM


class PokrycieJednostkiAlgorithm(QgsProcessingAlgorithm):
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
    ADMIN = 'ADMIN'
    NAME_FIELD = 'NAME_FIELD'
    THRESHOLDS = 'THRESHOLDS'
    OFFROAD_SPEED = 'OFFROAD_SPEED'
    OFFROAD_MAX = 'OFFROAD_MAX'
    BARRIERS = 'BARRIERS'
    TOLERANCE = 'TOLERANCE'
    OUTPUT = 'OUTPUT'

    def tr(self, s):
        return QCoreApplication.translate('PokrycieJednostki', s)

    def createInstance(self):
        return PokrycieJednostkiAlgorithm()

    def name(self):
        return 'pokrycie_jednostki'

    def displayName(self):
        return self.tr('Pokrycie ludności wg jednostek (powiaty/gminy)')

    def group(self):
        return self.tr('Analiza sieciowa')

    def groupId(self):
        return 'analiza'

    def shortHelpString(self):
        return self.tr(
            'Dla każdego poligonu administracyjnego (powiat/gmina/obręb) liczy % mieszkańców w zasięgu T '
            '(na punktach popytu, superwęzłem, barrier-aware) i wpisuje do tabeli atrybutów. Wynik '
            'kolorowany gradientem zieleni wg % i podpisany na środku poligonu „nazwa — XX%".\n\n'
            '• Sieć, jednostki, punkty popytu i poligony w układzie METRYCZNYM (UTM/EPSG:2180).\n'
            '• Ludność z punktów popytu (waga); % = ludność objęta w poligonie ÷ ludność w poligonie.\n'
            '• Progi w MINUTACH, np. "8,15".'
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
            self.TYPE_FIELD, self.tr('Pole typu jednostki (do alarmowania)'),
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
            self.POP_FIELD, self.tr('Pole ludności (waga); puste = po 1'),
            parentLayerParameterName=self.DEMAND, type=QgsProcessingParameterField.Numeric, optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.ADMIN, self.tr('Jednostki administracyjne (poligony: powiaty/gminy)'),
            [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterField(
            self.NAME_FIELD, self.tr('Pole nazwy jednostki (do podpisu)'),
            parentLayerParameterName=self.ADMIN, defaultValue='name', optional=True))
        self.addParameter(QgsProcessingParameterString(
            self.THRESHOLDS, self.tr('Progi czasu dotarcia [min]'), defaultValue='8,15'))
        self.addParameter(QgsProcessingParameterNumber(
            self.OFFROAD_SPEED, self.tr('Prędkość dojścia [km/h]'),
            QgsProcessingParameterNumber.Double, defaultValue=10.0, minValue=1))
        self.addParameter(QgsProcessingParameterNumber(
            self.OFFROAD_MAX, self.tr('Maks. dojście poza drogą R_max [m]'),
            QgsProcessingParameterNumber.Double, defaultValue=300.0, minValue=0))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.BARRIERS, self.tr('Bariery (rzeki, tory) — opcjonalne'),
            [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorLine], optional=True))
        self.addParameter(self._adv(QgsProcessingParameterNumber(
            self.TOLERANCE, self.tr('Tolerancja sklejania węzłów [m]'),
            QgsProcessingParameterNumber.Double, defaultValue=25.0, minValue=0)))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr('Jednostki z % pokrycia'), QgsProcessing.TypeVectorPolygon))

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
            raise QgsProcessingException(self.tr('Dane w układzie geograficznym — przerzuć do metrycznego (UTM/2180).'))
        class_field = self.parameterAsString(parameters, self.CLASS_FIELD, context)
        speed_kmh = self._matrix_to_map(self.parameterAsMatrix(parameters, self.SPEEDS, context))
        default_speed = self.parameterAsDouble(parameters, self.DEFAULT_SPEED, context)
        type_field = self.parameterAsString(parameters, self.TYPE_FIELD, context)
        alarm_min = self._matrix_to_map(self.parameterAsMatrix(parameters, self.ALARMS, context))
        default_alarm = self.parameterAsDouble(parameters, self.DEFAULT_ALARM, context)
        pop_field = self.parameterAsString(parameters, self.POP_FIELD, context)
        name_field = self.parameterAsString(parameters, self.NAME_FIELD, context)
        thr_str = self.parameterAsString(parameters, self.THRESHOLDS, context)
        off_ms = self.parameterAsDouble(parameters, self.OFFROAD_SPEED, context) / 3.6
        rmax = self.parameterAsDouble(parameters, self.OFFROAD_MAX, context)
        tol = self.parameterAsDouble(parameters, self.TOLERANCE, context)
        try:
            thresholds = sorted({float(x) for x in thr_str.replace(';', ',').split(',') if x.strip()})
        except ValueError:
            raise QgsProcessingException(self.tr('Progi czasu muszą być liczbami, np. "8,15".'))
        if not thresholds:
            raise QgsProcessingException(self.tr('Podaj co najmniej jeden próg.'))
        t_max_s = max(thresholds) * 60.0

        # --- sieć (vkmh wg klasy) ---
        feedback.pushInfo(self.tr('Przygotowanie sieci…'))
        authid = crs.authid() or crs.toWkt()
        mem = QgsVectorLayer('LineString?crs=' + authid, 'net_v', 'memory')
        pr = mem.dataProvider(); pr.addAttributes([QgsField('vkmh', QVariant.Double)]); mem.updateFields()
        cidx = net.fields().lookupField(class_field) if class_field else -1
        fs = []
        for f in net.getFeatures():
            g = f.geometry()
            if g.isEmpty():
                continue
            cls = f[cidx] if cidx >= 0 else None
            vk = speed_kmh.get(str(cls).strip() if cls is not None else None, default_speed)
            nf = QgsFeature(); nf.setGeometry(g); nf.setAttributes([float(vk) if vk and vk > 0 else default_speed]); fs.append(nf)
        pr.addFeatures(fs)

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

        # --- superwęzeł: 1 Dijkstra ---
        feedback.pushInfo(self.tr('Analiza dojazdu (superwęzeł)…'))
        director = QgsVectorLayerDirector(mem, -1, '', '', '', QgsVectorLayerDirector.DirectionBoth)
        director.addStrategy(QgsNetworkSpeedStrategy(mem.fields().lookupField('vkmh'), float(default_speed), 1000.0 / 3600.0))
        builder = QgsGraphBuilder(crs, False, tol)
        tied = director.makeGraph(builder, points)
        graph = builder.graph(); nV = graph.vertexCount()
        sv = graph.addVertex(QgsPointXY(0.0, 0.0))
        for i, tp in enumerate(tied):
            tv = graph.findVertex(tp)
            if tv >= 0:
                graph.addEdge(sv, tv, [alarms[i]])
        _, cost = QgsGraphAnalyzer.dijkstra(graph, sv, 0)
        feedback.setProgress(35)
        if feedback.isCanceled():
            return {}

        # indeks osiągalnych węzłów
        idx = QgsSpatialIndex(); node_t = {}; node_pt = {}; fid = 0
        for v in range(nV):
            c = cost[v]
            if 0 <= c <= t_max_s:
                p = graph.vertex(v).point()
                ft = QgsFeature(fid); ft.setGeometry(QgsGeometry.fromPointXY(p))
                idx.addFeature(ft); node_t[fid] = c; node_pt[fid] = p; fid += 1
        feedback.setProgress(50)

        # bariery
        bar_src = self.parameterAsSource(parameters, self.BARRIERS, context)
        bar_idx = None; bar_geom = {}
        if bar_src is not None:
            bar_idx = QgsSpatialIndex(); bxf = None
            if bar_src.sourceCrs() != crs:
                bxf = QgsCoordinateTransform(bar_src.sourceCrs(), crs, context.project() or QgsProject.instance())
            bfid = 0
            for bf in bar_src.getFeatures():
                bg = bf.geometry()
                if bg.isEmpty():
                    continue
                if bxf:
                    bg = QgsGeometry(bg); bg.transform(bxf)
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

        # --- poligony administracyjne: indeks + geom + nazwa ---
        adm_src = self.parameterAsSource(parameters, self.ADMIN, context)
        axf = None
        if adm_src.sourceCrs() != crs:
            axf = QgsCoordinateTransform(adm_src.sourceCrs(), crs, context.project() or QgsProject.instance())
        has_name = bool(name_field) and name_field in [fl.name() for fl in adm_src.fields()]
        poly_idx = QgsSpatialIndex(); poly_geom = {}; poly_name = {}; poly_src_feat = {}
        pfid = 0
        for af in adm_src.getFeatures():
            g = QgsGeometry(af.geometry())   # KOPIA — bez niej iterator nadpisuje referencję
            if g.isEmpty():
                continue
            if axf:
                g.transform(axf)
            ft = QgsFeature(); ft.setId(pfid); ft.setGeometry(g)
            poly_idx.addFeature(ft); poly_geom[pfid] = g
            poly_name[pfid] = (str(af[name_field]) if has_name else 'jedn. %d' % pfid)
            poly_src_feat[pfid] = af
            pfid += 1
        agg = {p: {'tot': 0.0, 'cov': {T: 0.0 for T in thresholds}} for p in poly_geom}

        # --- punkty popytu: pokrycie + przypisanie do poligonu ---
        dem_src = self.parameterAsSource(parameters, self.DEMAND, context)
        dxf = None
        if dem_src.sourceCrs() != crs:
            dxf = QgsCoordinateTransform(dem_src.sourceCrs(), crs, context.project() or QgsProject.instance())
        has_pop = bool(pop_field) and pop_field in [fl.name() for fl in dem_src.fields()]
        n_dem = dem_src.featureCount() or 0; done = 0
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
            # do którego poligonu należy?
            pg = QgsGeometry.fromPointXY(p); target = None
            for pid in poly_idx.intersects(QgsRectangle(p.x(), p.y(), p.x(), p.y())):
                if poly_geom[pid].contains(pg):
                    target = pid; break
            if target is None:
                continue
            # czas dotarcia (min po czystych kandydatach)
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
            agg[target]['tot'] += pop
            if best is not None:
                for T in thresholds:
                    if best <= T * 60.0:
                        agg[target]['cov'][T] += pop
            done += 1
            if n_dem:
                feedback.setProgress(50 + 45.0 * done / n_dem)

        # --- wynik: poligony z % ---
        out_fields = QgsFields()
        out_fields.append(QgsField('nazwa', QVariant.String))
        out_fields.append(QgsField('ludnosc', QVariant.Double))
        for T in thresholds:
            out_fields.append(QgsField('pokr_%dmin_pct' % int(round(T)), QVariant.Double))
        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context, out_fields,
                                               QgsWkbTypes.MultiPolygon, crs)
        if sink is None:
            raise QgsProcessingException(self.tr('Nie udało się utworzyć warstwy wynikowej.'))
        feedback.pushInfo('—' * 30)
        for pid in poly_geom:
            tot = agg[pid]['tot']
            of = QgsFeature(out_fields); of.setGeometry(poly_geom[pid])
            attrs = [poly_name[pid], round(tot, 0)]
            line = '%s: ludn. %.0f' % (poly_name[pid], tot)
            for T in thresholds:
                pct = (100.0 * agg[pid]['cov'][T] / tot) if tot > 0 else None
                attrs.append(round(pct, 1) if pct is not None else None)
                line += '  %g min: %s' % (T, ('%.1f%%' % pct) if pct is not None else 'b.d.')
            of.setAttributes(attrs); sink.addFeature(of)
            feedback.pushInfo('  ' + line)

        self._dest_id = dest_id
        self._maxT = max(thresholds)
        self._pct_field = 'pokr_%dmin_pct' % int(round(max(thresholds)))
        return {self.OUTPUT: dest_id}

    def postProcessAlgorithm(self, context, feedback):
        try:
            layer = QgsProcessingUtils.mapLayerFromString(self._dest_id, context)
            if layer is None:
                return {self.OUTPUT: self._dest_id}
            ramp = QgsStyle.defaultStyle().colorRamp('Greens')
            base = QgsFillSymbol.createSimple({'outline_color': '110,110,110', 'outline_width': '0.12'})
            ren = QgsGraduatedSymbolRenderer.createRenderer(
                layer, self._pct_field, 5, QgsGraduatedSymbolRenderer.Jenks, base, ramp)
            layer.setRenderer(ren)
            # etykieta na centroidzie: nazwa + %
            ls = QgsPalLayerSettings(); ls.fieldName = 'concat("nazwa", \'\\n\', round("%s"), \'%%\')' % self._pct_field
            ls.isExpression = True
            tf = QgsTextFormat(); f = QFont('Arial'); f.setPointSizeF(8.0); f.setBold(True); tf.setFont(f); tf.setSize(8.0)
            buf = QgsTextBufferSettings(); buf.setEnabled(True); buf.setSize(1.0); buf.setColor(QColor('white'))
            tf.setBuffer(buf); ls.setFormat(tf)
            try:
                from qgis.core import Qgis
                ls.placement = Qgis.LabelPlacement.Horizontal
            except Exception:
                pass
            layer.setLabeling(QgsVectorLayerSimpleLabeling(ls)); layer.setLabelsEnabled(True)
            layer.setName(self.tr('Pokrycie wg jednostek (%g min)') % self._maxT)
            layer.triggerRepaint()
        except Exception:
            pass
        return {self.OUTPUT: self._dest_id}
