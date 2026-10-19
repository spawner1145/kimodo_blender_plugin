"""Blender translation registration; editable Simplified Chinese catalog in locales/."""
import json
from pathlib import Path

import bpy

DOMAIN = __package__
CONTEXT = 'Kimodo'


def tr(message):
    return bpy.app.translations.pgettext_iface(message, CONTEXT)


def register():
    path = Path(__file__).parent / 'locales' / 'zh_HANS.json'
    catalog = json.loads(path.read_text(encoding='utf-8'))
    entries = {(CONTEXT, source): target for source, target in catalog.items()}
    bpy.app.translations.register(DOMAIN, {'zh_HANS': entries, 'zh_CN': entries})


def unregister():
    bpy.app.translations.unregister(DOMAIN)
