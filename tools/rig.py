"""Build a skeleton for a Mega Knight scan and skin the mesh to it.

The scans have no bones, so the rig is generated: joints are placed from
proportions measured off the mesh, then every vertex is bound to the bones by
nearest-segment distance followed by diffusion smoothing across the mesh
surface, which is what keeps the shoulders and hips from creasing.
"""

from collections import defaultdict

import numpy as np

# Skeleton definition. Positions are fractions of the character's height,
# measured from the silhouette profile of both scans (they share proportions).
#   name: (parent, x, y, z)
# +Z is the direction the knight faces. The .L/.R suffixes are screen sides as
# seen head-on in the default front view: .R is +X, .L is -X. (Head-on that is
# the knight's own left and right the other way round -- the labels are the
# viewer's, and every clip in anim.py is written against them.)
SKELETON = [
    ("Root",        None,        0.00, 0.00, 0.00),
    ("Hips",        "Root",      0.00, 0.32, 0.00),
    ("Spine",       "Hips",      0.00, 0.44, 0.00),
    ("Chest",       "Spine",     0.00, 0.55, 0.00),
    ("Neck",        "Chest",     0.00, 0.62, 0.00),
    ("Head",        "Neck",      0.00, 0.68, -0.01),
    ("Shoulder.L", "Chest",     -0.17, 0.575, 0.00),
    ("UpperArm.L", "Shoulder.L", -0.28, 0.45, 0.03),
    ("Fist.L",     "UpperArm.L", -0.43, 0.26, 0.06),
    ("Shoulder.R", "Chest",      0.17, 0.575, 0.00),
    ("UpperArm.R", "Shoulder.R", 0.28, 0.45, 0.03),
    ("Fist.R",     "UpperArm.R", 0.43, 0.26, 0.06),
    ("Thigh.L",    "Hips",      -0.10, 0.28, 0.00),
    ("Shin.L",     "Thigh.L",   -0.12, 0.14, 0.00),
    ("Foot.L",     "Shin.L",    -0.13, 0.03, 0.03),
    ("Thigh.R",    "Hips",       0.10, 0.28, 0.00),
    ("Shin.R",     "Thigh.R",    0.12, 0.14, 0.00),
    ("Foot.R",     "Shin.R",     0.13, 0.03, 0.03),
]

# Bones that must not steal weight from each other, whatever the distance says.
# Without this the two fists -- which nearly touch the opposite hip -- bleed
# across the body.
EXCLUSIVE_SIDES = {"L": ["Shoulder.L", "UpperArm.L", "Fist.L", "Thigh.L", "Shin.L", "Foot.L"],
                   "R": ["Shoulder.R", "UpperArm.R", "Fist.R", "Thigh.R", "Shin.R", "Foot.R"]}


class Skeleton:
    def __init__(self, spec=SKELETON, height=1.0, mirror_z=1.0):
        self.names = [row[0] for row in spec]
        self.index = {name: i for i, name in enumerate(self.names)}
        self.parents = [(-1 if row[1] is None else self.index[row[1]]) for row in spec]
        self.rest = np.array([[row[2], row[3], row[4] * mirror_z] for row in spec]) * height
        self.children = defaultdict(list)
        for i, p in enumerate(self.parents):
            if p >= 0:
                self.children[p].append(i)

    @property
    def count(self):
        return len(self.names)

    def local_rest(self):
        """Each joint's offset from its parent (the bind-pose translation)."""
        local = self.rest.copy()
        for i, p in enumerate(self.parents):
            if p >= 0:
                local[i] = self.rest[i] - self.rest[p]
        return local

    def bone_segments(self):
        """(start, end) world-space points per joint; leaves get a stub.

        A joint's bone runs to its *first* child, not to the average of them:
        averaging would shrink Hips and Chest down to stubs (their children
        fan out sideways into the legs and arms) and the thighs would then
        capture the whole lower torso.
        """
        segments = []
        for i in range(self.count):
            kids = self.children[i]
            if kids:
                end = self.rest[kids[0]]
            elif self.parents[i] >= 0:
                end = self.rest[i] + (self.rest[i] - self.rest[self.parents[i]]) * 0.45
            else:
                end = self.rest[i] + np.array([0, 0.05, 0])
            segments.append((self.rest[i], end))
        return segments


def _segment_distance(points, a, b):
    ab = b - a
    length_sq = float(ab @ ab)
    if length_sq < 1e-12:
        return np.linalg.norm(points - a, axis=1)
    t = np.clip((points - a) @ ab / length_sq, 0.0, 1.0)
    closest = a + t[:, None] * ab
    return np.linalg.norm(points - closest, axis=1)


