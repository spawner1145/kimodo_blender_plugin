"""Translate prompts without touching bpy data from background threads."""
import queue
import threading

import bpy
from bpy.props import BoolProperty, IntProperty
from bpy.types import Operator

from .prompt_translation import contains_chinese, translator
from .translations import tr

_active = []


@bpy.app.handlers.persistent
def _on_load_pre(_filepath):
    for operator in list(_active):
        operator.cancel(bpy.context)


def collect_targets(settings, segment_index=-1, all_segments=False):
    if all_segments:
        return [seg for seg in settings.motion_segments if contains_chinese(seg.prompt)]
    if segment_index >= 0:
        if segment_index >= len(settings.motion_segments):
            return []
        return [settings.motion_segments[segment_index]]
    return [settings]


def apply_results(snapshots, results):
    applied = 0
    for (target, original), translated in zip(snapshots, results):
        try:
            # Removed CollectionProperty items can retain readable RNA wrappers.
            # Verify membership before touching their no-longer-owned data.
            settings = getattr(target.id_data, 'kimodo', None)
            if settings is None or (target != settings and not any(
                    target == segment for segment in settings.motion_segments)):
                continue
            # Never overwrite an edit made while the HTTP request was in flight.
            if target.prompt != original or translated == original:
                continue
            target.prompt_original = original
            target.prompt = translated
            applied += 1
        except (ReferenceError, RuntimeError):
            continue  # A segment or scene may have been deleted while translating.
    return applied


class KIMODO_OT_TranslatePrompt(Operator):
    bl_translation_context = 'Kimodo'
    bl_idname = 'kimodo.translate_prompt'
    bl_label = 'Translate Chinese to English'
    bl_description = 'Translate the prompt online without an API key; keep the original for restoration'
    bl_options = {'REGISTER', 'UNDO'}

    segment_index: IntProperty(translation_context='Kimodo', default=-1, options={'SKIP_SAVE'})
    all_segments: BoolProperty(translation_context='Kimodo', default=False, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        s = getattr(getattr(context, 'scene', None), 'kimodo', None)
        return s is not None and not s.is_translating and not s.is_generating

    def invoke(self, context, event):
        s = context.scene.kimodo
        targets = collect_targets(s, self.segment_index, self.all_segments)
        self._snapshots = [(target, target.prompt) for target in targets
                           if contains_chinese(target.prompt)]
        if not self._snapshots:
            self.report({'INFO'}, tr('No Chinese prompts to translate'))
            return {'CANCELLED'}
        self._scene = context.scene
        self._closed = False
        self._result = queue.Queue()
        texts = [text for _, text in self._snapshots]
        service = s.translation_service
        result_queue = self._result

        def work():
            try:
                # Only immutable strings and the result queue cross into this thread.
                result_queue.put((True, [translator.translate(text, service) for text in texts]))
            except Exception as exc:
                result_queue.put((False, str(exc)))

        s.is_translating = True
        s.translation_status = tr('Translating…')
        self._wm = context.window_manager
        self._timer = self._wm.event_timer_add(0.1, window=context.window)
        self._wm.modal_handler_add(self)
        _active.append(self)
        threading.Thread(target=work, daemon=True).start()
        return {'RUNNING_MODAL'}

    def execute(self, context):
        return self.invoke(context, None)

    def _finish(self, context):
        self._closed = True
        if getattr(self, '_timer', None) is not None:
            try:
                self._wm.event_timer_remove(self._timer)
            except (ReferenceError, RuntimeError):
                pass
            self._timer = None
        try:
            self._scene.kimodo.is_translating = False
        except (ReferenceError, AttributeError):
            pass
        if self in _active:
            _active.remove(self)
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()

    def modal(self, context, event):
        if self._closed:
            return {'CANCELLED'}
        if event.type == 'ESC':
            self.cancel(context)
            return {'CANCELLED'}
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        try:
            success, result = self._result.get_nowait()
        except queue.Empty:
            return {'RUNNING_MODAL'}
        try:
            if success:
                applied = apply_results(self._snapshots, result)
                message = tr('Translated {count} prompts').format(count=applied)
                self._scene.kimodo.translation_status = message
                self.report({'INFO'}, message)
            else:
                message = tr('Translation failed: {error}').format(error=result)
                self._scene.kimodo.translation_status = message
                self.report({'ERROR'}, message)
        except (ReferenceError, AttributeError):
            return {'CANCELLED'}
        finally:
            self._finish(context)
        return {'FINISHED'} if success else {'CANCELLED'}

    def cancel(self, context):
        try:
            self._scene.kimodo.translation_status = tr('Translation cancelled; original text kept')
        except (ReferenceError, AttributeError):
            pass
        self._finish(context)


class KIMODO_OT_RestorePrompt(Operator):
    bl_translation_context = 'Kimodo'
    bl_idname = 'kimodo.restore_prompt'
    bl_label = 'Restore Original Chinese'
    bl_description = 'Restore the original prompt saved before translation'
    bl_options = {'REGISTER', 'UNDO'}

    segment_index: IntProperty(translation_context='Kimodo', default=-1, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        s = getattr(getattr(context, 'scene', None), 'kimodo', None)
        return s is not None and not s.is_translating and not s.is_generating

    def execute(self, context):
        targets = collect_targets(context.scene.kimodo, self.segment_index)
        for target in targets:
            if target.prompt_original:
                target.prompt = target.prompt_original
                target.prompt_original = ''
        return {'FINISHED'}


CLASSES = (KIMODO_OT_TranslatePrompt, KIMODO_OT_RestorePrompt)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    if _on_load_pre not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(_on_load_pre)


def unregister():
    _on_load_pre(None)
    if _on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_on_load_pre)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
