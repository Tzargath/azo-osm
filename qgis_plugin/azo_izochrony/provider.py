# -*- coding: utf-8 -*-
import os
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider
from .algorithm import IzochronyAZOAlgorithm
from .wskaznik import WskaznikPokryciaAlgorithm
from .jednostki import PokrycieJednostkiAlgorithm
from .dane_gugik import DaneGugikAlgorithm


class AzoProvider(QgsProcessingProvider):

    def loadAlgorithms(self):
        # ⚠ Pobieranie danych PIERWSZE na liście — to jest pierwszy krok
        #   użytkownika, który ma własny powiat i nic poza numerem TERYT.
        self.addAlgorithm(DaneGugikAlgorithm())
        self.addAlgorithm(IzochronyAZOAlgorithm())
        self.addAlgorithm(WskaznikPokryciaAlgorithm())
        self.addAlgorithm(PokrycieJednostkiAlgorithm())

    def id(self):
        return 'azo'

    def name(self):
        return 'AZO — zabezpieczenie operacyjne'

    def longName(self):
        return 'AZO — zabezpieczenie operacyjne (izochrony PSP)'

    def icon(self):
        path = os.path.join(os.path.dirname(__file__), 'icon.svg')
        return QIcon(path) if os.path.exists(path) else QgsProcessingProvider.icon(self)
