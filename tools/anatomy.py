"""Turn a bare Mega Knight scan into landmarks a skeleton can be built from.

The scans are single watertight blobs with no parts or bones, so every joint
position is derived from the geometry itself: horizontal slices are clustered
along X, and the moment a slice breaks into three islands we know we are level
with the arms.
"""

import numpy as np


def cut_pedestal(positions, uvs, indices, drop_below=None):
    """Remove the display plinth the scan is standing on.

    The plinth is a thin square slab: in a bottom-up scan of horizontal slices
    it shows up as a couple of bins holding thousands of vertices and reaching
    a much larger XZ radius than the character ever does.
    """
    from objmesh import drop_vertices, largest_component

    y = positions[:, 1]
    radius = np.hypot(positions[:, 0], positions[:, 2])

    if drop_below is None:
        low, high = y.min(), y.min() + 0.25 * (y.max() - y.min())
        edges = np.linspace(low, high, 60)
        which = np.digitize(y, edges) - 1
        cut = low
        for b in range(len(edges) - 1):
            sel = which == b
            if sel.sum() < 200:
                continue
            if radius[sel].max() > 1.5 * np.percentile(radius[y > high], 99):
                cut = edges[b + 1]
        drop_below = cut

    keep = y > drop_below
    positions, uvs, indices, _ = drop_vertices(positions, uvs, indices, keep)
    positions, uvs, indices, _ = largest_component(positions, uvs, indices)
    return positions, uvs, indices, drop_below


def normalise(positions, height=1.0):
    """Feet on y = 0, centred on XZ, scaled so the character is `height` tall."""
    lo, hi = positions.min(0), positions.max(0)
    scale = height / (hi[1] - lo[1])
    centre = np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])
    return (positions - centre) * scale, scale


def _clusters_1d(values, gap):
    """Split sorted 1-D values wherever there is a gap wider than `gap`."""
    order = np.argsort(values)
    sorted_values = values[order]
    breaks = np.where(np.diff(sorted_values) > gap)[0]
    groups, start = [], 0
    for b in list(breaks) + [len(sorted_values) - 1]:
        groups.append(order[start:b + 1])
        start = b + 1
    return [g for g in groups if len(g) > 4]


def slice_clusters(positions, y0, y1, gap=0.02):
    sel = (positions[:, 1] >= y0) & (positions[:, 1] < y1)
    if sel.sum() < 8:
        return []
    idx = np.flatnonzero(sel)
    out = []
    for group in _clusters_1d(positions[idx, 0], gap):
        members = idx[group]
        out.append({
            "n": len(members),
            "centre": positions[members].mean(0),
            "xmin": positions[members, 0].min(),
            "xmax": positions[members, 0].max(),
            "members": members,
        })
    return sorted(out, key=lambda c: c["centre"][0])


def find_landmarks(positions, slices=80):
    """Locate the joints. Returns a dict of 3-D points in normalised space."""
    height = positions[:, 1].max()
    edges = np.linspace(0, height, slices + 1)

    # --- where do the arms hang free of the torso? -----------------------
    arm_rows = []
    for i in range(slices):
        clusters = slice_clusters(positions, edges[i], edges[i + 1])
        if len(clusters) >= 3:
            arm_rows.append((edges[i], clusters))

    if not arm_rows:
        raise RuntimeError("could not separate the arms from the torso")

    arm_y = np.array([row[0] for row in arm_rows])
    arm_top, arm_bottom = arm_y.max(), arm_y.min()

    # Fists: the outermost cluster of the widest slice.
    widest = max(arm_rows, key=lambda row: row[1][-1]["centre"][0] - row[1][0]["centre"][0])
    left_fist = widest[1][0]["centre"].copy()
    right_fist = widest[1][-1]["centre"].copy()

    # --- legs: below the pelvis a slice splits into two ------------------
    leg_rows = []
    for i in range(slices):
        if edges[i] > arm_bottom:
            break
        clusters = slice_clusters(positions, edges[i], edges[i + 1])
        if len(clusters) == 2:
            leg_rows.append((edges[i], clusters))

    if leg_rows:
        crotch = max(row[0] for row in leg_rows)
        ankle_row = leg_rows[0]
        left_foot = ankle_row[1][0]["centre"].copy()
        right_foot = ankle_row[1][1]["centre"].copy()
    else:
        crotch = 0.30 * height
        span = np.percentile(np.abs(positions[positions[:, 1] < 0.15 * height, 0]), 80)
        left_foot = np.array([-span / 2, 0.02 * height, 0.0])
        right_foot = np.array([span / 2, 0.02 * height, 0.0])

    # --- torso centreline ------------------------------------------------
    def torso_centre(y0, y1):
        clusters = slice_clusters(positions, y0, y1)
        if not clusters:
            sel = (positions[:, 1] >= y0) & (positions[:, 1] < y1)
            return positions[sel].mean(0) if sel.any() else np.zeros(3)
        # the torso is the cluster nearest x = 0
        return min(clusters, key=lambda c: abs(c["centre"][0]))["centre"].copy()

    hips = torso_centre(crotch, crotch + 0.05 * height)
    chest = torso_centre(arm_top - 0.06 * height, arm_top)

    # --- head: above the shoulders the silhouette narrows then flares ----
    head_slices = []
    for i in range(slices):
        if edges[i] < arm_top:
            continue
        sel = (positions[:, 1] >= edges[i]) & (positions[:, 1] < edges[i + 1])
        if sel.sum() > 6:
            head_slices.append((edges[i], np.abs(positions[sel, 0]).max(), positions[sel].mean(0)))
    if head_slices:
        widths = np.array([h[1] for h in head_slices])
        neck_i = int(np.argmin(widths[:max(2, len(widths) // 2)]))
        neck = head_slices[neck_i][2].copy()
        neck[0] = chest[0]
    else:
        neck = chest + np.array([0, 0.08 * height, 0])

    shoulder_y = arm_top - 0.02 * height
    shoulder_x = 0.55 * (abs(left_fist[0]) + abs(right_fist[0])) / 2

    landmarks = {
        "height": height,
        "hips": np.array([chest[0], crotch, chest[2]]),
        "chest": chest,
        "neck": neck,
        "head": np.array([neck[0], (neck[1] + height) / 2, neck[2]]),
        "shoulder.L": np.array([-shoulder_x * 0.55, shoulder_y, chest[2]]),
        "shoulder.R": np.array([shoulder_x * 0.55, shoulder_y, chest[2]]),
        "fist.L": left_fist,
        "fist.R": right_fist,
        "hip.L": np.array([left_foot[0] * 0.6, crotch, 0.0]),
        "hip.R": np.array([right_foot[0] * 0.6, crotch, 0.0]),
        "foot.L": np.array([left_foot[0], 0.02 * height, left_foot[2]]),
        "foot.R": np.array([right_foot[0], 0.02 * height, right_foot[2]]),
        "arm_top": arm_top,
        "arm_bottom": arm_bottom,
        "crotch": crotch,
    }
    for side in "LR":
        shoulder = landmarks[f"shoulder.{side}"]
        fist = landmarks[f"fist.{side}"]
        landmarks[f"elbow.{side}"] = shoulder + (fist - shoulder) * 0.5
        hip = landmarks[f"hip.{side}"]
        foot = landmarks[f"foot.{side}"]
        landmarks[f"knee.{side}"] = hip + (foot - hip) * 0.5
    return landmarks
