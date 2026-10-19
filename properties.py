"""
Kimodo Blender Bridge — Properties
All bpy.props definitions: addon preferences, scene-level settings, bone mapping.
"""

from .translations import tr
from . import api_client

import bpy
from bpy.props import (
    StringProperty, FloatProperty, IntProperty, BoolProperty,
    EnumProperty, CollectionProperty, PointerProperty, FloatVectorProperty,
)
from bpy.types import PropertyGroup, AddonPreferences


# ---------------------------------------------------------------------------
# Motion segment (one prompt + time range bar in the timeline)
# ---------------------------------------------------------------------------

# Default colours cycling for new segments
_SEGMENT_COLORS = [
    (0.20, 0.55, 0.90, 0.85),  # blue
    (0.20, 0.75, 0.45, 0.85),  # green
    (0.90, 0.60, 0.15, 0.85),  # orange
    (0.75, 0.25, 0.75, 0.85),  # purple
    (0.90, 0.25, 0.25, 0.85),  # red
    (0.15, 0.80, 0.80, 0.85),  # cyan
    (0.90, 0.85, 0.20, 0.85),  # yellow
]


def _on_end_frame_update(self, context):
    """When a segment's end_frame changes, push the next segment's start_frame forward."""
    s = context.scene.kimodo
    segs = s.motion_segments
    for i, seg in enumerate(segs):
        if seg == self and i + 1 < len(segs):
            next_seg = segs[i + 1]
            duration = next_seg.end_frame - next_seg.start_frame
            next_seg.start_frame = self.end_frame + 1
            next_seg.end_frame = next_seg.start_frame + duration
            
            break
    
    # Update scene frame_end if any segment's end_frame is larger
    if segs:
        max_end_frame = max(seg.end_frame for seg in segs)
        if max_end_frame > context.scene.frame_end:
            context.scene.frame_end = max_end_frame


# ComfyUI-style seed control: exactly one mode is active at a time.
# `seed` is always >= 0. RANDOM mode ignores it and draws a fresh random seed
# each generation. Leaving RANDOM keeps the last generated seed (written back to
# `seed` after generation) so the result can be reproduced.
SEED_MODE_ITEMS = [
    ('FIXED',     "", "Don't edit — keep this exact seed for every generation", 'PINNED',       0),
    ('INCREMENT', "", "Increase the seed by 1 after each generation (+1)",      'ADD',          1),
    ('DECREMENT', "", "Decrease the seed by 1 after each generation (-1)",      'REMOVE',       2),
    ('RANDOM',    "", "Use a new random seed for every generation",             'FILE_REFRESH', 3),
]


def _on_seed_mode_update(self, context):
    """When switching to FIXED, copy last_used_seed into seed so the panel
    field shows the seed that was actually used last — letting the user lock
    the result of a previous INCREMENT/DECREMENT/RANDOM generation."""
    if self.seed_mode == 'FIXED':
        self.seed = self.last_used_seed



