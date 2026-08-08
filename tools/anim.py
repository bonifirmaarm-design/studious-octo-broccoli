"""Hand-authored animation clips for the Mega Knight rig.

Poses are written as euler angles in degrees per joint; the builder samples them
onto a fixed frame rate with eased interpolation, which is what gives the
punch its snap and the jump its hang time.
"""

import numpy as np

FPS = 30
DEG = np.pi / 180.0


def quat_from_euler(x, y, z):
    cx, sx = np.cos(x / 2), np.sin(x / 2)
    cy, sy = np.cos(y / 2), np.sin(y / 2)
    cz, sz = np.cos(z / 2), np.sin(z / 2)
    return np.array([
        sx * cy * cz + cx * sy * sz,
        cx * sy * cz - sx * cy * sz,
        cx * cy * sz + sx * sy * cz,
        cx * cy * cz - sx * sy * sz,
    ])


def ease(t, kind="smooth"):
    t = np.clip(t, 0.0, 1.0)
    if kind == "linear":
        return t
    if kind == "smooth":
        return t * t * (3 - 2 * t)
    if kind == "in":            # slow start, used for wind-ups
        return t * t * t
    if kind == "out":           # fast start, used for impacts
        return 1 - (1 - t) ** 3
    if kind == "snap":          # very fast start, for the strike itself
        return 1 - (1 - t) ** 5
    if kind == "anticipate":    # dips backwards before moving forward
        return t * t * (2.70158 * t - 1.70158)
    if kind == "overshoot":
        return 1 + 2.2 * (t - 1) ** 3 + 1.2 * (t - 1) ** 2
    raise ValueError(kind)


class Clip:
    """A list of keyframes; each keyframe is a time plus a pose dict."""

    def __init__(self, name, loop=True):
        self.name = name
        self.loop = loop
        self.keys = []  # (time, pose, easing)

    def key(self, time, pose, easing="smooth"):
        """pose: {joint: (rx, ry, rz)} degrees, plus optional 'root_pos'/'root_scale'."""
        self.keys.append((time, pose, easing))
        return self

    @property
    def duration(self):
        return max(t for t, _, _ in self.keys)

    def _joints(self):
        names = set()
        for _, pose, _ in self.keys:
            names.update(k for k in pose if k not in ("root_pos", "root_scale"))
        return sorted(names)

    def sample(self):
        """Returns (times, {joint: quats}, root_translation, root_scale)."""
        duration = self.duration
        frames = max(2, int(round(duration * FPS)) + 1)
        times = np.linspace(0.0, duration, frames)

        joints = self._joints()
        rotations = {name: np.zeros((frames, 3)) for name in joints}
        root_pos = np.zeros((frames, 3))
        root_scale = np.ones((frames, 3))

        def value_at(index, channel, default):
            """Interpolate one channel across the keyframe list."""
            keyed = [(t, pose[channel], easing) for t, pose, easing in self.keys if channel in pose]
            if not keyed:
                return np.tile(default, (frames, 1))
            out = np.zeros((frames, len(default)))
            for i, t in enumerate(times):
                if t <= keyed[0][0]:
                    out[i] = keyed[0][1]
                    continue
                if t >= keyed[-1][0]:
                    out[i] = keyed[-1][1]
                    continue
                for k in range(len(keyed) - 1):
                    t0, v0, _ = keyed[k]
                    t1, v1, easing = keyed[k + 1]
                    if t0 <= t <= t1:
                        span = max(t1 - t0, 1e-6)
                        a = ease((t - t0) / span, easing)
                        out[i] = np.asarray(v0) + (np.asarray(v1) - np.asarray(v0)) * a
                        break
            return out

        for name in joints:
            rotations[name] = value_at(None, name, (0.0, 0.0, 0.0))
        root_pos = value_at(None, "root_pos", (0.0, 0.0, 0.0))
        root_scale = value_at(None, "root_scale", (1.0, 1.0, 1.0))

        quats = {name: np.array([quat_from_euler(*(row * DEG)) for row in rotations[name]])
                 for name in joints}
        return times, quats, root_pos, root_scale


