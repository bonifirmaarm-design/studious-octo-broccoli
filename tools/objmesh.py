"""OBJ loading plus the mesh surgery used to clean up the Mega Knight scans."""

import numpy as np


def load_obj(path):
    """Returns (positions, uvs, faces) where faces are (v_index, vt_index) pairs."""
    positions, uvs, faces = [], [], []
    with open(path) as fh:
        for line in fh:
            if line.startswith("v "):
                positions.append([float(x) for x in line.split()[1:4]])
            elif line.startswith("vt "):
                uvs.append([float(x) for x in line.split()[1:3]])
            elif line.startswith("f "):
                corners = []
                for token in line.split()[1:]:
                    bits = token.split("/")
                    vi = int(bits[0]) - 1
                    ti = int(bits[1]) - 1 if len(bits) > 1 and bits[1] else -1
                    corners.append((vi, ti))
                for k in range(1, len(corners) - 1):
                    faces.append((corners[0], corners[k], corners[k + 1]))
    return (np.asarray(positions, dtype=np.float64),
            np.asarray(uvs, dtype=np.float32) if uvs else None,
            np.asarray(faces, dtype=np.int64))


def unify(positions, uvs, faces):
    """Collapse (v, vt) corner pairs into single glTF vertices."""
    corners = faces.reshape(-1, 2)
    keys, inverse = np.unique(corners, axis=0, return_inverse=True)
    new_positions = positions[keys[:, 0]]
    if uvs is not None:
        new_uvs = np.zeros((len(keys), 2), dtype=np.float32)
        has_uv = keys[:, 1] >= 0
        new_uvs[has_uv] = uvs[keys[has_uv, 1]]
        new_uvs[:, 1] = 1.0 - new_uvs[:, 1]
    else:
        new_uvs = None
    return new_positions, new_uvs, inverse.astype(np.int64).reshape(-1)


def connected_components(vertex_count, indices):
    """Union-find over triangle edges; returns a per-vertex component label."""
    parent = np.arange(vertex_count)

    def find(a):
        root = a
        while parent[root] != root:
            root = parent[root]
        while parent[a] != root:
            parent[a], a = root, parent[a]
        return root

    tris = indices.reshape(-1, 3)
    for a, b in ((0, 1), (1, 2), (2, 0)):
        for x, y in zip(tris[:, a], tris[:, b]):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry
    labels = np.array([find(i) for i in range(vertex_count)])
    _, labels = np.unique(labels, return_inverse=True)
    return labels


def weld(positions, tolerance=1e-5):
    """Map duplicate positions onto a shared index so components join up."""
    quantised = np.round(positions / tolerance).astype(np.int64)
    _, first, inverse = np.unique(quantised, axis=0, return_index=True, return_inverse=True)
    return inverse


def drop_vertices(positions, uvs, indices, keep_mask):
    """Delete vertices (and any triangle touching them), re-indexing the result."""
    tris = indices.reshape(-1, 3)
    keep_tris = keep_mask[tris].all(axis=1)
    tris = tris[keep_tris]

    used = np.zeros(len(positions), dtype=bool)
    used[tris.reshape(-1)] = True
    remap = np.full(len(positions), -1, dtype=np.int64)
    remap[used] = np.arange(used.sum())

    return (positions[used],
            uvs[used] if uvs is not None else None,
            remap[tris].reshape(-1),
            used)


def largest_component(positions, uvs, indices):
    """Keep only the biggest connected island (drops scan debris)."""
    welded = weld(positions)
    labels = connected_components(welded.max() + 1, welded[indices])[welded]
    counts = np.bincount(labels)
    keep = labels == counts.argmax()
    return drop_vertices(positions, uvs, indices, keep)
