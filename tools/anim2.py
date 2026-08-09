"""Animation clips authored against the oriented rig in rig2.py.

Because every bone points along its own local +Y, the same numbers mean the
same motion on every character:

    forward  (+X)  swings a limb towards the facing side
    twist    (+Y)  rotates it about its own length
    out      (+Z)  swings it sideways -- mirrored between .L and .R

Use `sym()` to write a symmetric pose once; it flips twist and out for the
left side. No clip carries horizontal root motion: the game moves units
itself, so clips only ever lift the root off the ground.
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
    return {
        "linear": t,
        "smooth": t * t * (3 - 2 * t),
        "in": t * t * t,
        "out": 1 - (1 - t) ** 3,
        "snap": 1 - (1 - t) ** 5,
    }[kind]


def side(pose, name, forward=0.0, twist=0.0, out=0.0):
    """Add a rotation to one joint, on top of whatever the pose already has.

    Poses are additive so a character's rest correction -- dropping arms out
    of the T-pose the model was scanned in -- can be layered under every clip.
    """
    have = pose.get(name, (0.0, 0.0, 0.0))
    pose[name] = (have[0] + forward, have[1] + twist, have[2] + out)
    return pose


def sym(pose, base, forward=0.0, twist=0.0, out=0.0):
    """Add a mirrored pair: `base`.R gets (f, t, o), `base`.L gets (f, -t, -o)."""
    side(pose, f"{base}.R", forward, twist, out)
    side(pose, f"{base}.L", forward, -twist, -out)
    return pose


def scaled(pose, factor, keep=("root_scale",)):
    """A weaker version of a pose, used for follow-through keys."""
    out = {}
    for k, v in pose.items():
        out[k] = v if k in keep else tuple(np.asarray(v) * factor)
    if "root_scale" in pose:
        out["root_scale"] = (1.0, 1.0, 1.0)
    return out


class Clip:
    def __init__(self, name, loop=True):
        self.name = name
        self.loop = loop
        self.keys = []

    def key(self, time, pose, easing="smooth"):
        self.keys.append((time, pose, easing))
        return self

    @property
    def duration(self):
        return max(t for t, _, _ in self.keys)

    def sample(self, joint_names):
        frames = max(2, int(round(self.duration * FPS)) + 1)
        times = np.linspace(0.0, self.duration, frames)

        channels = set()
        for _, pose, _ in self.keys:
            channels.update(pose)

        def track(channel, default):
            keyed = [(t, pose[channel], e) for t, pose, e in self.keys if channel in pose]
            out = np.tile(np.asarray(default, dtype=float), (frames, 1))
            if not keyed:
                return out
            # A channel written only in the middle keys must still start and
            # end at the pose's default, otherwise it is held constant for the
            # whole clip and the motion silently disappears.
            first_time = self.keys[0][0]
            last_time = self.keys[-1][0]
            if keyed[0][0] > first_time:
                keyed.insert(0, (first_time, default, keyed[0][2]))
            if keyed[-1][0] < last_time:
                keyed.append((last_time, default, "smooth"))
            for i, t in enumerate(times):
                if t <= keyed[0][0]:
                    out[i] = keyed[0][1]
                elif t >= keyed[-1][0]:
                    out[i] = keyed[-1][1]
                else:
                    for k in range(len(keyed) - 1):
                        t0, v0, _ = keyed[k]
                        t1, v1, easing = keyed[k + 1]
                        if t0 <= t <= t1:
                            a = ease((t - t0) / max(t1 - t0, 1e-6), easing)
                            out[i] = np.asarray(v0) + (np.asarray(v1) - np.asarray(v0)) * a
                            break
            return out

        rotations = {}
        for channel in sorted(channels):
            if channel in ("root_pos", "root_scale"):
                continue
            if channel not in joint_names:
                continue                       # pose mentions a bone this rig lacks
            values = track(channel, (0.0, 0.0, 0.0)) * DEG
            rotations[channel] = np.array([quat_from_euler(*row) for row in values])

        return (times, rotations,
                track("root_pos", (0.0, 0.0, 0.0)),
                track("root_scale", (1.0, 1.0, 1.0)))


# --------------------------------------------------------------------------
# Rest correction.
#
# The scans were captured in a T-pose (arms straight out) or, for the Mega
# Knights, with the arms already hanging. Every clip is layered on top of a
# per-character correction that brings the arms down to a natural carry, so
# the same clips read correctly on both kinds of model.


def arm_drop_base(drop_degrees, elbow=16.0):
    """Bring the arms down out of the scanned pose and slightly forward, so
    they hang beside the body instead of skimming through it."""
    base = {}
    sym(base, "Shoulder", forward=4, out=-drop_degrees * 0.34)
    sym(base, "UpperArm", forward=6, out=-drop_degrees * 0.66)
    sym(base, "Elbow", forward=elbow)
    return base


def rest(base=None, **root):
    pose = {k: tuple(v) for k, v in (base or {}).items()}
    pose.setdefault("root_pos", (0, 0, 0))
    pose.setdefault("root_scale", (1, 1, 1))
    pose.update(root)
    return pose


# --------------------------------------------------------------------------
# Biped clips. `reach` scales the arm swings: the Mega Knights are so wide
# that the same angles read twice as big on them.


def biped_idle(reach=1.0, base=None):
    clip = Clip("Idle")
    clip.key(0.0, rest(base))
    pose = rest(base, root_pos=(0, 0.014, 0))
    side(pose, "Spine", 2)
    side(pose, "Chest", 1.5)
    side(pose, "Head", -2)
    sym(pose, "Shoulder", out=-3 * reach)
    sym(pose, "UpperArm", forward=3, out=-4 * reach)
    clip.key(1.1, pose)
    clip.key(2.2, rest(base))
    return clip


def biped_walk(reach=1.0, stride=30.0, base=None):
    clip = Clip("Walk")

    def pose(phase, lift):
        p = rest(base, root_pos=(0, lift, 0))
        swing = stride * phase
        side(p, "Hips", twist=3 * phase)
        side(p, "Spine", 4, -2 * phase)
        side(p, "Head", -3, 2 * phase)
        side(p, "Thigh.R", swing)
        side(p, "Thigh.L", -swing)
        side(p, "Shin.R", -max(0.0, swing) * 0.8)
        side(p, "Shin.L", -max(0.0, -swing) * 0.8)
        side(p, "UpperArm.R", -swing * 0.55, 0, -6 * reach)
        side(p, "UpperArm.L", swing * 0.55, 0, 6 * reach)
        return p

    clip.key(0.00, pose(1, 0.0))
    clip.key(0.20, pose(0.3, 0.03))
    clip.key(0.40, pose(-1, 0.0))
    clip.key(0.60, pose(-0.3, 0.03))
    clip.key(0.80, pose(1, 0.0))
    return clip


def biped_attack(reach=1.0, base=None):
    """Right-arm swing: wind up across the body, then drive through."""
    clip = Clip("Attack", loop=False)
    clip.key(0.00, rest(base))

    wind = rest(base, root_pos=(0, -0.02, 0))
    side(wind, "Hips", twist=12)
    side(wind, "Spine", -4, 9)
    side(wind, "Chest", -4, 10)
    side(wind, "Head", 2, -8)
    side(wind, "Shoulder.R", -16, 0, 12 * reach)
    side(wind, "UpperArm.R", -34, 0, 26 * reach)
    side(wind, "Elbow.R", -30)
    side(wind, "Shoulder.L", 8, 0, -4 * reach)
    side(wind, "UpperArm.L", 16, 0, -8 * reach)
    clip.key(0.26, wind, "in")

    hit = rest(base, root_scale=(1.02, 0.98, 1.03))
    side(hit, "Hips", twist=-16)
    side(hit, "Spine", 7, -11)
    side(hit, "Chest", 8, -12)
    side(hit, "Head", -4, 8)
    side(hit, "Shoulder.R", 26, 0, -6 * reach)
    side(hit, "UpperArm.R", 62, 0, -12 * reach)
    side(hit, "Elbow.R", 18)
    side(hit, "Shoulder.L", -8, 0, 4 * reach)
    side(hit, "UpperArm.L", -16, 0, 8 * reach)
    clip.key(0.40, hit, "snap")

    follow = rest(base)
    side(follow, "Hips", twist=-8)
    side(follow, "Chest", 4, -6)
    side(follow, "Shoulder.R", 14, 0, -3 * reach)
    side(follow, "UpperArm.R", 34, 0, -6 * reach)
    side(follow, "Elbow.R", 10)
    clip.key(0.60, follow, "out")
    clip.key(0.95, rest(base), "smooth")
    return clip


def biped_shoot(reach=1.0, base=None):
    """Draw a bow and loose it. The left arm holds the bow out front."""
    clip = Clip("Shoot", loop=False)
    clip.key(0.00, rest(base))

    def aiming(draw):
        p = rest(base)
        side(p, "Spine", -2, -8)
        side(p, "Chest", -2, -10)
        side(p, "Head", 0, 8)
        side(p, "Shoulder.L", -34, 0, -6 * reach)
        side(p, "UpperArm.L", -54, 0, -8 * reach)
        side(p, "Elbow.L", -6)
        side(p, "Shoulder.R", -20, 0, 8 * reach)
        side(p, "UpperArm.R", -30, 0, 14 * reach)
        side(p, "Elbow.R", -draw)
        return p

    clip.key(0.32, aiming(70), "out")
    clip.key(0.50, aiming(92), "in")

    loose = aiming(34)
    side(loose, "UpperArm.R", 0, 0, 8 * reach)
    loose["root_scale"] = (1.01, 0.99, 1.02)
    clip.key(0.58, loose, "snap")

    clip.key(0.98, rest(base), "smooth")
    return clip


def biped_hit(reach=1.0, base=None):
    clip = Clip("Hit", loop=False)
    clip.key(0.00, rest(base))
    flinch = rest(base, root_pos=(0, 0.02, 0))
    side(flinch, "Hips", -12)
    side(flinch, "Spine", -14)
    side(flinch, "Chest", -11)
    side(flinch, "Head", -20)
    sym(flinch, "UpperArm", forward=14, out=12 * reach)
    clip.key(0.10, flinch, "snap")

    settle = rest(base)
    side(settle, "Spine", -5)
    side(settle, "Head", -7)
    sym(settle, "UpperArm", forward=5, out=4 * reach)
    clip.key(0.34, settle, "out")
    clip.key(0.62, rest(base), "smooth")
    return clip


def biped_die(reach=1.0, base=None):
    """Stagger, drop to the knees and slump. The view fades the body out, so
    the clip never drives it through the floor -- sinking is what made the
    legs vanish while the body still showed."""
    clip = Clip("Die", loop=False)
    clip.key(0.00, rest(base))

    stagger = rest(base, root_pos=(0, -0.04, 0))
    side(stagger, "Spine", -14)
    side(stagger, "Chest", -10)
    side(stagger, "Head", -18)
    sym(stagger, "UpperArm", forward=-10, out=20 * reach)
    sym(stagger, "Thigh", forward=8)
    clip.key(0.22, stagger, "out")

    kneel = rest(base, root_pos=(0, -0.16, 0), root_scale=(1.03, 0.94, 1.03))
    side(kneel, "Hips", 26)
    side(kneel, "Spine", 20)
    side(kneel, "Chest", 14)
    side(kneel, "Head", 22)
    sym(kneel, "UpperArm", forward=18, out=16 * reach)
    sym(kneel, "Thigh", forward=-46)
    sym(kneel, "Shin", forward=64)
    clip.key(0.60, kneel, "in")

    slump = rest(base, root_pos=(0, -0.24, 0), root_scale=(1.05, 0.90, 1.05))
    side(slump, "Hips", 36)
    side(slump, "Spine", 30)
    side(slump, "Chest", 20)
    side(slump, "Head", 30)
    sym(slump, "UpperArm", forward=26, out=10 * reach)
    sym(slump, "Thigh", forward=-52)
    sym(slump, "Shin", forward=70)
    clip.key(1.10, slump, "out")
    return clip


def mega_jump(height=1.5, base=None):
    """Crouch, launch, tuck, land fists first. Vertical motion only."""
    clip = Clip("Jump", loop=False)
    clip.key(0.00, rest(base))

    crouch = rest(base, root_pos=(0, -0.13, 0), root_scale=(1.06, 0.90, 1.06))
    side(crouch, "Hips", 6)
    side(crouch, "Spine", 7)
    side(crouch, "Head", -5)
    sym(crouch, "Thigh", forward=-22)
    sym(crouch, "Shin", forward=30)
    sym(crouch, "UpperArm", forward=26, out=4)
    clip.key(0.30, crouch, "in")

    launch = rest(base, root_pos=(0, height * 0.45, 0), root_scale=(0.92, 1.12, 0.92))
    side(launch, "Spine", -6)
    side(launch, "Head", -7)
    sym(launch, "Thigh", forward=8)
    sym(launch, "UpperArm", forward=-16, out=28)
    clip.key(0.48, launch, "snap")

    apex = rest(base, root_pos=(0, height, 0), root_scale=(0.96, 1.05, 0.96))
    side(apex, "Hips", 5)
    side(apex, "Chest", -6)
    sym(apex, "Thigh", forward=-32)
    sym(apex, "Shin", forward=42)
    sym(apex, "UpperArm", forward=-22, out=34)
    sym(apex, "Hand", out=12)
    clip.key(0.84, apex, "out")

    fall = rest(base, root_pos=(0, height * 0.40, 0), root_scale=(0.94, 1.09, 0.94))
    sym(fall, "Thigh", forward=-10)
    sym(fall, "Shin", forward=12)
    sym(fall, "UpperArm", forward=-18, out=30)
    clip.key(1.14, fall, "in")

    impact = rest(base, root_pos=(0, -0.15, 0), root_scale=(1.12, 0.86, 1.12))
    side(impact, "Hips", 8)
    side(impact, "Spine", 9)
    side(impact, "Chest", 8)
    side(impact, "Head", 5)
    sym(impact, "Thigh", forward=-32, out=-8)
    sym(impact, "Shin", forward=42)
    sym(impact, "UpperArm", forward=-26, out=-18)
    sym(impact, "Hand", forward=-10, out=-8)
    clip.key(1.28, impact, "snap")

    recover = rest(base, root_pos=(0, -0.05, 0), root_scale=(1.05, 0.96, 1.05))
    side(recover, "Hips", 4)
    sym(recover, "Thigh", forward=-13, out=-3)
    sym(recover, "Shin", forward=17)
    sym(recover, "UpperArm", forward=-10, out=-7)
    clip.key(1.52, recover, "out")

    clip.key(1.90, rest(base), "smooth")
    return clip


def mega_smash(base=None):
    """Both fists overhead, then straight down into the ground."""
    clip = Clip("Smash", loop=False)
    clip.key(0.00, rest(base))

    load = rest(base, root_pos=(0, 0.05, 0), root_scale=(0.97, 1.05, 0.97))
    side(load, "Spine", -6)
    side(load, "Chest", -6)
    side(load, "Head", -7)
    sym(load, "Shoulder", forward=-8, out=18)
    sym(load, "UpperArm", forward=-18, out=34)
    sym(load, "Hand", out=12)
    clip.key(0.34, load, "in")

    slam = rest(base, root_pos=(0, -0.09, 0), root_scale=(1.09, 0.89, 1.09))
    side(slam, "Hips", 7)
    side(slam, "Spine", 8)
    side(slam, "Chest", 8)
    sym(slam, "Shoulder", forward=-10, out=-8)
    sym(slam, "UpperArm", forward=-22, out=-16)
    sym(slam, "Hand", forward=-12, out=-6)
    sym(slam, "Thigh", forward=-14)
    sym(slam, "Shin", forward=18)
    clip.key(0.50, slam, "snap")

    settle = rest(base, root_scale=(1.03, 0.97, 1.03))
    side(settle, "Spine", 3)
    sym(settle, "UpperArm", forward=-9, out=-6)
    sym(settle, "Thigh", forward=-6)
    sym(settle, "Shin", forward=7)
    clip.key(0.72, settle, "out")
    clip.key(1.12, rest(base), "smooth")
    return clip


# --------------------------------------------------------------------------
# Dragon


def dragon_flap(name="Idle", period=0.9, amplitude=1.0, forward=0.0, base=None):
    clip = Clip(name)

    def pose(up, bob):
        p = rest(base, root_pos=(0, bob, 0))
        side(p, "Spine", forward * 6)
        side(p, "Chest", forward * 4)
        side(p, "Neck", -forward * 5)
        sym(p, "Wing", forward=-6 * up * amplitude, out=34 * up * amplitude)
        sym(p, "WingTip", out=26 * up * amplitude)
        side(p, "Tail", -8 * up)
        side(p, "TailTip", -10 * up)
        sym(p, "Thigh", forward=8 + 6 * up)
        return p

    clip.key(0.0, pose(1, 0.05))
    clip.key(period * 0.5, pose(-1, -0.03), "smooth")
    clip.key(period, pose(1, 0.05), "smooth")
    return clip


def dragon_breath(base=None):
    clip = Clip("Shoot", loop=False)
    clip.key(0.00, rest(base))

    rear = rest(base, root_pos=(0, 0.07, 0))
    side(rear, "Neck", -26)
    side(rear, "Head", -18)
    side(rear, "Chest", -8)
    sym(rear, "Wing", forward=-10, out=30)
    clip.key(0.26, rear, "in")

    blast = rest(base, root_pos=(0, -0.02, 0), root_scale=(1.04, 0.97, 1.04))
    side(blast, "Neck", 22)
    side(blast, "Head", 16)
    side(blast, "Chest", 6)
    sym(blast, "Wing", forward=8, out=-12)
    clip.key(0.38, blast, "snap")
    clip.key(0.70, rest(base), "out")
    return clip


def dragon_hit(base=None):
    clip = Clip("Hit", loop=False)
    clip.key(0.00, rest(base))
    flinch = rest(base, root_pos=(0, -0.05, 0))
    side(flinch, "Chest", -16)
    side(flinch, "Neck", -20)
    side(flinch, "Head", -14)
    sym(flinch, "Wing", out=-18)
    clip.key(0.10, flinch, "snap")
    clip.key(0.50, rest(base), "out")
    return clip


def dragon_die(base=None):
    """Wings fold, the dragon drops to the ground and goes limp."""
    clip = Clip("Die", loop=False)
    clip.key(0.00, rest(base))

    falter = rest(base, root_pos=(0, 0.05, 0))
    side(falter, "Chest", -14)
    side(falter, "Neck", -22)
    side(falter, "Head", -18)
    sym(falter, "Wing", out=-10)
    clip.key(0.24, falter, "out")

    limp = rest(base, root_pos=(0, -0.30, 0), root_scale=(1.06, 0.88, 1.06))
    side(limp, "Chest", 16)
    side(limp, "Neck", 24)
    side(limp, "Head", 20)
    sym(limp, "Wing", forward=8, out=-30)
    sym(limp, "WingTip", out=-26)
    side(limp, "Tail", 14)
    sym(limp, "Thigh", forward=-20)
    clip.key(1.00, limp, "in")
    return clip


# --------------------------------------------------------------------------
# Mounted rider


def rider_idle(base=None):
    clip = Clip("Idle")
    clip.key(0.0, rest(base))
    breathe = rest(base, root_pos=(0, 0.02, 0))
    side(breathe, "Mount", 2)
    side(breathe, "MountHead", -4)
    side(breathe, "Spine", -2)
    sym(breathe, "UpperArm", forward=4, out=-4)
    clip.key(0.85, breathe)
    clip.key(1.7, rest(base))
    return clip


def rider_gallop(base=None):
    clip = Clip("Walk")

    def pose(phase, lift, pitch):
        p = rest(base, root_pos=(0, lift, 0))
        side(p, "Mount", pitch)
        side(p, "MountHead", -pitch * 1.4)
        side(p, "MountTail", -pitch * 0.8)
        side(p, "Spine", pitch * 0.5)
        side(p, "Chest", -pitch * 0.3)
        side(p, "Head", -pitch * 0.4)
        for tag, s in (("F", 1.0), ("B", -1.0)):
            side(p, f"Hoof{tag}.R", 34 * phase * s)
            side(p, f"Hoof{tag}.L", -34 * phase * s)
        sym(p, "UpperArm", forward=6 * phase, out=-6)
        return p

    clip.key(0.00, pose(1, 0.00, 8))
    clip.key(0.16, pose(0, 0.09, -6))
    clip.key(0.32, pose(-1, 0.00, 8))
    clip.key(0.48, pose(0, 0.09, -6))
    clip.key(0.64, pose(1, 0.00, 8))
    return clip


def rider_attack(base=None):
    """Hammer swing from over the shoulder."""
    clip = Clip("Attack", loop=False)
    clip.key(0.00, rest(base))

    wind = rest(base)
    side(wind, "Chest", -8, 12)
    side(wind, "Head", 0, -8)
    side(wind, "Shoulder.R", -30, 0, 22)
    side(wind, "UpperArm.R", -56, 0, 34)
    side(wind, "Mount", -4)
    clip.key(0.28, wind, "in")

    hit = rest(base, root_scale=(1.02, 0.98, 1.02))
    side(hit, "Chest", 12, -14)
    side(hit, "Head", 4, 9)
    side(hit, "Shoulder.R", 34, 0, -8)
    side(hit, "UpperArm.R", 72, 0, -16)
    side(hit, "Mount", 7)
    clip.key(0.42, hit, "snap")

    follow = rest(base)
    side(follow, "Chest", 5, -6)
    side(follow, "Shoulder.R", 15)
    side(follow, "UpperArm.R", 32)
    side(follow, "Mount", 3)
    clip.key(0.64, follow, "out")
    clip.key(1.00, rest(base), "smooth")
    return clip


def rider_hit(base=None):
    clip = Clip("Hit", loop=False)
    clip.key(0.00, rest(base))
    flinch = rest(base)
    side(flinch, "Spine", -16)
    side(flinch, "Chest", -12)
    side(flinch, "Head", -20)
    side(flinch, "Mount", -8)
    side(flinch, "MountHead", 10)
    clip.key(0.10, flinch, "snap")
    clip.key(0.55, rest(base), "out")
    return clip


def rider_die(base=None):
    """The mount stumbles and drops; the rider slumps over its neck."""
    clip = Clip("Die", loop=False)
    clip.key(0.00, rest(base))

    stumble = rest(base, root_pos=(0, -0.08, 0))
    side(stumble, "Mount", 14)
    side(stumble, "MountHead", -18)
    side(stumble, "Spine", -12)
    side(stumble, "Head", -14)
    clip.key(0.26, stumble, "out")

    down = rest(base, root_pos=(0, -0.22, 0), root_scale=(1.05, 0.88, 1.05))
    side(down, "Mount", 22)
    side(down, "MountHead", -26)
    side(down, "MountTail", 16)
    sym(down, "HoofF", forward=-40)
    sym(down, "HoofB", forward=34)
    side(down, "Spine", 26)
    side(down, "Chest", 20)
    side(down, "Head", 24)
    sym(down, "UpperArm", forward=22, out=12)
    clip.key(0.95, down, "in")
    return clip


# --------------------------------------------------------------------------


def clip_set(archetype, reach=1.0, base=None, jump_height=1.5):
    """Clip factories for one character, already bound to its rest correction."""
    if archetype in ("biped", "mega"):
        clips = {
            "idle": lambda: biped_idle(reach, base),
            "walk": lambda: biped_walk(reach, 26.0 if archetype == "mega" else 30.0, base),
            "attack": lambda: biped_attack(reach, base),
            "shoot": lambda: biped_shoot(reach, base),
            "hit": lambda: biped_hit(reach, base),
            "die": lambda: biped_die(reach, base),
        }
        # Jump and Smash are ordinary biped clips, so any two-legged rig can
        # use them -- the Trump Mega Knight was scanned in a T-pose and needs
        # the plain biped skeleton while keeping the Mega Knight moveset.
        clips["jump"] = lambda: mega_jump(jump_height, base)
        clips["smash"] = lambda: mega_smash(base)
        return clips
    if archetype == "dragon":
        return {
            "idle": lambda: dragon_flap("Idle", 0.9, 1.0, 0.0, base),
            "walk": lambda: dragon_flap("Walk", 0.62, 1.25, 1.0, base),
            "shoot": lambda: dragon_breath(base),
            "hit": lambda: dragon_hit(base),
            "die": lambda: dragon_die(base),
        }
    if archetype == "rider":
        return {
            "idle": lambda: rider_idle(base),
            "walk": lambda: rider_gallop(base),
            "attack": lambda: rider_attack(base),
            "hit": lambda: rider_hit(base),
            "die": lambda: rider_die(base),
        }
    raise KeyError(archetype)