def build_adjacency(vertex_count, indices):
    """Neighbour lists as a padded index array, for vectorised smoothing."""
    tris = indices.reshape(-1, 3)
    pairs = np.vstack([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    pairs = np.vstack([pairs, pairs[:, ::-1]])
    order = np.argsort(pairs[:, 0], kind="stable")
    pairs = pairs[order]
    starts = np.searchsorted(pairs[:, 0], np.arange(vertex_count))
    ends = np.searchsorted(pairs[:, 0], np.arange(vertex_count), side="right")
    return pairs[:, 1], starts, ends


def smooth_weights(weights, neighbours, starts, ends, anchors=None,
                   iterations=140, blend=0.7):
    """Diffuse the weights over the surface so joints bend instead of shearing.

    Vertices flagged in `anchors` are pinned to their initial weights every
    iteration. Without those Dirichlet boundaries free diffusion converges to a
    uniform blend and every bone ends up dragging the whole body.
    """
    counts = (ends - starts).astype(np.float64)
    counts[counts == 0] = 1.0
    empty = ends <= starts
    pinned = weights[anchors].copy() if anchors is not None else None
    for _ in range(iterations):
        summed = np.add.reduceat(weights[neighbours], starts, axis=0)
        summed[empty] = weights[empty]
        averaged = summed / counts[:, None]
        weights = (1 - blend) * weights + blend * averaged
        if anchors is not None:
            weights[anchors] = pinned
        total = weights.sum(axis=1, keepdims=True)
        total[total == 0] = 1.0
        weights /= total
    return weights


def skin(positions, indices, skeleton, welded=None, max_influences=4, anchor_quantile=0.55):
    """Vertex -> (joint indices, weights), four influences per vertex.

    Each vertex starts bound wholly to its nearest bone. The half of each
    bone's vertices that sit closest to it are pinned, and the rest are
    relaxed by diffusion, so the blending happens only in the seams between
    body parts.
    """
    if welded is None:
        welded = np.arange(len(positions))
    unique_count = int(welded.max()) + 1

    # One representative position per welded vertex.
    unique_positions = np.zeros((unique_count, 3))
    np.add.at(unique_positions, welded, positions)
    counts = np.bincount(welded, minlength=unique_count).astype(np.float64)
    counts[counts == 0] = 1.0
    unique_positions /= counts[:, None]

    segments = skeleton.bone_segments()
    distances = np.stack([_segment_distance(unique_positions, a, b) for a, b in segments], axis=1)

    # Root is structural only; its children own the geometry.
    distances[:, skeleton.index["Root"]] = np.inf

    # A limb never claims geometry on the other side of the body: the fists
    # hang close enough to the opposite hip for plain distance to get it wrong.
    span = np.abs(unique_positions[:, 0]).max()
    for side, bones in EXCLUSIVE_SIDES.items():
        wrong_side = unique_positions[:, 0] > 0.12 * span if side == "L" \
            else unique_positions[:, 0] < -0.12 * span
        distances[np.ix_(wrong_side, [skeleton.index[b] for b in bones])] = np.inf

    best = distances.argmin(axis=1)
    weights = np.zeros((unique_count, skeleton.count))
    weights[np.arange(unique_count), best] = 1.0

    # Pin the vertices nearest each bone; relax everything else.
    best_distance = distances[np.arange(unique_count), best]
    anchors = np.zeros(unique_count, dtype=bool)
    for b in range(skeleton.count):
        owned = np.flatnonzero(best == b)
        if len(owned) < 8:
            anchors[owned] = True
            continue
        limit = np.quantile(best_distance[owned], anchor_quantile)
        anchors[owned[best_distance[owned] <= limit]] = True

    neighbours, starts, ends = build_adjacency(unique_count, welded[indices])
    weights = smooth_weights(weights, neighbours, starts, ends, anchors)
    weights = weights[welded]

    # Keep the strongest four influences.
    top = np.argsort(-weights, axis=1)[:, :max_influences]
    joints = top.astype(np.uint16)
    kept = np.take_along_axis(weights, top, axis=1)
    kept /= np.maximum(kept.sum(axis=1, keepdims=True), 1e-9)
    return joints, kept.astype(np.float32)


def inverse_bind_matrices(skeleton):
    matrices = np.tile(np.eye(4), (skeleton.count, 1, 1))
    matrices[:, :3, 3] = -skeleton.rest
    return matrices