class KIMODO_MotionSegment(PropertyGroup):
    """One motion segment: a text prompt mapped to a frame range."""

    prompt_original: StringProperty(translation_context='Kimodo', name="Original Chinese Prompt", default="")

    prompt: StringProperty(translation_context='Kimodo',
        name="Prompt",
        description="Text description of the motion for this segment",
        default="a person walks forward",
    )
    start_frame: IntProperty(translation_context='Kimodo',
        name="Start Frame",
        description="First frame of this motion segment",
        default=1,
        min=0,
    )
    end_frame: IntProperty(translation_context='Kimodo',
        name="End Frame",
        description="Last frame of this motion segment",
        default=60,
        min=1,
        update=_on_end_frame_update,
    )
    model_type: EnumProperty(translation_context='Kimodo',
        name="Model",
        items=[
            ("smpl",  "SOMA / SMPL",  "Standard human body skeleton"),
            #("smplx", "SMPL-X",       "Extended body with hands and face"),
        ],
        default="smpl",
    )
    seed: IntProperty(translation_context='Kimodo',
        name="Seed",
        description="Base seed used in FIXED / INCREMENT / DECREMENT modes (RANDOM ignores it)",
        default=0,
        min=0,
    )
    last_used_seed: IntProperty(translation_context='Kimodo',
        name="Last Used Seed",
        description="Seed actually used in the most recent generation. Switching to FIXED copies this into `seed` so the result can be locked.",
        default=0,
        min=0,
    )
    seed_mode: EnumProperty(translation_context='Kimodo',
        name="Seed Mode",
        description="What happens to the seed after each generation",
        items=SEED_MODE_ITEMS,
        default='RANDOM',
        update=_on_seed_mode_update,
    )
    color: FloatVectorProperty(translation_context='Kimodo',
        name="Color",
        description="Bar colour in the timeline",
        subtype='COLOR_GAMMA',
        size=4,
        min=0.0, max=1.0,
        default=(0.20, 0.55, 0.90, 0.85),
    )
    enabled: BoolProperty(translation_context='Kimodo',
        name="Enabled",
        description="Include this segment in generation",
        default=True,
    )
    # State tracking
    last_bvh_path: StringProperty(translation_context='Kimodo', default="")
    generated: BoolProperty(translation_context='Kimodo', default=False)


# ---------------------------------------------------------------------------
# Constraint item (one Kimodo motion constraint)
# ---------------------------------------------------------------------------

class KIMODO_ConstraintItem(PropertyGroup):
    """A single Kimodo constraint: a Blender object at a frame defines a spatial goal."""

    constraint_type: EnumProperty(translation_context='Kimodo',
        name="Type",
        description="Kimodo constraint type",
        items=[
            ('root2d',      "Root Waypoint",    "2D ground-plane position (XZ). Place an Empty where you want the character's root to be.",  'EMPTY_ARROWS',   0),
            ('fullbody',    "Full-Body Pose",   "Full-body keyframe. Pose an armature exactly as you want the character at this frame.",       'ARMATURE_DATA',  1),
            ('left_hand',   "Left Hand",        "Left wrist/hand end-effector target. Place an Empty at the desired hand position.",          'VIEW_PAN',       2),
            ('right_hand',  "Right Hand",       "Right wrist/hand end-effector target.",                                                     'VIEW_PAN',       3),
            ('left_foot',   "Left Foot",        "Left foot/heel end-effector target. Place an Empty at the desired foot position.",           'SNAP_FACE',      4),
            ('right_foot',  "Right Foot",       "Right foot/heel end-effector target.",                                                      'SNAP_FACE',      5),
        ],
        default='root2d',
    )
    frame: IntProperty(translation_context='Kimodo',
        name="Frame",
        description="Blender frame at which this constraint applies",
        default=1,
        min=0,
    )
    marker_object: PointerProperty(translation_context='Kimodo',
        name="Object",
        description="Empty or Armature that defines the spatial constraint in the viewport",
        type=bpy.types.Object,
    )
    enabled: BoolProperty(translation_context='Kimodo',
        name="Enabled",
        description="Include this constraint in generation",
        default=True,
    )
    # root2d extras
    include_heading: BoolProperty(translation_context='Kimodo',
        name="Include Heading",
        description="Also constrain the facing direction at this waypoint",
        default=False,
    )
    heading_angle: FloatProperty(translation_context='Kimodo',
        name="Heading (°)",
        description="Desired facing direction in degrees (0 = +Y forward in Blender / -Z in Kimodo)",
        default=0.0,
        subtype='ANGLE',
    )
    # display label
    label: StringProperty(translation_context='Kimodo',
        name="Label",
        description="Optional human-readable label for this constraint",
        default="",
    )


# ---------------------------------------------------------------------------
# Generation history entry
# ---------------------------------------------------------------------------

