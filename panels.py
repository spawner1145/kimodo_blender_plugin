"""
Kimodo Blender Bridge — Panels
All N-panel UI panels in the 3D Viewport → Kimodo tab.
"""

import os
import textwrap

import bpy
import json
from bpy.types import Panel
from .translations import tr
from . import api_client


def _draw_prompt_translation(layout, target, settings, segment_index=-1):
    row = layout.row(align=True)
    row.enabled = not settings.is_translating and not settings.is_generating
    op = row.operator('kimodo.translate_prompt', text=tr('Chinese → English'), icon='WORLD')
    op.segment_index = segment_index
    if target.prompt_original:
        op = row.operator('kimodo.restore_prompt', text=tr('Restore Chinese'), icon='LOOP_BACK')
        op.segment_index = segment_index


# ---------------------------------------------------------------------------
# Base class — common settings
# ---------------------------------------------------------------------------

class KIMODO_PanelBase:
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = 'Kimodo'


# ---------------------------------------------------------------------------
# Generation history (shared by both Generate panel modes)
# ---------------------------------------------------------------------------

def _label_wrapped(col, text, context, icon='NONE'):
    """Labels don't wrap on their own, so long prompts (e.g. 5+ joined
    segment prompts) were cut off. Emit the text as multiple labels sized
    to the panel width instead."""
    try:
        ui_scale = context.preferences.system.ui_scale
    except Exception:
        ui_scale = 1.0
    width_px = context.region.width if context.region else 320
    chars = max(24, int(width_px / (7 * ui_scale)) - 4)
    for i, line in enumerate(textwrap.wrap(text, width=chars) or [""]):
        col.label(text=line, icon=icon if i == 0 else 'BLANK1')


def _draw_history_detail(layout, context, entry):
    """Selected entry: full wrapped prompt(s) with the seed(s) used."""
    col = layout.column(align=True)
    prompts = [p.strip() for p in entry.prompt.split(" | ")] if entry.prompt else [""]
    seed_list = [x.strip() for x in entry.seeds.split(",") if x.strip()] if entry.seeds else []

    if len(prompts) > 1:
        # Multi-segment generation: one line per segment with its own seed
        for i, p in enumerate(prompts):
            seed_txt = f"   ({tr('Seed')} {seed_list[i]})" if i < len(seed_list) else ""
            _label_wrapped(col, f"{i + 1}.  {p}{seed_txt}", context,
                           icon='TEXT' if i == 0 else 'BLANK1')
        meta = f"{tr('Duration (s)')}: {entry.duration:.1f}  ·  {entry.timestamp.replace('T', ' ')}"
        if not seed_list:  # entry from a version that only stored the first seed
            meta = f"{tr('Seed')}: {entry.seed}  ·  {meta}"
    else:
        _label_wrapped(col, entry.prompt, context, icon='TEXT')
        meta = f"{tr('Seed')}: {entry.seed}  ·  {entry.duration:.1f}s  ·  {entry.timestamp.replace('T', ' ')}"

    meta_col = layout.column(align=True)
    _label_wrapped(meta_col, meta, context, icon='TIME')


def _draw_history(layout, context, s):
    layout.separator()
    hist_header = layout.row(align=True)
    hist_header.prop(
        s, "history_expanded",
        icon='DISCLOSURE_TRI_DOWN' if s.history_expanded else 'DISCLOSURE_TRI_RIGHT',
        icon_only=True, emboss=False,
    )
    hist_header.label(
        text=tr('History ({v0})').format(v0=len(s.generation_history)), icon='TIME'
    )
    if not s.history_expanded:
        return
    if not s.generation_history:
        layout.label(text=tr('No generations yet.'), icon='INFO')
    else:
        layout.template_list(
            "KIMODO_UL_History", "",
            s, "generation_history",
            s, "history_index",
            rows=min(len(s.generation_history), 5),
        )
        if 0 <= s.history_index < len(s.generation_history):
            entry = s.generation_history[s.history_index]
            detail = layout.box()
            _draw_history_detail(detail, context, entry)
            op_row = detail.row(align=True)
            reimport_op = op_row.operator(
                "kimodo.reimport_from_history",
                text=tr('Re-import BVH'), icon='IMPORT',
            )
            reimport_op.index = s.history_index
    layout.operator("kimodo.clear_history", text=tr('Clear History'), icon='TRASH')


# ---------------------------------------------------------------------------
# Panel 1: Connection
# ---------------------------------------------------------------------------

