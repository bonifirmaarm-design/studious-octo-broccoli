"""Skeleton layouts, fitted to each scan's own measurements.

Three body plans cover the whole roster:

* ``biped``  - everything that stands on two legs, whether it was scanned in a
  T-pose (archers, kings, barbarian, skeleton) or with its arms down and fists
  forward (the Mega Knights). The arm chain is laid along the straight line
  from the measured shoulder to the measured hand, so both poses work.
* ``dragon`` - winged body with a tail.
* ``rider``  - a mount carrying a rider whose upper body is animated.
"""

import numpy as np

from measure import measure

EXCLUSIVE = {
    "L": ["Shoulder.L", "UpperArm.L", "Hand.L", "Thigh.L", "Shin.L", "Foot.L",
          "Wing.L", "WingTip.L"],
    "R": ["Shoulder.R", "UpperArm.R", "Hand.R", "Thigh.R", "Shin.R", "Foot.R",
          "Wing.R", "WingTip.R"],
}


def _lerp(a, b, t):
    return a + (b - a) * t


def biped(positions, arms_low=False):
    lm = measure(positions, arms_low=arms_low)
    crotch = lm["crotch"]
    shoulder_y = lm["shoulder_y"]
    shoulder_x = max(lm["shoulder_x"], 0.04)
    neck_y = lm["neck_y"]

    hand = np.array([lm["arm_span"] * 0.90, lm["hand_y"], 0.02])
    shoulder = np.array([shoulder_x, shoulder_y, 0.0])
    elbow = _lerp(shoulder, hand, 0.5)
    upper = _lerp(shoulder, hand, 0.16)

    hip_x = lm["foot_x"] * 0.62
    foot_x = lm["foot_x"]
    knee = np.array([_lerp(hip_x, foot_x, 0.5), crotch * 0.5, 0.0])

    def mirror(point, sign):
        return [sign * point[0], point[1], point[2]]

    joints = [
        ("Root", None, [0.0, 0.0, 0.0]),
        ("Hips", "Root", [0.0, crotch, 0.0]),
        ("Spine", "Hips", [0.0, _lerp(crotch, shoulder_y, 0.42), 0.0]),
        ("Chest", "Spine", [0.0, _lerp(crotch, shoulder_y, 0.86), 0.0]),
        ("Neck", "Chest", [0.0, neck_y, 0.0]),
        ("Head", "Neck", [0.0, _lerp(neck_y, lm["head_top"], 0.55), 0.0]),
    ]
    for side, sign in (("L", -1.0), ("R", 1.0)):
        joints += [
            (f"Shoulder.{side}", "Chest", mirror(shoulder, sign)),
            (f"UpperArm.{side}", f"Shoulder.{side}", mirror(upper, sign)),
            (f"Elbow.{side}", f"UpperArm.{side}", mirror(elbow, sign)),
            (f"Hand.{side}", f"Elbow.{side}", mirror(hand, sign)),
        ]
    for side, sign in (("L", -1.0), ("R", 1.0)):
        joints += [
            (f"Thigh.{side}", "Hips", [sign * hip_x, crotch, 0.0]),
            (f"Shin.{side}", f"Thigh.{side}", mirror(knee, sign)),
            (f"Foot.{side}", f"Shin.{side}", [sign * foot_x, 0.035, lm["foot_z"] + 0.02]),
        ]
    return joints, lm


def dragon(positions):
    """Winged body: spine along Z, wings out to the sides, tail behind."""
    z_min, z_max = positions[:, 2].min(), positions[:, 2].max()
    height = positions[:, 1].max()
    span = np.abs(positions[:, 0]).max()

    # Every scan in this set was captured facing +Z, so the head is at z_max.
    # Sniffing for it from the silhouette got the hog rider's mount backwards.
    sign = 1.0
    back = z_min

    body_y = 0.44 * height
    chest_z = sign * 0.10 * abs(z_max - z_min)
    wing_y = 0.72 * height

    joints = [
        ("Root", None, [0.0, 0.0, 0.0]),
        ("Hips", "Root", [0.0, body_y, -sign * 0.06 * abs(z_max - z_min)]),
        ("Spine", "Hips", [0.0, body_y + 0.06 * height, chest_z * 0.4]),
        ("Chest", "Spine", [0.0, body_y + 0.14 * height, chest_z]),
        ("Neck", "Chest", [0.0, 0.72 * height, chest_z + sign * 0.10 * abs(z_max - z_min)]),
        ("Head", "Neck", [0.0, 0.82 * height, chest_z + sign * 0.22 * abs(z_max - z_min)]),
        ("Tail", "Hips", [0.0, body_y * 0.9, back * 0.45]),
        ("TailTip", "Tail", [0.0, body_y * 0.7, back * 0.9]),
    ]
    for side, s in (("L", -1.0), ("R", 1.0)):
        joints += [
            (f"Wing.{side}", "Chest", [s * 0.16 * span, wing_y, chest_z * 0.5]),
            (f"WingTip.{side}", f"Wing.{side}", [s * 0.95 * span, wing_y + 0.10 * height,
                                                 chest_z * 0.2]),
        ]
    for side, s in (("L", -1.0), ("R", 1.0)):
        joints += [
            (f"Thigh.{side}", "Hips", [s * 0.22 * span, body_y * 0.75, -sign * 0.02]),
            (f"Foot.{side}", f"Thigh.{side}", [s * 0.28 * span, 0.04, sign * 0.04]),
        ]
    return joints, {"height": 1.0, "span": float(span)}