class KIMODO_HistoryEntry(PropertyGroup):
    """One entry in the rolling generation history."""
    prompt: StringProperty(translation_context='Kimodo', name="Prompt", default="")
    seed: IntProperty(translation_context='Kimodo', name="Seed", default=0)
    # Comma-separated per-segment seeds for multi-prompt generations
    # (empty for single-prompt entries and entries from older versions)
    seeds: StringProperty(translation_context='Kimodo', name="Seeds", default="")
    duration: FloatProperty(translation_context='Kimodo', name="Duration", default=5.0)
    bvh_path: StringProperty(translation_context='Kimodo', name="BVH Path", default="")
    timestamp: StringProperty(translation_context='Kimodo', name="Timestamp", default="")


# ---------------------------------------------------------------------------
# Bone mapping item (one row in the UIList)
# ---------------------------------------------------------------------------

def _on_inherit_rotation_update(self, context):
    """Push this entry's inherit-rotation override onto the target bone immediately."""
    arm = context.scene.kimodo.target_armature
    if not arm or not self.target_bone:
        return
    bone = arm.data.bones.get(self.target_bone)
    if bone is not None:
        try:
            bone.use_inherit_rotation = self.inherit_rotation
        except Exception:
            pass


class KIMODO_BoneMappingItem(PropertyGroup):
    """A single source → target bone pair for retargeting."""
    source_bone: StringProperty(translation_context='Kimodo',
        name="Source Bone",
        description="Bone name in the Kimodo-generated armature",
        default="",
    )
    target_bone: StringProperty(translation_context='Kimodo',
        name="Target Bone",
        description="Bone name in your target armature",
        default="",
    )
    enabled: BoolProperty(translation_context='Kimodo',
        name="Enabled",
        description="Include this bone in retargeting",
        default=True,
    )
    retarget_mode: EnumProperty(translation_context='Kimodo',
        name="Mode",
        description="How this bone pair is driven",
        items=[
            ("COPY_ROTATION",    "Copy Rotation",    "Copy only rotation; root bone also gets Copy Location"),
            ("COPY_TRANSFORMS",  "Copy Transforms",  "Copy location + rotation + scale together"),
            ("CHILD_OF",         "Child Of",         "Full parent-child relationship; preserves rest-pose offset"),
            ("CHILD_OF_ROTATION", "Child Of (Rotation)", "Child Of constraint with only rotation enabled (no location or scale)"),
        ],
        default="CHILD_OF",
    )
    inherit_rotation: BoolProperty(translation_context='Kimodo',
        name="Inherit Rotation",
        description=(
            "Override the target bone's 'Inherit Rotation' property. When unchecked, "
            "this bone will not inherit rotation from its parent. Applied immediately "
            "on toggle and again when you click Apply Constraints"
        ),
        default=True,
        update=_on_inherit_rotation_update,
    )


# ---------------------------------------------------------------------------
# Scene-level settings
# ---------------------------------------------------------------------------