class KIMODO_PT_Connection(KIMODO_PanelBase, Panel):
    bl_translation_context = 'Kimodo'
    bl_label    = "⚙  Connection"
    bl_idname   = "KIMODO_PT_Connection"
    bl_order    = 10
    

    def draw(self, context):
        layout = self.layout
        s = context.scene.kimodo
        prefs = context.preferences.addons[__package__].preferences
        fields = layout.column(align=True)
        fields.enabled = not s.is_connected and not s.is_connecting and not s.is_generating
        fields.prop(prefs, 'server_url')
        fields.prop(prefs, 'api_token')
        op = layout.operator('wm.url_open', text=tr('Server WebUI'), icon='URL')
        op.url = prefs.server_url.rstrip('/') + '/'
        row = layout.row()
        row.enabled = not s.is_generating and not s.is_connecting
        row.prop(s, 'api_model', text=tr('API Model'))
        row = layout.row()
        row.enabled = not s.is_generating and not s.is_connecting
        row.prop(s,'api_encoder',text=tr('Text Encoder'))
        if s.is_connected or s.is_connecting:
            row = layout.row()
            row.enabled = not s.is_generating
            row.operator('kimodo.stop_kimodo', text=tr('Disconnect'), icon='UNLINKED')
        else:
            layout.operator('kimodo.start_kimodo', text=tr('Connect API'), icon='LINKED')
        layout.label(text=tr(s.connection_status), icon='CHECKMARK' if s.is_connected else 'INFO')
        info = api_client.server_info()
        if s.is_connected and info.get('offload'):
            layout.label(text=tr('Server GPU offload enabled'), icon='MEMORY')
        encoder = next((e for e in info.get('encoders',[]) if e['id']==s.api_encoder),{})
        if s.is_connected and encoder.get('approximate'):
            layout.label(text=tr('Text encoder: AWQ LLM2Vec (approximate)'), icon='INFO')


# ---------------------------------------------------------------------------
# Panel 2: Generate — Single Clip or Timeline, one workflow
# ---------------------------------------------------------------------------
#
# Single Clip (one prompt -> one motion) and Timeline (multiple prompt
# segments stitched together) used to be two separate panels that duplicated
# the model picker, the reuse-armature row, the FPS warning, the T-pose
# option, the Generate button and the history list -- identically, in two
# places, both collapsed by default. A new user had no way to tell which
# panel to open first, or that the two were even related. One panel with a
# mode switch keeps everything that's actually shared in one place, drawn
# once, and open by default since generating motion is the point of the addon.