# --------------------------------------------------------------------------
# The clips. Angles are degrees, applied in each joint's parent frame.
#
# Rotation conventions for this rig (+Z is the direction the knight faces):
#   * Bones that point UP   (Spine, Chest, Neck, Head): +X leans forward.
#   * Bones that point DOWN (arms, legs):               -X swings forward.
#   * Arms: -Z raises the left arm, +Z raises the right arm (outwards/up).
#   * +Y on Hips/Spine/Chest twists the torso to the knight's right.
# --------------------------------------------------------------------------

REST = {
    "Hips": (0, 0, 0), "Spine": (0, 0, 0), "Chest": (0, 0, 0), "Head": (0, 0, 0),
    "Shoulder.L": (0, 0, 0), "Shoulder.R": (0, 0, 0),
    "UpperArm.L": (0, 0, 0), "UpperArm.R": (0, 0, 0),
    "Fist.L": (0, 0, 0), "Fist.R": (0, 0, 0),
    "Thigh.L": (0, 0, 0), "Thigh.R": (0, 0, 0),
    "Shin.L": (0, 0, 0), "Shin.R": (0, 0, 0),
    "Foot.L": (0, 0, 0), "Foot.R": (0, 0, 0),
    "root_pos": (0, 0, 0), "root_scale": (1, 1, 1),
}


def rest(**overrides):
    pose = dict(REST)
    pose.update(overrides)
    return pose


def idle():
    """Slow breathing, weight rocking gently between the feet."""
    clip = Clip("Idle")
    clip.key(0.0, rest())
    clip.key(1.1, rest(**{
        "Hips": (-1.5, 0, 0), "Spine": (2.0, 0, 0), "Chest": (1.5, 0, 0), "Head": (-2.0, 0, 0),
        "Shoulder.L": (0, 0, -4), "Shoulder.R": (0, 0, 4),
        "UpperArm.L": (3, 0, -3), "UpperArm.R": (3, 0, 3),
        "root_pos": (0, 0.016, 0),
    }))
    clip.key(2.2, rest())
    return clip


def walk():
    """Heavy, wide-stance stomp -- the Mega Knight does not stroll."""
    clip = Clip("Walk")

    def pose(phase, lift):
        # phase +1: left leg forward. Forward for a leg is -X.
        left, right = -24 * phase, 24 * phase
        return rest(**{
            "Hips": (0, 3 * phase, 0),
            "Spine": (3, -2 * phase, 0),
            "Chest": (1, -1.5 * phase, 0),
            "Head": (-3, 1.5 * phase, 0),
            "Thigh.L": (left, 0, 0), "Thigh.R": (right, 0, 0),
            "Shin.L": (max(0.0, left) * 1.1, 0, 0),
            "Shin.R": (max(0.0, right) * 1.1, 0, 0),
            "Shoulder.L": (0, 0, -5), "Shoulder.R": (0, 0, 5),
            "UpperArm.L": (right * 0.45, 0, -5), "UpperArm.R": (left * 0.45, 0, 5),
            "root_pos": (0, lift, 0),
        })

    clip.key(0.00, pose(1, 0.0))
    clip.key(0.22, pose(0.35, 0.03))
    clip.key(0.44, pose(-1, 0.0))
    clip.key(0.66, pose(-0.35, 0.03))
    clip.key(0.88, pose(1, 0.0))
    return clip