class KIMODO_SceneSettings(PropertyGroup):
    """Stored on bpy.context.scene.kimodo — all per-scene settings."""

    prompt_original: StringProperty(translation_context='Kimodo', name="Original Chinese Prompt", default="")
    translation_service: EnumProperty(translation_context='Kimodo',
        name="Translation Service",
        description="Online translation without an API key; text is sent to the selected service only when you click Translate",
        items=[('AUTO', 'Auto (Alibaba / Youdao)', 'Try Alibaba first, then Youdao'),
               ('ALIBABA', 'Alibaba (Free)', 'Alibaba web translator, no API key'),
               ('YOUDAO', 'Youdao (Free)', 'Youdao demo translator; 1000-character limit')],
        default='AUTO',
    )
    is_translating: BoolProperty(translation_context='Kimodo', default=False, options={'SKIP_SAVE'})
    translation_status: StringProperty(translation_context='Kimodo', default="", options={'SKIP_SAVE'})

    # API connection lives in preferences; secrets are not saved into .blend.
    api_model: EnumProperty(translation_context='Kimodo', name="API Model",
        items=api_client.model_items, default=100)
    api_encoder: EnumProperty(translation_context='Kimodo', name="Text Encoder",
        items=api_client.encoder_items, default=100)
    block_swap: IntProperty(translation_context='Kimodo', name="Motion Block Swap",
        description="-1 uses server settings; 0 disables; positive values offload this many transformer blocks to CPU",
        default=-1,min=-1,max=128)
    text_block_swap: IntProperty(translation_context='Kimodo', name="Text Block Swap",
        description="-1 uses encoder settings; 0 disables; positive values swap text encoder layers",
        default=-1,min=-1,max=32)
    is_connecting: BoolProperty(default=False, options={'SKIP_SAVE'})
    connection_status: StringProperty(default="Not started", options={'SKIP_SAVE'})
    is_connected: BoolProperty(default=False, options={'SKIP_SAVE'})
    diffusion_steps: IntProperty(translation_context='Kimodo', name="Diffusion Steps",
        description="More denoising steps cost more time; 100 is the reference setting",
        default=100, min=1, max=1000)
    cfg_text: FloatProperty(translation_context='Kimodo', name="Text Guidance", default=2.0, min=0, max=10)
    cfg_constraints: FloatProperty(translation_context='Kimodo', name="Constraint Guidance", default=2.0, min=0, max=10)
    post_processing: BoolProperty(translation_context='Kimodo', name="Motion Post-processing",
        description="Requires the optional motion_correction package on the API server", default=False)
    show_inference_settings: BoolProperty(default=False)

    # --- Generation ---
    model_type: StringProperty(default='smpl', options={'HIDDEN'})
    generate_mode: EnumProperty(translation_context='Kimodo',
        name="Generate Mode",
        description="Single Clip generates one motion from one prompt. "
                     "Timeline builds a longer animation from multiple "
                     "prompt segments stitched together",
        items=[
            ("SINGLE",   "Single Clip", "One prompt, one motion clip"),
            ("TIMELINE", "Timeline",    "Multiple prompt segments stitched into one animation"),
        ],
        default="SINGLE",
    )
    prompt: StringProperty(translation_context='Kimodo',
        name="Prompt",
        description="Text description of the motion to generate",
        default="a person walks forward",
    )
    duration: FloatProperty(translation_context='Kimodo',
        name="Duration (s)",
        description="Length of the generated motion in seconds",
        default=5.0,
        min=1.0,
        max=30.0,
        step=50,
    )
    seed: IntProperty(translation_context='Kimodo',
        name="Seed",
        description="Base seed used in FIXED / INCREMENT / DECREMENT modes (RANDOM ignores it)",
        default=0,
        min=0,
    )
    last_used_seed: IntProperty(translation_context='Kimodo',
        name="Last Used Seed",
        description="Seed actually used in the most recent generation. Switching to FIXED copies this into `seed` so the result can be locked.",
        default=0,
        min=0,
    )
    seed_mode: EnumProperty(translation_context='Kimodo',
        name="Seed Mode",
        description="What happens to the seed after each generation",
        items=SEED_MODE_ITEMS,
        default='RANDOM',
        update=_on_seed_mode_update,
    )
    output_format: EnumProperty(translation_context='Kimodo',
        name="Format",
        description="File format Kimodo should export",
        items=[
            ("bvh", "BVH",  "Standard motion capture format. Blender imports natively."),
            ("npz", "NPZ",  "Kimodo native format (requires manual import)."),
        ],
        default="bvh",
    )
    bvh_standard_tpose: BoolProperty(translation_context='Kimodo',
        name="Use Standard T-Pose",
        description="Export BVH with standard T-pose rest pose instead of BONES-SEED pose (SOMA models only)",
        default=True,
    )
    reuse_armature: PointerProperty(translation_context='Kimodo',
        name="Reuse Armature",
        description=(
            "Apply generated motion to this armature instead of creating a new one. "
            "Preserves retargeting constraints already pointing at it. "
            "Leave empty to always create a new armature."
        ),
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'ARMATURE',
    )

    # Generation state (used by the modal operator)
    is_generating: BoolProperty(translation_context='Kimodo', default=False)
    generation_progress: StringProperty(translation_context='Kimodo', default="")
    last_bvh_path: StringProperty(translation_context='Kimodo',
        name="Last BVH Path",
        description="Path of the most recently imported motion file",
        default="",
    )

    # --- Motion Segments (timeline bars) ---
    motion_segments: CollectionProperty(translation_context='Kimodo', type=KIMODO_MotionSegment)
    segment_index: IntProperty(translation_context='Kimodo',
        name="Active Segment",
        description="Currently selected motion segment",
        default=0,
    )
    # Which segment is currently being generated (for multi-generate progress)
    generating_segment_index: IntProperty(translation_context='Kimodo', default=-1)

    # --- Retargeting ---
    source_armature: PointerProperty(translation_context='Kimodo',
        name="Source Armature",
        description="The Kimodo-generated armature (imported from BVH)",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'ARMATURE',
    )
    target_armature: PointerProperty(translation_context='Kimodo',
        name="Target Armature",
        description="Your character's armature to drive with the motion",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'ARMATURE',
    )
    bone_mappings: CollectionProperty(translation_context='Kimodo', type=KIMODO_BoneMappingItem)
    bone_mapping_index: IntProperty(translation_context='Kimodo', default=0)
    retarget_root_bone: StringProperty(translation_context='Kimodo',
        name="Root Bone (Target)",
        description="Root / hip bone on the target armature (gets position + rotation)",
        default="",
    )
    bake_start_frame: IntProperty(translation_context='Kimodo', name="Start Frame", default=1, min=0)
    bake_end_frame: IntProperty(translation_context='Kimodo', name="End Frame", default=250, min=1)

    # --- Motion Constraints ---
    motion_constraints: CollectionProperty(translation_context='Kimodo', type=KIMODO_ConstraintItem)
    constraint_index: IntProperty(translation_context='Kimodo', default=0)
    kimodo_fps: FloatProperty(translation_context='Kimodo',
        name="Kimodo FPS",
        description="Frames-per-second Kimodo generates at (default 30). "
                    "Used to convert Blender frame numbers to Kimodo frame indices.",
        default=30.0,
        min=1.0,
        max=120.0,
    )
    auto_canonicalize: BoolProperty(translation_context='Kimodo',
        name="Auto-Canonicalize",
        description="Automatically offset all constraint positions so the earliest "
                    "waypoint lands at Kimodo's (0,0) origin.",
        default=False,
    )
    constraint_json_preview: StringProperty(translation_context='Kimodo',
        name="Constraint JSON",
        description="Last-built constraints JSON (read-only preview)",
        default="",
    )

    # --- Multi-segment generation ---
    num_transition_frames: IntProperty(translation_context='Kimodo',
        name="Transition Frames",
        description="Number of blended frames between segments in multi-prompt generation",
        default=5,
        min=1,
        max=30,
    )

    # --- Generation history ---
    generation_history: CollectionProperty(translation_context='Kimodo', type=KIMODO_HistoryEntry)
    history_index: IntProperty(translation_context='Kimodo', name="Active History Entry", default=0)
    history_expanded: BoolProperty(translation_context='Kimodo',
        name="Show History",
        description="Expand / collapse the generation history list",
        default=False,
    )

    # --- Variations ---
    num_variations: IntProperty(translation_context='Kimodo',
        name="Variations",
        description="Number of random-seed variations to generate",
        default=3,
        min=2,
        max=5,
    )

    # --- Curve path sampling ---
    path_curve: PointerProperty(translation_context='Kimodo',
        name="Path Curve",
        description="Bezier or NURBS curve to sample as root XZ waypoints",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'CURVE',
    )
    path_waypoints: IntProperty(translation_context='Kimodo',
        name="Waypoints",
        description="Number of evenly-spaced waypoints to sample from the curve",
        default=8,
        min=2,
        max=30,
    )
    path_start_frame: IntProperty(translation_context='Kimodo',
        name="Start Frame",
        description="Timeline frame for the first waypoint",
        default=1,
        min=0,
    )
    path_end_frame: IntProperty(translation_context='Kimodo',
        name="End Frame",
        description="Timeline frame for the last waypoint",
        default=90,
        min=1,
    )

    # Preset name for saving
    preset_name: StringProperty(translation_context='Kimodo',
        name="Preset Name",
        description="Name to save / load bone mapping preset",
        default="my_rig",
    )


