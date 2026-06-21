# -*- coding: utf-8 -*-
def classFactory(iface):
    from .plugin import AzoPlugin
    return AzoPlugin(iface)