class KIMODO_PT_Generate(KIMODO_PanelBase, Panel):
    bl_translation_context = 'Kimodo'
    bl_label   = "🎬  Generate"
    bl_idname  = "KIMODO_PT_Generate"
    bl_order   = 14

    def draw(self, context):
        layout = self.layout
        s = context.scene.kimodo
        layout.enabled = True

        mode_row = layout.row(align=True)
        mode_row.enabled = not s.is_generating
        mode_row.prop(s, "generate_mode", expand=True)

        layout.prop(s, 'translation_service', text=tr('Translation'))
        if s.translation_status:
            layout.label(text=s.translation_status, icon='TIME' if s.is_translating else 'INFO')

        layout.separator(factor=0.5)

        profile = next((p for p in api_client.server_info().get('models',[]) if p['id']==s.api_model),{})
        layout.label(text=tr('Motion skeleton')+': '+profile.get('skeleton','SOMA'),icon='ARMATURE_DATA')
        box = layout.box()
        box.prop(s, 'show_inference_settings', text=tr('Inference Settings'),
                 icon='TRIA_DOWN' if s.show_inference_settings else 'TRIA_RIGHT', emboss=False)
        if s.show_inference_settings:
            col = box.column(align=True)
            col.prop(s, 'diffusion_steps')
            col.prop(s, 'cfg_text')
            col.prop(s, 'cfg_constraints')
            col.prop(s, 'block_swap')
            col.prop(s, 'text_block_swap')
            col.label(text=tr('Block swap: -1 follows server, 0 disables'),icon='INFO')
            row = col.row()
            supported = api_client.server_info().get('capabilities', {}).get('post_processing', False)
            row.enabled = supported
            row.prop(s, 'post_processing')
            if not supported:
                col.label(text=tr('Server motion correction is not installed'), icon='INFO')

        layout.separator(factor=0.5)

        inputs = layout.column()
        inputs.enabled = not s.is_generating
        if s.generate_mode == 'SINGLE':
            self._draw_single(inputs, context, s)
        else:
            self._draw_timeline(inputs, context, s)

        layout.separator()

        # --- Shared: output options ---
        layout.prop(s, "bvh_standard_tpose", icon='ARMATURE_DATA')
        reuse_row = layout.row(align=True)
        reuse_row.prop(s, "reuse_armature", text=tr('Reuse'), icon='ARMATURE_DATA')
        reuse_row.operator("kimodo.pick_latest_armature", text="", icon='SORTTIME')

        if s.generate_mode == 'TIMELINE':
            trans_row = layout.row(align=True)
            trans_row.label(text=tr('Transition Frames:'))
            trans_row.prop(s, "num_transition_frames", text="")

        # --- Shared: FPS warning ---
        scene_fps = context.scene.render.fps / context.scene.render.fps_base
        if abs(scene_fps - 30.0) > 0.01:
            fps_box = layout.box()
            fps_box.alert = True
            fps_box.label(text=tr('Scene is {v0:.4g} FPS — Kimodo needs 30 FPS').format(v0=scene_fps), icon='ERROR')
            fps_box.operator("kimodo.set_to_30fps", text=tr('Set to 30 FPS'), icon='RECOVER_LAST')

        layout.separator()

        # --- Shared: Generate / Cancel ---
        if s.is_generating:
            col = layout.column()
            col.enabled = True   # re-enable for cancel
            col.operator("kimodo.cancel_generation", text=tr('⏹  Cancel'), icon='X')
            box = layout.box()
            box.label(text=tr(s.generation_progress or "Working…"), icon='TIME')
        else:
            row = layout.column()
            row.enabled = s.is_connected and not s.is_translating
            row.scale_y = 2
            if s.generate_mode == 'SINGLE':
                connected_icon = 'PLAY' if s.is_connected else 'UNLINKED'
                row.operator("kimodo.generate", text=tr('Generate Motion'), icon=connected_icon)
                if s.generation_progress:
                    layout.label(text=tr(s.generation_progress),
                                 icon='CHECKMARK' if "Done" in s.generation_progress else 'ERROR')
            else:
                row.operator("kimodo.generate_all_segments", text=tr('Generate Motion'), icon='PLAY')

        # --- Single-mode only: batch variations ---
        if s.generate_mode == 'SINGLE':
            layout.separator()
            var_row = layout.row(align=True)
            var_row.enabled = s.is_connected and not s.is_generating and not s.is_translating
            var_row.prop(s, "num_variations", text=tr('Variations'))
            var_row.operator(
                "kimodo.generate_variations",
                text=tr('Generate {v0} Variations').format(v0=s.num_variations),
                icon='DUPLICATE',
            )

        # --- Shared: History ---
        _draw_history(layout, context, s)

        # --- Shared: Manual import fallback ---
        layout.separator()
        box = layout.box()
        box.label(text=tr('Manual Import'), icon='IMPORT')
        row = box.row()
        row.prop(s, "last_bvh_path", text=tr('BVH Path'))
        row.operator("kimodo.import_bvh", text="", icon='FILE_FOLDER').filepath = ""

    def _draw_single(self, layout, context, s):
        layout.label(text=tr('Prompt:'))
        layout.prop(s, "prompt", text="")
        _draw_prompt_translation(layout, s, s)

        layout.prop(s, "duration", slider=True)
        seed_row = layout.row(align=True)
        seed_field = seed_row.row(align=True)
        seed_field.enabled = s.seed_mode != 'RANDOM'
        seed_field.prop(s, "seed")
        seed_modes = seed_row.row(align=True)
        seed_modes.alignment = 'RIGHT'
        seed_modes.prop(s, "seed_mode", expand=True)

        row = layout.row(align=True)
        row.label(text=tr('Output:'))
        row.prop(s, "output_format", expand=True)

    def _draw_timeline(self, layout, context, s):
        row = layout.row(align=True)
        row.operator("kimodo.add_segment",    text=tr('Add'),    icon='ADD')
        row.operator("kimodo.remove_segment", text=tr('Remove'), icon='REMOVE')
        row.separator()
        row.operator("kimodo.duplicate_segment", text="", icon='DUPLICATE')
        row.operator("kimodo.move_segment_up",   text="", icon='TRIA_UP')
        row.operator("kimodo.move_segment_down", text="", icon='TRIA_DOWN')
        row = layout.row()
        row.enabled = not s.is_translating and not s.is_generating
        row.operator('kimodo.translate_prompt', text=tr('Translate All Segments'), icon='WORLD').all_segments = True

        layout.separator(factor=0.5)

        if not s.motion_segments:
            col = layout.column()
            col.label(text=tr('No segments yet.'), icon='INFO')
            col.label(text=tr('Click Add to create one.'))
            return

        for i, seg in enumerate(s.motion_segments):
            is_generating = (i == s.generating_segment_index)

            box = layout.box()
            header = box.row(align=True)

            header.prop(seg, "enabled", text="", emboss=False,
                        icon='CHECKBOX_HLT' if seg.enabled else 'CHECKBOX_DEHLT')

            title = f"  {seg.prompt[:28]}{'…' if len(seg.prompt) > 28 else ''}"
            header.label(text=title)
            header.label(text=tr('{v0}–{v1}').format(v0=seg.start_frame, v1=seg.end_frame))

            if is_generating:
                header.label(text="", icon='TIME')
            elif seg.generated:
                header.label(text="", icon='CHECKMARK')

            op_rem = header.operator("kimodo.remove_segment_by_index", text="", icon='X', emboss=False)
            op_rem.index = i

            col = box.column(align=True)
            col.prop(seg, "prompt", text="")
            _draw_prompt_translation(col, seg, s, i)

            row2 = col.row(align=True)
            start_sub = row2.row(align=True)
            start_sub.enabled = (i == 0)
            start_sub.prop(seg, "start_frame", text=tr('Start'))
            row2.prop(seg, "end_frame", text=tr('End'))

            fps = context.scene.render.fps / context.scene.render.fps_base
            dur = (seg.end_frame - seg.start_frame + 1) / fps

            row3 = col.row(align=True)
            row3.label(text=tr('  {v0:.1f}s · {v1} frames').format(v0=dur, v1=seg.end_frame - seg.start_frame + 1),
                      icon='TIME')
            seed_field = row3.row(align=True)
            seed_field.enabled = seg.seed_mode != 'RANDOM'
            seed_field.prop(seg, "seed", text=tr('Seed'))
            seed_modes = row3.row(align=True)
            seed_modes.alignment = 'RIGHT'
            seed_modes.prop(seg, "seed_mode", expand=True)