# ---------------------------------------------------------------------------
# Addon preferences
# ---------------------------------------------------------------------------

class KIMODO_AddonPreferences(AddonPreferences):
    bl_translation_context = 'Kimodo'
    bl_idname = __package__

    saved_presets: StringProperty(translation_context='Kimodo',
        name="Saved Presets",
        description="JSON blob of all saved bone-mapping presets",
        default="{}",
    )

    server_url: StringProperty(translation_context='Kimodo', name="API URL",
        description="Address of the standalone Kimodo inference server",
        default="http://127.0.0.1:6600")
    api_token: StringProperty(translation_context='Kimodo', name="API Token",
        description="Optional server token; leave blank for a local server without authentication",
        default="", subtype='PASSWORD')

    def draw(self, context):
        self.layout.prop(self, 'server_url')
        self.layout.prop(self, 'api_token')
        self.layout.label(text=tr('Run the inference server separately, then connect in the Kimodo sidebar.'))


# ---------------------------------------------------------------------------
# Transient-state cleanup (#43)
# ---------------------------------------------------------------------------
# is_generating / generation_progress are scene properties, so Blender saves
# them into the .blend (and undo can restore them). A loaded file can never
# have a live generation, so a saved is_generating=True would permanently
# gray out the Generate button behind a "Cancelling…" that never finishes.

