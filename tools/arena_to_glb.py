"""Convert a USDZ arena into a GLB, which every engine reads without a plugin.

Usage:
    python3 tools/arena_to_glb.py <source.usdz> <out.glb>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import trimesh
from PIL import Image

from usdload import load_full


def to_glb(usdz_path, glb_path):
    scene = trimesh.Scene()
    for i, m in enumerate(load_full(usdz_path)):
        F, C, uv = m['F'], m['C'], m['uv']
        if len(F) == 0:
            continue
        if uv is None:
            tm = trimesh.Trimesh(m['V'], F, process=False)
        else:
            # glTF wants one UV per vertex, so split vertices per unique (position, uv) pair
            idx = C if m['uvinterp'] == 'faceVarying' else F
            if m['uvidx'] is not None:
                idx = m['uvidx'][idx]
            corners = np.stack([F.ravel(), idx.ravel()], 1)
            uniq, inv = np.unique(corners, axis=0, return_inverse=True)
            tm = trimesh.Trimesh(m['V'][uniq[:, 0]], inv.reshape(-1, 3), process=False)
            tm.visual = trimesh.visual.TextureVisuals(
                uv=uv[uniq[:, 1]],
                image=Image.fromarray(m['tex']) if m['tex'] is not None else None)
        scene.add_geometry(tm, node_name=f"{m['name']}_{i}")
    scene.export(glb_path)
    return glb_path


if __name__ == '__main__':
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    out = to_glb(sys.argv[1], sys.argv[2])
    print('->', out, os.path.getsize(out) // 1024, 'KB')