# ---------------------------------------------------------------------------
# Panel 3: Motion Constraints
# ---------------------------------------------------------------------------

class KIMODO_PT_Constraints(KIMODO_PanelBase, Panel):
    bl_translation_context = 'Kimodo'
    bl_label   = "🎯  Motion Constraints"
    bl_idname  = "KIMODO_PT_Constraints"
    bl_order   = 25
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        s = context.scene.kimodo

        # --- Quick-add buttons ---
        layout.label(text=tr('Add Constraint at Current Frame:'), icon='ADD')
        grid = layout.grid_flow(row_major=True, columns=3, even_columns=True, align=True)

        add_types = [
            ('root2d',      "Root XZ",    'EMPTY_ARROWS'),
            ('fullbody',    "Full-Body",  'ARMATURE_DATA'),
            ('left_hand',   "L.Hand",     'VIEW_PAN'),
            ('right_hand',  "R.Hand",     'VIEW_PAN'),
            ('left_foot',   "L.Foot",     'SNAP_FACE'),
            ('right_foot',  "R.Foot",     'SNAP_FACE'),
        ]
        for ctype, label, icon in add_types:
            op = grid.operator("kimodo.add_constraint", text=tr(label), icon=icon)
            op.constraint_type = ctype

        # Fullbody tip — shown when Full-Body button is in the grid
        has_fullbody = any(ci.constraint_type == 'fullbody' for ci in s.motion_constraints)
        if not has_fullbody:
            tip = layout.box()
            tip.label(text=tr('Full-Body tip:'), icon='INFO')
            tip.label(text=tr('Select an armature first, then click Full-Body.'))
            tip.label(text=tr('Or generate once — source arm will be duplicated.'))

        # --- Curve path waypoint sampler ---
        layout.separator()
        path_box = layout.box()
        path_box.label(text=tr('Sample Curve as Waypoints'), icon='CURVE_DATA')
        split = path_box.split(factor=0.8, align=True)
        split.prop(s, "path_curve", text=tr('Curve'))
        split.operator("kimodo.draw_freehand_curve", text=tr('Draw'), icon='GREASEPENCIL')
        if s.path_curve:
            prow = path_box.row(align=True)
            prow.prop(s, "path_waypoints", text=tr('Points'))
            prow.prop(s, "path_start_frame", text=tr('Start F'))
            prow.prop(s, "path_end_frame", text=tr('End F'))
            path_box.operator(
                "kimodo.sample_curve_as_waypoints",
                text=tr('Sample {v0} Waypoints').format(v0=s.path_waypoints),
                icon='NORMALIZE_FCURVES',
            )

        layout.separator()
        n = len(s.motion_constraints)
        if n:
            layout.label(text=tr('Constraints: {count}').format(count=n), icon='SEQUENCE')
        else:
            layout.label(text=tr('No constraints — motion is unconstrained'), icon='INFO')

        for i, ci in enumerate(s.motion_constraints):
            box = layout.box()

            # --- Row 1: what it is ---
            row = box.row(align=True)
            row.prop(ci, "enabled", text="", emboss=False,
                     icon='CHECKBOX_HLT' if ci.enabled else 'CHECKBOX_DEHLT')

            type_icons = {
                'root2d': 'EMPTY_ARROWS', 'fullbody': 'ARMATURE_DATA',
                'left_hand': 'VIEW_PAN',  'right_hand': 'VIEW_PAN',
                'left_foot': 'SNAP_FACE', 'right_foot': 'SNAP_FACE',
            }
            row.label(text="", icon=type_icons.get(ci.constraint_type, 'DOT'))
            row.prop(ci, "constraint_type", text="")

            op_rem = row.operator("kimodo.remove_constraint", text="", icon='X')
            op_rem.index = i
            op_rem.delete_object = False

            # --- Row 2: when + jump/select. Type labels ("Full-Body Pose",
            # "Root Waypoint"...) are too long to share a row with these and
            # the type dropdown -- that's what crammed everything down to
            # single letters before. ---
            row2 = box.row(align=True)
            row2.prop(ci, "frame", text=tr('Frame'))

            op_goto = row2.operator("kimodo.goto_constraint_frame", text="", icon='TIME')
            op_goto.frame = ci.frame

            op_sel = row2.operator("kimodo.select_constraint_object", text="", icon='RESTRICT_SELECT_OFF')
            op_sel.index = i

            # --- Object picker row — type-aware ---
            sub = box.row(align=True)

            if ci.constraint_type == 'fullbody':
                # Armature picker with validation warning
                obj = ci.marker_object
                if obj and obj.type != 'ARMATURE':
                    # Wrong type — show error
                    sub.alert = True
                    sub.label(text=tr('⚠ Not an armature!'), icon='ERROR')
                    sub.prop(ci, "marker_object", text=tr('Fix →'))
                elif not obj:
                    # Nothing set — show hint
                    sub.alert = True
                    sub.label(text=tr('Select an armature above then click Full-Body again'), icon='INFO')
                    sub.prop(ci, "marker_object", text=tr('Or set →'))
                else:
                    # Valid armature — show normally with bone count hint
                    bone_n = len(obj.data.bones)
                    sub.prop(ci, "marker_object", text=tr('Pose Ref  ({v0} bones)').format(v0=bone_n))
                    sub.operator(
                        "kimodo.select_constraint_object",
                        text="", icon='EDITMODE_HLT',
                    ).index = i
            else:
                # Regular Empty picker for all other types
                sub.prop(ci, "marker_object", text=tr('Marker'))

            # root2d heading extras
            if ci.constraint_type == 'root2d':
                sub2 = box.row(align=True)
                sub2.prop(ci, "include_heading", text=tr('Heading'))
                if ci.include_heading:
                    sub2.prop(ci, "heading_angle", text="")

        layout.separator()

        # --- Settings ---
        box = layout.box()
        box.label(text=tr('Settings'), icon='PREFERENCES')
        row = box.row(align=True)
        row.prop(s, "kimodo_fps")
        row.prop(s, "auto_canonicalize", toggle=True, text=tr('Auto-Origin'))

        layout.separator()

        # --- Actions ---
        row = layout.row(align=True)
        row.operator("kimodo.preview_constraints_json", icon='TEXT', text=tr('Preview JSON'))
        row.operator("kimodo.clear_constraints",        icon='TRASH', text=tr('Clear All'))


