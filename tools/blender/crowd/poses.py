"""Poses and animation clips, written as bone directions in armature space.

A direction is where a bone points, not how much it turns, so the same pose
fits a 1.5 m teen and a 1.9 m broad fan. X is the fan's left, -Y their front,
Z up. Right-side bones mirror the left unless a pose says otherwise.

Clips are key poses on frames at 24 fps. `loop` clips end where they start.
Impostor poses are the eight stills the far crowd flips between.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Matrix, Quaternion, Vector

FPS = 24

ARM_DOWN = {"upperarm.L": (0.20, 0.02, -1), "forearm.L": (0.10, -0.12, -1), "hand.L": (0.08, -0.16, -1)}
LEGS_STAND = {"thigh.L": (0.02, 0.0, -1), "shin.L": (0.0, 0.02, -1), "foot.L": (0, -1, -0.35)}
LEGS_SIT = {"thigh.L": (0.08, -1, 0.05), "shin.L": (0.03, 0.14, -1), "foot.L": (0, -1, -0.25)}
LEGS_SEMI = {"thigh.L": (0.05, -0.8, -0.6), "shin.L": (0.02, 0.35, -1), "foot.L": (0, -1, -0.3)}
TORSO = {"spine": (0, 0.02, 1), "chest": (0, 0.0, 1), "neck": (0, -0.06, 1), "head": (0, -0.04, 1)}

SIT_HIPS = (0.0, 0.30, 0.52)          # pelvis in a seat, in metres for a 1.75 m fan
SEMI_HIPS = (0.0, 0.16, 0.76)

POSES: dict[str, dict] = {
    "stand": {"dirs": {**TORSO, **ARM_DOWN, **LEGS_STAND}},
    "stand_b": {"hips": (0.025, 0.0, 0.965), "dirs": {**TORSO, "spine": (-0.04, 0.02, 1), "head": (0.05, -0.04, 1),
                **LEGS_STAND, "thigh.L": (0.06, 0, -1), "thigh.R": (0.02, 0, -1),
                "upperarm.L": (0.24, -0.35, -1), "forearm.L": (-1, -0.45, 0.12), "hand.L": (-1, -0.2, 0.1),
                "upperarm.R": (-0.24, -0.38, -1), "forearm.R": (1, -0.5, 0.2), "hand.R": (1, -0.2, 0.1)}},
    "sit": {"hips": SIT_HIPS, "dirs": {"spine": (0, 0.12, 1), "chest": (0, 0.05, 1), "neck": (0, -0.12, 1), "head": (0, -0.1, 1),
            **LEGS_SIT, "upperarm.L": (0.12, 0.06, -1), "forearm.L": (0.06, -1, -0.35), "hand.L": (0.03, -1, -0.6)}},
    "sit_b": {"hips": SIT_HIPS, "dirs": {"spine": (0.05, 0.02, 1), "chest": (0.02, -0.08, 1), "neck": (0.0, -0.2, 1), "head": (0.12, -0.15, 1),
              **LEGS_SIT, "thigh.R": (-0.14, -1, 0.05),
              "upperarm.L": (0.10, -0.35, -1), "forearm.L": (0.02, -1, -0.15), "hand.L": (0, -1, -0.4),
              "upperarm.R": (-0.18, -0.5, -1), "forearm.R": (0.2, -0.6, 1), "hand.R": (0.1, -0.2, 1)}},
    "semi": {"hips": SEMI_HIPS, "dirs": {"spine": (0, -0.25, 1), "chest": (0, -0.1, 1), "neck": (0, -0.1, 1), "head": (0, 0.0, 1),
             **LEGS_SEMI, "upperarm.L": (0.35, -0.5, -0.4), "forearm.L": (0.2, -0.6, 0.6), "hand.L": (0.1, -0.3, 1)}},
    "clap_a": {"dirs": {**TORSO, **LEGS_STAND, "upperarm.L": (0.38, -0.75, -0.55), "forearm.L": (0.28, -1, 0.40), "hand.L": (0.2, -1, 0.5)}},
    "clap_b": {"dirs": {**TORSO, **LEGS_STAND, "upperarm.L": (0.14, -0.85, -0.5), "forearm.L": (-0.50, -1, 0.35), "hand.L": (-0.7, -0.8, 0.4)}},
    "cheer_a": {"dirs": {**TORSO, "head": (0, 0.12, 1), "neck": (0, 0.05, 1), **LEGS_STAND,
                "upperarm.L": (0.42, -0.05, 1), "forearm.L": (0.18, 0.0, 1), "hand.L": (0.1, 0, 1)}},
    "cheer_b": {"dirs": {**TORSO, "head": (0, 0.05, 1), **LEGS_STAND,
                "upperarm.L": (0.78, -0.12, 0.62), "forearm.L": (0.40, -0.05, 1), "hand.L": (0.2, 0, 1)}},
    "pump_a": {"dirs": {**TORSO, "head": (-0.05, 0.02, 1), **LEGS_STAND, **ARM_DOWN,
               "upperarm.R": (-0.25, -0.15, 1), "forearm.R": (-0.05, -0.10, 1), "hand.R": (0, -0.1, 1)}},
    "pump_b": {"dirs": {**TORSO, **LEGS_STAND, **ARM_DOWN,
               "upperarm.R": (-0.45, -0.45, 0.75), "forearm.R": (0.1, -1, 0.55), "hand.R": (0.1, -1, 0.5)}},
    "groan": {"dirs": {"spine": (0, -0.14, 1), "chest": (0, -0.12, 1), "neck": (0, -0.35, 1), "head": (0, -0.45, 1), **LEGS_STAND,
              "upperarm.L": (0.82, -0.18, 0.55), "forearm.L": (-0.78, 0.12, 0.62), "hand.L": (-0.6, 0.3, 0.1)}},
    "phone": {"dirs": {**TORSO, "head": (0, -0.12, 1), **LEGS_STAND, **ARM_DOWN,
              "upperarm.R": (-0.16, -0.78, 0.62), "forearm.R": (0.04, -0.35, 1), "hand.R": (0, -0.25, 1)}},
}
for i in range(4):
    th = i * math.pi / 2
    POSES[f"towel_{i}"] = {"dirs": {**TORSO, "head": (0, 0.08, 1), **LEGS_STAND, **ARM_DOWN,
                                    "upperarm.R": (-0.15, 0.0, 1), "forearm.R": (0.75 * math.cos(th), 0.75 * math.sin(th), 0.65),
                                    "hand.R": (0.9 * math.cos(th), 0.9 * math.sin(th), 0.45)}}

CLIPS = {
    "idle_sway": {"loop": True, "keys": [(0, "sit"), (28, "sit_b"), (56, "sit")]},
    "sit": {"loop": True, "keys": [(0, "sit"), (1, "sit")]},
    "stand": {"loop": False, "keys": [(0, "sit"), (8, "semi"), (16, "stand")]},
    "clap": {"loop": True, "keys": [(0, "clap_a"), (6, "clap_b"), (12, "clap_a")]},
    "cheer": {"loop": True, "keys": [(0, "cheer_b"), (8, "cheer_a"), (16, "cheer_b")]},
    "fist_pump": {"loop": True, "keys": [(0, "pump_b"), (6, "pump_a"), (12, "pump_b")]},
    "towel_spin": {"loop": True, "keys": [(0, "towel_0"), (3, "towel_1"), (6, "towel_2"), (9, "towel_3"), (12, "towel_0")]},
    "wave": {"loop": False, "keys": [(0, "sit"), (8, "semi"), (14, "cheer_a"), (22, "semi"), (32, "sit")]},
    "groan": {"loop": False, "keys": [(0, "stand"), (12, "groan"), (40, "groan")]},
    "phone_raise": {"loop": False, "keys": [(0, "stand"), (14, "phone"), (44, "phone")]},
}

IMPOSTOR_POSES = ["sit", "sit_b", "stand", "clap_a", "clap_b", "cheer_a", "cheer_b", "groan"]

# A slot a crowd shows ("cheer_a", "clap_b") is filled per fan from a family
# of real celebrations, so a section on its feet is not one gesture copied
# 24 times. The frozen pose meshes and the impostor atlas both bake the
# fan's own variant into the slot, so no renderer has to know.
TORSO_UP = {"spine": (0, 0.03, 1), "chest": (0, 0.06, 1), "neck": (0, 0.1, 1), "head": (0, 0.16, 1)}
VARIANTS = {
    "cheer_a": [
        # Arms up in a V, elbows soft, chin up.
        {**TORSO_UP, "upperarm.L": (0.55, -0.12, 0.83), "forearm.L": (0.18, -0.2, 1), "hand.L": (0.05, -0.1, 1)},
        # Both fists pumping just above the head, elbows well bent.
        {**TORSO_UP, "upperarm.L": (0.62, -0.28, 0.55), "forearm.L": (-0.35, -0.25, 0.95), "hand.L": (-0.25, -0.05, 1)},
        # Clapping overhead: hands meet above the crown.
        {**TORSO_UP, "upperarm.L": (0.3, -0.3, 0.9), "forearm.L": (-0.7, -0.12, 0.72), "hand.L": (-0.9, 0.0, 0.45)},
        # Turned to high-five a neighbour: lean left, right arm up and across.
        {"spine": (0.12, 0.02, 1), "chest": (0.28, -0.02, 1), "neck": (0.3, -0.05, 1), "head": (0.35, 0.05, 1),
         "upperarm.L": (0.45, -0.3, -0.6), "forearm.L": (0.2, -0.7, 0.4), "hand.L": (0.1, -0.5, 0.8),
         "upperarm.R": (0.35, -0.2, 0.9), "forearm.R": (0.55, 0.0, 0.85), "hand.R": (0.5, 0.05, 1)},
        # Leaning over the row in front, both arms thrown forward and up.
        {"spine": (0, -0.28, 1), "chest": (0, -0.38, 1), "neck": (0, -0.3, 1), "head": (0, -0.1, 1),
         "upperarm.L": (0.35, -0.85, 0.55), "forearm.L": (0.12, -0.55, 0.9), "hand.L": (0.05, -0.3, 1)},
        # One arm punching the air, the other fist at the chest.
        {**TORSO_UP, "upperarm.L": (0.18, -0.35, -0.85), "forearm.L": (-0.45, -0.85, 0.3), "hand.L": (-0.4, -0.6, 0.6),
         "upperarm.R": (-0.25, -0.15, 1), "forearm.R": (-0.05, -0.1, 1), "hand.R": (0, -0.1, 1)},
    ],
    "clap_b": [
        # Hands together in front of the chest, elbows out and down.
        {"upperarm.L": (0.35, -0.55, -0.75), "forearm.L": (-0.75, -0.6, 0.3), "hand.L": (-0.8, -0.4, 0.45)},
        # Clapping at face height.
        {"upperarm.L": (0.45, -0.6, -0.35), "forearm.L": (-0.55, -0.45, 0.7), "hand.L": (-0.7, -0.2, 0.7)},
        # Clapping overhead.
        {"upperarm.L": (0.3, -0.3, 0.9), "forearm.L": (-0.7, -0.12, 0.72), "hand.L": (-0.9, 0.0, 0.45)},
    ],
}


def variant_for(fan_index, pose_name):
    family = VARIANTS.get(pose_name)
    if not family or fan_index is None:
        return {}
    return family[(fan_index * 7 + 3) % len(family)]


def _mirror(dirs: dict) -> dict:
    out = dict(dirs)
    for name, d in dirs.items():
        if name.endswith(".L"):
            r = name[:-2] + ".R"
            if r not in dirs:
                out[r] = (-d[0], d[1], d[2])
    return out


def apply_pose(rig, pose_name: str, height: float, fan_index=None):
    """Set every bone of `rig` to a pose; parents first, so children aim from posed heads.

    With a fan index, a slot that has variants takes that fan's own.
    """
    pose = POSES[pose_name]
    over = variant_for(fan_index, pose_name)
    # A variant's explicit right-side bones win; its left side mirrors unless given.
    base = {k: v for k, v in pose["dirs"].items()}
    base.update({k: v for k, v in over.items() if not k.endswith(".R")})
    dirs = _mirror(base)
    dirs.update({k: v for k, v in over.items() if k.endswith(".R")})
    if rig.get("mpfb"):
        import mh
        mh.apply_pose(rig, dirs, pose.get("hips"), height, pose_name)
        return
    k = height / 1.75
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    order = [b for b in rig.pose.bones]            # created parent-first in fan.BONES
    for pb in order:
        rest = pb.bone.matrix_local
        rest_dir = (pb.bone.tail_local - pb.bone.head_local).normalized()
        if pb.name == "hips" and "hips" in pose:
            head = Vector(pose["hips"]) * k
        else:
            head = pb.head.copy()
        if pb.name in dirs:
            target = Vector(dirs[pb.name]).normalized()
            q = rest_dir.rotation_difference(target)
        elif pb.parent is not None:
            # Unposed bones keep their rest relation to a posed parent.
            parent_rot = (pb.parent.matrix.to_3x3() @ pb.parent.bone.matrix_local.to_3x3().inverted()).to_quaternion()
            q = parent_rot
        else:
            q = Quaternion()
        m = q.to_matrix().to_4x4() @ rest.to_3x3().to_4x4()
        m.translation = head
        pb.matrix = m
        bpy.context.view_layer.update()


def key_pose(rig, frame: int):
    for pb in rig.pose.bones:
        pb.keyframe_insert("rotation_quaternion", frame=frame, group=pb.name)
        if pb.name == "hips":
            pb.keyframe_insert("location", frame=frame, group=pb.name)


def build_actions(rig, height: float, prefix: str) -> dict[str, tuple[int, int]]:
    """One action per clip on this rig. Returns each clip's frame range."""
    ranges = {}
    rig.animation_data_create()
    for clip, spec in CLIPS.items():
        act = bpy.data.actions.new(f"{prefix}{clip}")
        act.use_fake_user = True
        rig.animation_data.action = act
        for frame, pose in spec["keys"]:
            apply_pose(rig, pose, height)
            key_pose(rig, frame)
        ranges[clip] = (spec["keys"][0][0], spec["keys"][-1][0])
    rig.animation_data.action = None
    return ranges
