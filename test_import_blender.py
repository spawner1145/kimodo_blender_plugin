"""Run in background Blender; no API, weights or external BVH extension required."""
from pathlib import Path
import sys
import tempfile
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kimodo_blender_plugin
from kimodo_blender_plugin.operators import _import_bvh

kimodo_blender_plugin.register()
try:
    bpy.context.scene.render.fps = 60
    text = '''HIERARCHY
ROOT Hips
{
  OFFSET 0 100 0
  CHANNELS 6 Xposition Yposition Zposition Zrotation Yrotation Xrotation
  JOINT Head
  {
    OFFSET 0 50 0
    CHANNELS 3 Zrotation Yrotation Xrotation
    End Site
    {
      OFFSET 0 10 0
    }
  }
}
MOTION
Frames: 3
Frame Time: 0.033333333
0 100 0 0 0 0 0 0 0
10 100 0 0 15 0 0 0 0
20 100 0 0 30 0 0 0 0
'''
    def guard(event, args):
        if event in ('socket.connect', 'socket.getaddrinfo'):
            raise RuntimeError('Addon validation disallows network')
        if event == 'open' and args and isinstance(args[0], str) and 'io_anim_bvh' in args[0]:
            raise RuntimeError('Addon validation disallows external BVH source')
    sys.addaudithook(guard)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'sample.bvh'
        path.write_text(text, 'utf-8')
        _import_bvh(filepath=str(path), axis_forward='-Z', axis_up='Y', target='ARMATURE',
                    global_scale=.01, use_fps_scale=True, update_scene_fps=False)
        obj = bpy.context.object
        assert obj.type == 'ARMATURE' and set(obj.pose.bones.keys()) == {'Hips', 'Head'}
        assert bpy.context.scene.render.fps == 60
        bpy.context.scene.frame_set(5)
        assert abs((obj.matrix_world @ obj.pose.bones['Hips'].head).x - .2) < 1e-5
        print('KIMODO_BUNDLED_BVH_IMPORT_OK', list(obj.animation_data.action.frame_range))
finally:
    kimodo_blender_plugin.unregister()