# ---------------------------------------------------------------------------
# Panel 4: Retarget
# ---------------------------------------------------------------------------

class KIMODO_PT_Retarget(KIMODO_PanelBase, Panel):
    bl_translation_context = 'Kimodo'
    bl_label   = "🦴  Retarget"
    bl_idname  = "KIMODO_PT_Retarget"
    bl_order   = 30
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        s = context.scene.kimodo

        # Armature pickers
        box = layout.box()
        box.label(text=tr('Armatures'), icon='ARMATURE_DATA')
        box.prop(s, "source_armature", text=tr('Source (Kimodo)'))
        box.prop(s, "target_armature", text=tr('Target (Your Rig)'))
        box.prop(s, "retarget_root_bone", text=tr('Root Bone'))

        layout.separator()

        # Bone mapping list
        layout.label(text=tr('Bone Mapping:'), icon='BONE_DATA')
        layout.label(text=tr("Link toggle = target bone's Inherit Rotation"), icon='LINKED')

        if s.source_armature and s.target_armature:
            # Auto-match button
            layout.operator("kimodo.auto_map_bones",
                            text=tr('Auto-Match Bones'), icon='SHADERFX')

        row = layout.row()
        row.template_list(
            "KIMODO_UL_BoneMappings", "",
            s, "bone_mappings",
            s, "bone_mapping_index",
            rows=6,
        )

        col = row.column(align=True)
        col.operator("kimodo.add_bone_mapping",    text="", icon='ADD')
        col.operator("kimodo.remove_bone_mapping", text="", icon='REMOVE')

        layout.separator()

        # Apply / Remove constraints
        row = layout.row(align=True)
        row.operator("kimodo.apply_retargeting",  text=tr('Apply Constraints'), icon='CONSTRAINT_BONE')
        row.operator("kimodo.remove_retargeting", text="",                  icon='X')

        layout.separator()

        # Bake section
        box = layout.box()
        box.label(text=tr('Bake Animation'), icon='RENDER_ANIMATION')
        row = box.row(align=True)
        row.prop(s, "bake_start_frame", text=tr('Start'))
        row.prop(s, "bake_end_frame",   text=tr('End'))
        box.operator("kimodo.bake_retargeting",
                     text=tr('Bake & Remove Constraints'), icon='NLA_PUSHDOWN')

        layout.separator()

        # Presets
        box = layout.box()
        box.label(text=tr('Bone Map Presets'), icon='PRESET')
        row = box.row(align=True)
        row.prop(s, "preset_name", text="")
        row.operator("kimodo.save_preset", text="", icon='FILE_TICK')
        row.operator("kimodo.load_preset", text="", icon='IMPORT').preset_name = s.preset_name

        # List saved presets
        try:
            prefs = context.preferences.addons[__package__].preferences
            from . import retarget as rt
            preset_names = rt.list_presets(prefs)
        except Exception:
            preset_names = []

        if preset_names:
            col = box.column(align=True)
            for name in preset_names:
                row2 = col.row(align=True)
                op_load = row2.operator("kimodo.load_preset",   text=name, icon='IMPORT')
                op_load.preset_name = name
                op_del  = row2.operator("kimodo.delete_preset", text="",   icon='TRASH')
                op_del.preset_name = name

        # File export / import
        row = box.row(align=True)
        row.operator("kimodo.export_preset_file", text=tr('Export to File'), icon='EXPORT')
        row.operator("kimodo.import_preset_file", text=tr('Import from File'), icon='IMPORT')


