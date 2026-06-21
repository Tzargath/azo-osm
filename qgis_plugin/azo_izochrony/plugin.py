# -*- coding: utf-8 -*-
import os
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QToolButton, QMenu
from qgis.core import QgsApplication
from .provider import AzoProvider

ICON = os.path.join(os.path.dirname(__file__), 'icon.svg')
ALG_MAP = 'azo:izochrony_azo'
ALG_IND = 'azo:wskaznik_pokrycia'
ALG_JED = 'azo:pokrycie_jednostki'


class AzoPlugin:
    """Dostawca Processing + jeden przycisk na pasku z rozwijanym menu narzędzi."""

    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.actions = []
        self.toolbar = None
        self.button = None
        self.menu_name = 'Izochrony AZO (PSP)'

    def initProcessing(self):
        self.provider = AzoProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()
        icon = QIcon(ICON)

        a_map = QAction(icon, 'Mapa stref dojazdu (izochrony)', self.iface.mainWindow())
        a_map.triggered.connect(lambda: self._run(ALG_MAP))
        a_ind = QAction(icon, 'Wskaźnik pokrycia ludności (punkty popytu)', self.iface.mainWindow())
        a_ind.triggered.connect(lambda: self._run(ALG_IND))
        a_jed = QAction(icon, 'Pokrycie wg jednostek (powiaty/gminy)', self.iface.mainWindow())
        a_jed.triggered.connect(lambda: self._run(ALG_JED))
        self.actions = [a_map, a_ind, a_jed]

        # rozwijane menu pod jednym przyciskiem
        self.popup = QMenu()
        self.popup.addAction(a_map)
        self.popup.addAction(a_ind)
        self.popup.addAction(a_jed)
        self.button = QToolButton()
        self.button.setIcon(icon)
        self.button.setToolTip('Izochrony AZO (PSP) — wybierz narzędzie')
        self.button.setMenu(self.popup)
        try:
            self.button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        except AttributeError:
            self.button.setPopupMode(QToolButton.InstantPopup)

        self.toolbar = self.iface.addToolBar('Izochrony AZO')
        self.toolbar.setObjectName('AzoIzochronyToolbar')
        self.toolbar.addWidget(self.button)

        # pozycje też w menu Wtyczki
        for a in self.actions:
            self.iface.addPluginToMenu(self.menu_name, a)

    def _run(self, alg_id):
        try:
            from processing import execAlgorithmDialog
            execAlgorithmDialog(alg_id, {})
        except Exception:
            self.iface.messageBar().pushInfo(
                'Izochrony AZO', 'Uruchom z panelu Przetwarzanie → AZO — zabezpieczenie operacyjne.')

    def unload(self):
        for a in self.actions:
            self.iface.removePluginMenu(self.menu_name, a)
        self.actions = []
        if self.toolbar is not None:
            self.toolbar.deleteLater()
            self.toolbar = None
        self.button = None
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
