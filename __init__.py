"""Kimodo API Bridge: HTTP motion generation, Chinese UI and prompt translation.

The model, PyTorch and quantization belong to the independent inference server.
This addon only sends parameters, downloads motion files and imports animation.
Based on Lewdineer's Kimodo Blender Bridge, GPL-2.0-or-later.
"""

bl_info = {
    "name":        "Kimodo API Bridge",
    "author":      "Lewdineer",
    "version":     (2, 1, 1),
    "blender":     (4, 2, 0),
    "location":    "View3D › Sidebar (N-Panel) › Kimodo",
    "description": "Generate motion through a configurable Kimodo HTTP API, with Chinese prompt translation",
    "doc_url":     "https://github.com/nv-tlabs/kimodo",
    "tracker_url": "https://github.com/nv-tlabs/kimodo/issues",
    "category":    "Animation",
    "support":     "COMMUNITY",
}

import bpy

# Sub-modules (imported after bl_info for Blender's enable/disable system)
from . import properties, operators, ui_list, panels, constraints
from . import translations, translation_operators
from . import api_client as sc


def register():
    translations.register()
    properties.register()
    translation_operators.register()
    operators.register()
    ui_list.register()
    panels.register()


def unregister():
    # Disconnect this client. The independently managed API server stays running.
    sc.stop()
    panels.unregister()
    ui_list.unregister()
    operators.unregister()
    translation_operators.unregister()
    properties.unregister()
    translations.unregister()
