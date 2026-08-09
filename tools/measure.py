"""Measure a scanned character so a skeleton can be fitted to it.

Every uploaded model is a single un-rigged blob in a T- or A-pose. The numbers
here come from horizontal slices of the silhouette: where the arms stick out,
where the legs split, where the neck narrows.
"""

import numpy as np

from anatomy import slice_clusters


def profile(positions, bands=40):
    """Half-width of the silhouette in X for each horizontal band."""
    height = positions[:, 1].max()
    edges = np.linspace(0, height, bands + 1)
    out = np.zeros(bands)
    for i in range(bands):
        sel = (positions[:, 1] >= edges[i]) & (positions[:, 1] < edges[i + 1])
        out[i] = np.abs(positions[sel, 0]).max() if sel.sum() > 3 else 0.0
    return out, edges


def measure(positions, arms_low=False):
    """Landmarks in normalised space (feet at y=0, height 1, centred in XZ).

    `arms_low` switches to the Mega Knight reading, where the widest point is
    a pair of fists hanging by the hips rather than outstretched arms.
    """
    widths, edges = profile(positions)
    centres = (edges[:-1] + edges[1:]) / 2
    bands = len(widths)

    # --- arms ------------------------------------------------------------
    # Outstretched arms put the widest slice at shoulder height; the Mega
    # Knight instead carries its fists low, so look in a different window.
    window = slice(int(bands * 0.15), int(bands * 0.55)) if arms_low \
        else slice(int(bands * 0.45), int(bands * 0.92))
    local = widths[window]
    hand_band = window.start + int(np.argmax(local))
    hand_y = centres[hand_band]
    arm_span = widths[hand_band]

    # --- torso -----------------------------------------------------------
    # Sample the trunk below the arms, where nothing sticks out sideways.
    torso_band = max(1, int(bands * (0.30 if arms_low else 0.42)))
    torso_half = float(np.median(widths[max(0, torso_band - 3):torso_band + 3]))

    # --- shoulders -------------------------------------------------------
    # For a T-pose the shoulder sits at hand height; for arms-down poses the
    # shoulder is well above the fists.
    shoulder_y = hand_y if not arms_low else min(0.78, hand_y + 0.30)
    shoulder_x = min(torso_half * 0.85, arm_span * 0.42)

    # --- legs ------------------------------------------------------------
    crotch = None
    for i in range(min(bands // 2, int(bands * 0.55)), 0, -1):
        if len(slice_clusters(positions, edges[i], edges[i + 1])) >= 2:
            crotch = centres[i]
            break
    if crotch is None:
        crotch = 0.42 * (0.75 if not arms_low else 1.0)

    ankle = slice_clusters(positions, edges[0], edges[2])
    if len(ankle) >= 2:
        foot_x = float(np.mean([abs(ankle[0]["centre"][0]), abs(ankle[-1]["centre"][0])]))
        foot_z = float(np.mean([ankle[0]["centre"][2], ankle[-1]["centre"][2]]))
    else:
        foot_x, foot_z = max(0.06, torso_half * 0.45), 0.0

    # --- head ------------------------------------------------------------
    # Above the shoulders the body narrows into the neck and flares into the
    # head again; the narrowest band in that stretch is the neck.
    top_start = int(np.searchsorted(centres, shoulder_y + 0.02))
    upper = widths[top_start:]
    if len(upper) > 2:
        search = upper[:max(2, len(upper) // 2)]
        neck_y = centres[top_start + int(np.argmin(np.where(search > 0, search, 9)))]
    else:
        neck_y = shoulder_y + 0.05
    neck_y = float(np.clip(neck_y, shoulder_y + 0.01, 0.95))

    head_top = float(centres[max(np.flatnonzero(widths > 0.02), default=bands - 1)])

    return {
        "height": 1.0,
        "hand_y": float(hand_y),
        "arm_span": float(arm_span),
        "shoulder_y": float(shoulder_y),
        "shoulder_x": float(shoulder_x),
        "torso_half": torso_half,
        "crotch": float(crotch),
        "foot_x": float(foot_x),
        "foot_z": float(foot_z),
        "neck_y": neck_y,
        "head_top": head_top,
        "widths": widths,
    }


def describe(landmarks):
    keys = ("hand_y", "arm_span", "shoulder_y", "shoulder_x", "torso_half",
            "crotch", "foot_x", "neck_y", "head_top")
    return "  ".join(f"{k}={landmarks[k]:.3f}" for k in keys)