def punch():
    """Right fist driven straight forward, torso rotating through the hit."""
    clip = Clip("Punch", loop=False)
    clip.key(0.00, rest())

    # 1. Wind-up: twist away, right fist pulled back and cocked up a little.
    clip.key(0.28, rest(**{
        "Hips": (0, 10, 0), "Spine": (-3, 6, 0), "Chest": (-3, 7, 0), "Head": (2, -7, 0),
        "Shoulder.R": (10, 6, 8), "UpperArm.R": (24, 8, 16), "Fist.R": (8, 0, 6),
        "Shoulder.L": (-4, -4, -3), "UpperArm.L": (-8, -5, -5),
        "Thigh.L": (3, 0, 0), "Thigh.R": (-4, 0, 0),
        "root_pos": (0, -0.02, -0.04), "root_scale": (1.02, 0.98, 1.02),
    }), "in")

    # 2. Strike: hips lead, the arm swings forward (-X) and up (+Z on the
    #    right arm) so the fist lands at chest height rather than by the knee.
    clip.key(0.42, rest(**{
        "Hips": (0, -13, 0), "Spine": (5, -8, 0), "Chest": (6, -9, 0), "Head": (-4, 6, 0),
        "Shoulder.R": (-14, -8, 14), "UpperArm.R": (-52, -10, 34), "Fist.R": (-14, 0, 8),
        "Shoulder.L": (6, 5, -4), "UpperArm.L": (13, 6, -7),
        "Thigh.L": (-6, 0, 0), "Thigh.R": (6, 0, 0),
        "root_pos": (0, 0.005, 0.12), "root_scale": (0.98, 1.02, 1.03),
    }), "snap")

    # 3. Follow-through, arm still extended.
    clip.key(0.64, rest(**{
        "Hips": (0, -9, 0), "Spine": (3, -6, 0), "Chest": (4, -6, 0), "Head": (-2, 4, 0),
        "Shoulder.R": (-9, -5, 9), "UpperArm.R": (-34, -6, 22), "Fist.R": (-8, 0, 5),
        "Shoulder.L": (4, 3, -2), "UpperArm.L": (8, 4, -4),
        "Thigh.L": (-4, 0, 0), "Thigh.R": (4, 0, 0),
        "root_pos": (0, 0, 0.08),
    }), "out")

    clip.key(1.05, rest(), "smooth")
    return clip


def smash():
    """Both fists raised, then driven into the ground."""
    clip = Clip("Smash", loop=False)
    clip.key(0.00, rest())

    # Load: arms swing up and out, chest opens back. The torso angles stay
    # small on purpose -- they stack down the chain, so 5 + 6 + 6 already
    # reads as a big arch on a body this wide.
    clip.key(0.36, rest(**{
        "Hips": (-3, 0, 0), "Spine": (-6, 0, 0), "Chest": (-6, 0, 0), "Head": (-7, 0, 0),
        "Shoulder.L": (-8, 0, -16), "Shoulder.R": (-8, 0, 16),
        "UpperArm.L": (-16, 0, -30), "UpperArm.R": (-16, 0, 30),
        "Fist.L": (0, 0, -10), "Fist.R": (0, 0, 10),
        "Thigh.L": (4, 0, 0), "Thigh.R": (4, 0, 0),
        "root_pos": (0, 0.05, -0.03), "root_scale": (0.97, 1.05, 0.97),
    }), "in")

    # Slam: arms drive down past rest, body folds over the impact.
    clip.key(0.52, rest(**{
        "Hips": (7, 0, 0), "Spine": (8, 0, 0), "Chest": (8, 0, 0), "Head": (5, 0, 0),
        "Shoulder.L": (-10, 0, 8), "Shoulder.R": (-10, 0, -8),
        "UpperArm.L": (-20, 0, 14), "UpperArm.R": (-20, 0, -14),
        "Fist.L": (-10, 0, 5), "Fist.R": (-10, 0, -5),
        "Thigh.L": (-14, 0, 0), "Thigh.R": (-14, 0, 0),
        "Shin.L": (18, 0, 0), "Shin.R": (18, 0, 0),
        "root_pos": (0, -0.09, 0.04), "root_scale": (1.07, 0.91, 1.07),
    }), "snap")

    # Rebound out of the crouch.
    clip.key(0.72, rest(**{
        "Hips": (3, 0, 0), "Spine": (4, 0, 0), "Chest": (4, 0, 0), "Head": (2, 0, 0),
        "Shoulder.L": (-5, 0, 4), "Shoulder.R": (-5, 0, -4),
        "UpperArm.L": (-10, 0, 7), "UpperArm.R": (-10, 0, -7),
        "Thigh.L": (-7, 0, 0), "Thigh.R": (-7, 0, 0),
        "Shin.L": (9, 0, 0), "Shin.R": (9, 0, 0),
        "root_pos": (0, -0.03, 0.02), "root_scale": (1.04, 0.96, 1.04),
    }), "out")

    clip.key(1.15, rest(), "smooth")
    return clip