def _reset_transient_generation_state() -> None:
    for scene in bpy.data.scenes:
        k = getattr(scene, "kimodo", None)
        if k is None:
            continue
        if k.is_generating:
            k.is_generating = False
        if k.generation_progress:
            k.generation_progress = ""
        if k.generating_segment_index != -1:
            k.generating_segment_index = -1
        k.is_connected = False
        k.is_connecting = False
        k.connection_status = 'Not started'
        k.is_translating = False
        k.translation_status = ''


@bpy.app.handlers.persistent
def _on_load_post(_filepath):
    _reset_transient_generation_state()


def _reset_after_register():
    """One-shot bpy.app.timers callback: clears stuck state in the file that
    is already open when the addon is enabled/updated (load_post won't fire
    for it)."""
    try:
        _reset_transient_generation_state()
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_classes = [
    KIMODO_MotionSegment,
    KIMODO_ConstraintItem,
    KIMODO_BoneMappingItem,
    KIMODO_HistoryEntry,
    KIMODO_SceneSettings,
    KIMODO_AddonPreferences,
]


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.kimodo = PointerProperty(translation_context='Kimodo', type=KIMODO_SceneSettings)
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)
    # bpy.data is restricted while addons register at startup; defer the
    # cleanup of the already-open file to a one-shot timer.
    bpy.app.timers.register(_reset_after_register, first_interval=0.0)


def unregister():
    if bpy.app.timers.is_registered(_reset_after_register):
        bpy.app.timers.unregister(_reset_after_register)
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    del bpy.types.Scene.kimodo
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
