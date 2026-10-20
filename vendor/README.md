# 内置 BVH 导入器

`import_bvh.py` 来自 Blender 5.2 随附的官方 `io_anim_bvh` 插件，
SPDX 作者为 Campbell Barton，许可为 GPL-2.0-or-later，完整许可见插件根目录 `LICENSE`。

本插件直接调用内置导入函数，不需要启用、安装或下载另一个 BVH 扩展。
本地修改包括兼容 Blender 4.2 的旧版 Action，并在帧率换算时使用 `fps_base`。