# ---------------------------------------------------------------------------
# Panel 4: Help / About
# ---------------------------------------------------------------------------

class KIMODO_PT_Help(KIMODO_PanelBase, Panel):
    bl_translation_context = 'Kimodo'
    bl_label   = "ℹ  Help"
    bl_idname  = "KIMODO_PT_Help"
    bl_order   = 90
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.label(text=tr('Quick Start:'), icon='QUESTION')
        col.separator()
        col.label(text=tr('1. Run the standalone inference server'))
        col.label(text=tr('2. Enter the API URL and click Connect API'))
        col.label(text=tr('   (model loads once, stays loaded)'))
        col.separator()
        col.label(text=tr('3. Enter prompt → Generate Motion'))
        col.label(text=tr('4. In Retarget tab, Pick source + target rigs'))
        col.label(text=tr('5. Auto-Match → Apply Constraints'))
        col.label(text=tr('6. If it does not match, manually add your control bones'))
        col.label(text=tr('7. Click Apply Constraints'))
        col.label(text=tr('8. Bake when satisfied'))
        col.separator()
        col.label(text=tr('Docs & Source:'), icon='URL')
        col.label(text=tr('github.com/nv-tlabs/kimodo'))


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_classes = [
    KIMODO_PT_Connection,
    KIMODO_PT_Generate,
    KIMODO_PT_Constraints,
    KIMODO_PT_Retarget,
    KIMODO_PT_Help,
]


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