def jump(distance=2.6, height=1.6):
    """Crouch, launch, tuck at the apex, then land fists first.

    The knight is mostly torso with very short legs, so the crouch and the
    landing are carried by the root squash and the arc of the root, with the
    legs only reinforcing them.
    """
    clip = Clip("Jump", loop=False)
    clip.key(0.00, rest())

    # Crouch: knees drive forward (-X thigh), shins fold back (+X shin).
    clip.key(0.34, rest(**{
        "Hips": (5, 0, 0), "Spine": (6, 0, 0), "Chest": (5, 0, 0), "Head": (-4, 0, 0),
        "Thigh.L": (-20, 0, 0), "Thigh.R": (-20, 0, 0),
        "Shin.L": (28, 0, 0), "Shin.R": (28, 0, 0),
        "Foot.L": (-9, 0, 0), "Foot.R": (-9, 0, 0),
        "Shoulder.L": (12, 0, 3), "Shoulder.R": (12, 0, -3),
        "UpperArm.L": (24, 0, 6), "UpperArm.R": (24, 0, -6),
        "root_pos": (0, -0.13, -0.05), "root_scale": (1.06, 0.91, 1.06),
    }), "in")

    # Launch: legs snap straight, arms thrown up and out.
    clip.key(0.52, rest(**{
        "Hips": (-4, 0, 0), "Spine": (-5, 0, 0), "Chest": (-4, 0, 0), "Head": (-6, 0, 0),
        "Thigh.L": (6, 0, 0), "Thigh.R": (6, 0, 0),
        "Shin.L": (-3, 0, 0), "Shin.R": (-3, 0, 0),
        "Foot.L": (12, 0, 0), "Foot.R": (12, 0, 0),
        "Shoulder.L": (-6, 0, -14), "Shoulder.R": (-6, 0, 14),
        "UpperArm.L": (-12, 0, -26), "UpperArm.R": (-12, 0, 26),
        "root_pos": (0, height * 0.42, distance * 0.16), "root_scale": (0.92, 1.13, 0.92),
    }), "snap")

    # Apex: knees tucked up, fists cocked ready to come down.
    clip.key(0.86, rest(**{
        "Hips": (5, 0, 0), "Spine": (-3, 0, 0), "Chest": (-5, 0, 0), "Head": (-3, 0, 0),
        "Thigh.L": (-30, 0, 0), "Thigh.R": (-30, 0, 0),
        "Shin.L": (40, 0, 0), "Shin.R": (40, 0, 0),
        "Foot.L": (-12, 0, 0), "Foot.R": (-12, 0, 0),
        "Shoulder.L": (-9, 0, -18), "Shoulder.R": (-9, 0, 18),
        "UpperArm.L": (-18, 0, -32), "UpperArm.R": (-18, 0, 32),
        "Fist.L": (0, 0, -10), "Fist.R": (0, 0, 10),
        "root_pos": (0, height, distance * 0.5), "root_scale": (0.96, 1.05, 0.96),
    }), "out")

    # Falling: legs reach down for the ground, fists still up.
    clip.key(1.16, rest(**{
        "Hips": (2, 0, 0), "Spine": (1, 0, 0), "Chest": (-2, 0, 0), "Head": (2, 0, 0),
        "Thigh.L": (-9, 0, 0), "Thigh.R": (-9, 0, 0),
        "Shin.L": (10, 0, 0), "Shin.R": (10, 0, 0),
        "Foot.L": (-3, 0, 0), "Foot.R": (-3, 0, 0),
        "Shoulder.L": (-8, 0, -15), "Shoulder.R": (-8, 0, 15),
        "UpperArm.L": (-16, 0, -28), "UpperArm.R": (-16, 0, 28),
        "Fist.L": (0, 0, -8), "Fist.R": (0, 0, 8),
        "root_pos": (0, height * 0.42, distance * 0.84), "root_scale": (0.94, 1.09, 0.94),
    }), "in")

    # Impact: full squash, both fists driven into the ground.
    clip.key(1.30, rest(**{
        "Hips": (8, 0, 0), "Spine": (8, 0, 0), "Chest": (8, 0, 0), "Head": (5, 0, 0),
        "Thigh.L": (-30, 0, -8), "Thigh.R": (-30, 0, 8),
        "Shin.L": (40, 0, 0), "Shin.R": (40, 0, 0),
        "Foot.L": (-13, 0, 0), "Foot.R": (-13, 0, 0),
        "Shoulder.L": (-12, 0, 10), "Shoulder.R": (-12, 0, -10),
        "UpperArm.L": (-24, 0, 16), "UpperArm.R": (-24, 0, -16),
        "Fist.L": (-10, 0, 6), "Fist.R": (-10, 0, -6),
        "root_pos": (0, -0.15, distance), "root_scale": (1.10, 0.88, 1.10),
    }), "snap")

    # Push back up out of the landing crouch.
    clip.key(1.54, rest(**{
        "Hips": (4, 0, 0), "Spine": (3, 0, 0), "Chest": (3, 0, 0), "Head": (2, 0, 0),
        "Thigh.L": (-13, 0, -3), "Thigh.R": (-13, 0, 3),
        "Shin.L": (17, 0, 0), "Shin.R": (17, 0, 0),
        "Foot.L": (-5, 0, 0), "Foot.R": (-5, 0, 0),
        "Shoulder.L": (-5, 0, 4), "Shoulder.R": (-5, 0, -4),
        "UpperArm.L": (-9, 0, 7), "UpperArm.R": (-9, 0, -7),
        "root_pos": (0, -0.05, distance), "root_scale": (1.06, 0.95, 1.06),
    }), "out")

    clip.key(1.95, rest(root_pos=(0, 0, distance)), "smooth")
    return clip


def hit():
    """Short flinch for the knight on the receiving end of a punch."""
    clip = Clip("Hit", loop=False)
    clip.key(0.00, rest())
    clip.key(0.10, rest(**{
        "Hips": (-12, 0, 0), "Spine": (-14, 0, 0), "Chest": (-12, 0, 0), "Head": (-20, 0, 0),
        "Shoulder.L": (6, 0, -10), "Shoulder.R": (6, 0, 10),
        "UpperArm.L": (14, 0, -16), "UpperArm.R": (14, 0, 16),
        "root_pos": (0, 0.02, -0.16), "root_scale": (0.96, 1.04, 0.96),
    }), "snap")
    clip.key(0.30, rest(**{
        "Hips": (-5, 0, 0), "Spine": (-5, 0, 0), "Chest": (-4, 0, 0), "Head": (-8, 0, 0),
        "Shoulder.L": (2, 0, -4), "Shoulder.R": (2, 0, 4),
        "UpperArm.L": (6, 0, -7), "UpperArm.R": (6, 0, 7),
        "root_pos": (0, 0, -0.06),
    }), "out")
    clip.key(0.62, rest(), "smooth")
    return clip


ALL_CLIPS = [idle, walk, punch, smash, jump, hit]
