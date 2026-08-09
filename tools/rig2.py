"""Oriented skeletons fitted to measured scans, plus automatic skinning.

Unlike a plain position-only skeleton, every joint here carries a rest
orientation with the bone pointing along its own local +Y. That makes the
animation conventions identical for every character no matter what pose the
scan was in:

    * +X rotation swings the bone's tip forward (towards +Z, the facing side)
    * +Z rotation swings it sideways
    * +Y rotation twists it

Without this, an arm modelled straight out to the side and an arm modelled
hanging down need opposite signs for the same motion.
"""

from collections import defaultdict

import numpy as np

FORWARD = np.array([0.0, 0.0, 1.0])


# --------------------------------------------------------------------------
# quaternion helpers (x, y, z, w)


def quat_from_matrix(m):
    trace = m[0, 0] + m[1, 1] + m[2, 2]
    if trace > 0:
        s = 0.5 / np.sqrt(trace + 1.0)
        return np.array([(m[2, 1] - m[1, 2]) * s, (m[0, 2] - m[2, 0]) * s,
                         (m[1, 0] - m[0, 1]) * s, 0.25 / s])
    if m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = 2.0 * np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2])
        return np.array([0.25 * s, (m[0, 1] + m[1, 0]) / s,
                         (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s])
    if m[1, 1] > m[2, 2]:
        s = 2.0 * np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2])
        return np.array([(m[0, 1] + m[1, 0]) / s, 0.25 * s,
                         (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s])
    s = 2.0 * np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1])
    return np.array([(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s,
                     0.25 * s, (m[1, 0] - m[0, 1]) / s])


def matrix_from_quat(q):
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return np.array([
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    ])


def quat_conj(q):
    return np.array([-q[0], -q[1], -q[2], q[3]])


def aim_quat(direction, reference=FORWARD):
    """Rotation taking local +Y onto `direction`, rolled so local +Z ~ reference."""
    y_axis = np.asarray(direction, dtype=float)
    norm = np.linalg.norm(y_axis)
    if norm < 1e-9:
        y_axis = np.array([0.0, 1.0, 0.0])
    else:
        y_axis = y_axis / norm
    ref = np.asarray(reference, dtype=float)
    if abs(float(y_axis @ ref)) > 0.985:                    # bone parallel to the reference
        ref = np.array([0.0, 1.0, 0.0]) if abs(y_axis[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    x_axis = np.cross(y_axis, ref)
    x_axis /= np.linalg.norm(x_axis)
    z_axis = np.cross(x_axis, y_axis)
    return quat_from_matrix(np.stack([x_axis, y_axis, z_axis], axis=1))


# --------------------------------------------------------------------------


class Skeleton:
    """A joint hierarchy with world rest positions and orientations."""

    def __init__(self, joints):
        """joints: list of (name, parent_name|None, position)."""
        self.names = [j[0] for j in joints]
        self.index = {n: i for i, n in enumerate(self.names)}
        self.parents = [(-1 if j[1] is None else self.index[j[1]]) for j in joints]
        self.rest = np.array([j[2] for j in joints], dtype=float)

        self.children = defaultdict(list)
        for i, p in enumerate(self.parents):
            if p >= 0:
                self.children[p].append(i)

        self.rest_rot = np.zeros((self.count, 4))
        for i in range(self.count):
            self.rest_rot[i] = aim_quat(self._bone_vector(i))

    @property
    def count(self):
        return len(self.names)

    def _bone_vector(self, i):
        kids = self.children[i]
        if kids:
            vector = self.rest[kids[0]] - self.rest[i]
            if np.linalg.norm(vector) > 1e-6:
                return vector
        if self.parents[i] >= 0:
            vector = self.rest[i] - self.rest[self.parents[i]]
            if np.linalg.norm(vector) > 1e-6:
                return vector
        return np.array([0.0, 1.0, 0.0])

    def bone_length(self, i):
        kids = self.children[i]
        if kids:
            return float(np.linalg.norm(self.rest[kids[0]] - self.rest[i]))
        if self.parents[i] >= 0:
            return float(np.linalg.norm(self.rest[i] - self.rest[self.parents[i]])) * 0.5
        return 0.1

    def bone_segments(self):
        """(start, end) per joint, used for binding vertices."""
        out = []
        for i in range(self.count):
            direction = self._bone_vector(i)
            direction = direction / max(np.linalg.norm(direction), 1e-9)
            out.append((self.rest[i], self.rest[i] + direction * self.bone_length(i)))
        return out

    def local_transforms(self):
        """Per-joint (translation, rotation) relative to the parent."""
        translations = np.zeros((self.count, 3))
        rotations = np.zeros((self.count, 4))
        for i, p in enumerate(self.parents):
            if p < 0:
                translations[i] = self.rest[i]
                rotations[i] = self.rest_rot[i]
                continue
            inverse_parent = matrix_from_quat(quat_conj(self.rest_rot[p]))
            translations[i] = inverse_parent @ (self.rest[i] - self.rest[p])
            rotations[i] = quat_mul(quat_conj(self.rest_rot[p]), self.rest_rot[i])
        return translations, rotations

    def inverse_bind_matrices(self):
        out = np.zeros((self.count, 4, 4))
        for i in range(self.count):
            rotation = matrix_from_quat(self.rest_rot[i])
            world = np.eye(4)
            world[:3, :3] = rotation
            world[:3, 3] = self.rest[i]
            out[i] = np.linalg.inv(world)
        return out


# --------------------------------------------------------------------------
# skinning


def _segment_distance(points, a, b):
    ab = b - a
    length_sq = float(ab @ ab)
    if length_sq < 1e-12:
        return np.linalg.norm(points - a, axis=1)
    t = np.clip((points - a) @ ab / length_sq, 0.0, 1.0)
    return np.linalg.norm(points - (a + t[:, None] * ab), axis=1)


def build_adjacency(vertex_count, indices):
    tris = indices.reshape(-1, 3)
    pairs = np.vstack([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    pairs = np.vstack([pairs, pairs[:, ::-1]])
    pairs = pairs[np.argsort(pairs[:, 0], kind="stable")]
    starts = np.searchsorted(pairs[:, 0], np.arange(vertex_count))
    ends = np.searchsorted(pairs[:, 0], np.arange(vertex_count), side="right")
    return pairs[:, 1], starts, ends


def smooth_weights(weights, neighbours, starts, ends, anchors, iterations=120, blend=0.7):
    """Diffuse weights over the surface, holding the anchored vertices fixed.

    The anchors are what make this work: unconstrained diffusion converges on
    a uniform blend, and then every bone drags the entire body.
    """
    counts = (ends - starts).astype(np.float64)
    counts[counts == 0] = 1.0
    empty = ends <= starts
    pinned = weights[anchors].copy()
    for _ in range(iterations):
        summed = np.add.reduceat(weights[neighbours], starts, axis=0)
        summed[empty] = weights[empty]
        weights = (1 - blend) * weights + blend * (summed / counts[:, None])
        weights[anchors] = pinned
        total = weights.sum(axis=1, keepdims=True)
        total[total == 0] = 1.0
        weights /= total
    return weights


def skin(positions, indices, skeleton, welded, exclusive_sides=None,
         structural=("Root",), max_influences=4, anchor_quantile=0.55):
    """Bind vertices to bones: nearest bone, then diffusion in the seams."""
    unique_count = int(welded.max()) + 1
    unique_positions = np.zeros((unique_count, 3))
    np.add.at(unique_positions, welded, positions)
    counts = np.bincount(welded, minlength=unique_count).astype(np.float64)
    counts[counts == 0] = 1.0
    unique_positions /= counts[:, None]

    segments = skeleton.bone_segments()
    distances = np.stack([_segment_distance(unique_positions, a, b) for a, b in segments], axis=1)
    for name in structural:
        if name in skeleton.index:
            distances[:, skeleton.index[name]] = np.inf

    # A limb must not claim geometry from the other half of the body: fists and
    # feet often pass closer to the opposite hip than to their own bone.
    if exclusive_sides:
        span = max(np.abs(unique_positions[:, 0]).max(), 1e-6)
        for side, bones in exclusive_sides.items():
            wrong = unique_positions[:, 0] > 0.12 * span if side == "L" \
                else unique_positions[:, 0] < -0.12 * span
            present = [skeleton.index[b] for b in bones if b in skeleton.index]
            if present:
                distances[np.ix_(wrong, present)] = np.inf

    best = distances.argmin(axis=1)
    weights = np.zeros((unique_count, skeleton.count))
    weights[np.arange(unique_count), best] = 1.0

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
    weights = smooth_weights(weights, neighbours, starts, ends, anchors)[welded]

    top = np.argsort(-weights, axis=1)[:, :max_influences]
    kept = np.take_along_axis(weights, top, axis=1)
    kept /= np.maximum(kept.sum(axis=1, keepdims=True), 1e-9)
    return top.astype(np.uint16), kept.astype(np.float32)