def _mass_above(positions, z_value, y_threshold):
    near = np.abs(positions[:, 2] - z_value) < 0.12
    return float((positions[near, 1] > y_threshold).sum())


def rider(positions):
    """A mount plus a rider: the mount bobs, the rider's arms swing."""
    height = positions[:, 1].max()
    z_min, z_max = positions[:, 2].min(), positions[:, 2].max()
    depth = z_max - z_min
    span = np.abs(positions[:, 0]).max()

    # The mount is the lower half, the rider the upper half.
    saddle_y = 0.46 * height
    widths, edges = _profile_pair(positions)
    arm_band = int(np.argmax(widths[len(widths) // 2:])) + len(widths) // 2
    arm_y = float((edges[arm_band] + edges[arm_band + 1]) / 2)
    arm_span = float(widths[arm_band])

    # As above: the mount faces +Z like every other scan here.
    sign = 1.0

    # Hips is listed FIRST among Mount's children on purpose: a joint's rest
    # orientation aims along its first child, and pointing Mount at MountHead
    # put the bone almost parallel to the frame's reference axis, which throws
    # the whole mount into a degenerate roll -- the pig ended up on its back.
    # Aiming Mount straight up at the saddle keeps the frame well conditioned.
    joints = [
        ("Root", None, [0.0, 0.0, 0.0]),
        ("Mount", "Root", [0.0, 0.30 * height, 0.0]),
        ("Hips", "Mount", [0.0, saddle_y, -sign * 0.03 * depth]),
        ("MountHead", "Mount", [0.0, 0.34 * height, sign * 0.34 * depth]),
        ("MountTail", "Mount", [0.0, 0.32 * height, -sign * 0.34 * depth]),
        ("Spine", "Hips", [0.0, saddle_y + 0.09 * height, 0.0]),
        ("Chest", "Spine", [0.0, saddle_y + 0.20 * height, 0.0]),
        ("Head", "Chest", [0.0, 0.90 * height, 0.0]),
    ]
    shoulder = np.array([0.30 * arm_span, arm_y, 0.0])
    hand = np.array([0.92 * arm_span, arm_y, 0.03])
    for side, s in (("L", -1.0), ("R", 1.0)):
        joints += [
            (f"Shoulder.{side}", "Chest", [s * shoulder[0], shoulder[1], shoulder[2]]),
            (f"UpperArm.{side}", f"Shoulder.{side}",
             [s * _lerp(shoulder[0], hand[0], 0.3), _lerp(shoulder[1], hand[1], 0.3), 0.01]),
            (f"Hand.{side}", f"UpperArm.{side}", [s * hand[0], hand[1], hand[2]]),
        ]
    for side, s in (("L", -1.0), ("R", 1.0)):
        for tag, z in (("F", sign * 0.24 * depth), ("B", -sign * 0.24 * depth)):
            joints.append((f"Hoof{tag}.{side}", "Mount", [s * 0.42 * span, 0.06 * height, z]))
    return joints, {"height": 1.0, "arm_y": arm_y, "span": float(span)}


def _mass_below(positions, z_value, y_threshold):
    near = np.abs(positions[:, 2] - z_value) < 0.12
    return float((positions[near, 1] < y_threshold).sum())


def _profile_pair(positions, bands=24):
    height = positions[:, 1].max()
    edges = np.linspace(0, height, bands + 1)
    widths = np.zeros(bands)
    for i in range(bands):
        sel = (positions[:, 1] >= edges[i]) & (positions[:, 1] < edges[i + 1])
        widths[i] = np.abs(positions[sel, 0]).max() if sel.sum() > 3 else 0.0
    return widths, edges


BUILDERS = {
    "biped": lambda p: biped(p, arms_low=False),
    "mega": lambda p: biped(p, arms_low=True),
    "dragon": dragon,
    "rider": rider,
}
