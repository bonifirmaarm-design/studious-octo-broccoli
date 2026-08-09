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
    # Walk UP from the feet while the silhouette still shows two legs
    # straddling the centre line; the crotch is where they merge. Scanning
    # downwards from mid-body instead put the Mega Knight's hips at 0.51 --
    # its fists split the slice far above the legs -- so walking drove the
    # whole torso.
    def leg_pair(y0, y1):
        clusters = slice_clusters(positions, y0, y1)
        if len(clusters) < 2:
            return None
        pair = sorted(clusters, key=lambda c: abs(c["centre"][0]))[:2]
        pair.sort(key=lambda c: c["centre"][0])
        left, right = pair[0]["centre"][0], pair[1]["centre"][0]
        if not (left < 0 < right):
            return None
        if abs(abs(left) - abs(right)) > 0.10:      # must straddle evenly
            return None
        if max(abs(left), abs(right)) > 0.35:       # legs hug the centre line
            return None
        return pair

    crotch, ankle_pair = None, None
    for i in range(1, int(bands * 0.55)):
        pair = leg_pair(edges[i], edges[i + 1])
        if pair:
            crotch = centres[i]
            if ankle_pair is None:
                ankle_pair = pair
        elif crotch is not None:
            break                                    # the legs have merged

    # These are all stylised humanoids with near-identical proportions (their
    # silhouette profiles overlap closely), so a reading outside a sane band is
    # the silhouette lying, not an unusual body: the Mega Knights' fists hang
    # past their knees and hide the legs completely, and the kings' robes reach
    # the floor so the split closes just above the boots.
    if arms_low or crotch is None:
        crotch = 0.26 if arms_low else 0.32
    else:
        crotch = float(np.clip(crotch, 0.22, 0.38))

    if ankle_pair:
        foot_x = float(np.mean([abs(c["centre"][0]) for c in ankle_pair]))
        foot_z = float(np.mean([c["centre"][2] for c in ankle_pair]))
    else:
        foot_x, foot_z = max(0.06, torso_half * 0.42), 0.0

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
