# Attribution

This is a locally modified version of Kimodo Blender Bridge v1.5.8 by Lewdineer.
Upstream: https://github.com/lewdineer/Kimodo_Blender_Bridge
The upstream Blender manifest declares GPL-2.0-or-later. Original author and
metadata are retained. Local modifications dated 2026-10-19 add a Simplified
Chinese catalog, explicit asynchronous Chinese-to-English prompt translation,
and a standalone HTTP API client (v2.0.0). Inference, model installation and
quantization have been moved out of this Blender addon into a separate service.
Local modifications are made available under GPL-2.0-or-later as well.

The keyless Alibaba / Youdao request flows were studied from WeiLin's
WeiLin-Comfyui-Tools (GPL v2):
https://github.com/weilin9999/WeiLin-Comfyui-Tools
Reference files: app/server/translate/network_translate/alibabav2.py and wangyi.py.
The Alibaba reference itself credits UlionTse/translators:
https://github.com/UlionTse/translators/blob/master/translators/server.py

This addon reimplements these HTTP flows using Python's standard library.
It does not bundle WeiLin-Comfyui-Tools, translators, or requests. The GPL v2
license text included as LICENSE is reproduced verbatim from the reference
repository. Alibaba and Youdao services remain operated by their respective
providers; availability and limits are controlled by those providers.
