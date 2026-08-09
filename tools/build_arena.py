"""Convert the Arena 7 USDZ into a web-ready GLB.

Parts listed in REMOVE_PARTS are dropped from the export -- that is how the
floating balloons above the arena get deleted.
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import usd_read
from glb import GLB, compute_normals

# Scene units are centimetres; 100 arena units == 1 metre in the game scene.
SCALE = 1.0 / 100.0

# Meshes deleted from the arena: the two hot-air balloons floating over the
# field. Each balloon is split across four meshes -- envelope, rope net,
# rigging lines and basket -- and none of these names is used by anything else.
REMOVE_PARTS = {
    "MAPA3_mergedObject_Material_028_0",  # red balloon envelopes
    "MAPA3_mergedObject_Material_029_0",  # rope netting over the envelopes
    "MAPA3_mergedObject_Material_030_0",  # rigging lines down to the baskets
    "MAPA3_mergedObject_Material_027_0",  # wicker baskets
}

# Tower footprints, in the same recentred metres the game uses. Triangles
# inside these cylinders are lifted out of the merged arena meshes into their
# own nodes, so a destroyed tower can actually be hidden at runtime.
TOWER_CUTS = [
    ("blue-king", -13.6, 0.15, 2.7, 2.35, 6.2),
    ("blue-left", -9.15, -5.30, 1.7, 2.35, 5.0),
    ("blue-right", -9.15, 5.25, 1.7, 2.35, 5.0),
    ("red-king", 15.7, 0.15, 2.7, 2.35, 6.2),
    ("red-left", 11.2, -5.30, 1.7, 2.35, 5.0),
    ("red-right", 11.2, 5.20, 1.7, 2.35, 5.0),
]


# Only the MAPA1 group is the actual Royal Arena shell; MAPA2/MAPA3 are the
# other two arenas stored in the same file. Set via --group.
GROUPS = {
    "mapa1": "MAPA1_",
    "mapa2": "MAPA2_",
    "mapa3": "MAPA3_",
    "all": "",
}


def _add_part(glb, name, positions, indices, uvs, material):
    """Add one mesh, dropping the vertices this triangle set does not use."""
    used = np.unique(indices)
    remap = np.full(len(positions), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    local_positions = positions[used]
    local_uvs = uvs[used] if uvs is not None else None
    local_indices = remap[indices]
    normals = compute_normals(local_positions.astype(np.float64), local_indices)
    mesh = glb.add_mesh(name, local_positions, local_indices, normals=normals,
                        uvs=local_uvs, material=material)
    return glb.add_node(name, mesh=mesh)


def build(out_path, group="all", remove=(), keep_only=None):
    texture_dir = usd_read.extract_textures()
    parts, materials = usd_read.read_parts(scale=SCALE)

    prefix = GROUPS[group]
    remove = set(remove)

    glb = GLB()
    texture_cache = {}
    material_cache = {}

    def material_index(name):
        if name in material_cache:
            return material_cache[name]
        info = materials.get(name, {"texture": None, "color": (0.8, 0.8, 0.8),
                                    "metallic": 0.0, "roughness": 0.7})
        tex_index = None
        if info["texture"]:
            path = os.path.join(texture_dir, info["texture"])
            if os.path.exists(path):
                if path not in texture_cache:
                    texture_cache[path] = glb.add_texture(glb.add_image(path))
                tex_index = texture_cache[path]
        color = (1, 1, 1, 1) if tex_index is not None else tuple(info["color"]) + (1.0,)
        index = glb.add_material(name or "mat", base_color_texture=tex_index, base_color=color,
                                 metallic=info.get("metallic", 0.0),
                                 roughness=info.get("roughness", 0.7))
        material_cache[name] = index
        return index

    kept, dropped = [], []
    for part in parts:
        if prefix and not part.name.startswith(prefix):
            continue
        if part.name in remove:
            dropped.append(part.name)
            continue
        if keep_only is not None and part.name not in keep_only:
            continue
        kept.append(part)

    # Re-centre the arena on the origin, floor at y = 0.
    stacked = np.vstack([p.positions for p in kept])
    lo, hi = stacked.min(0), stacked.max(0)
    offset = np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2], dtype=np.float32)

    root = glb.add_node("Arena", root=True)
    children = []
    tower_pieces = {name: [] for name, *_ in TOWER_CUTS}

    for part in kept:
        positions = (part.positions - offset).astype(np.float32)
        tris = part.indices.reshape(-1, 3)
        centroids = positions[tris].mean(axis=1)

        # Claim this part's triangles for whichever tower they sit inside.
        owner = np.full(len(tris), -1, dtype=np.int64)
        for i, (name, tx, tz, radius, y_lo, y_hi) in enumerate(TOWER_CUTS):
            inside = ((centroids[:, 0] - tx) ** 2 + (centroids[:, 2] - tz) ** 2 < radius * radius)
            inside &= (centroids[:, 1] > y_lo) & (centroids[:, 1] < y_hi) & (owner < 0)
            owner[inside] = i

        for i, (name, *_rest) in enumerate(TOWER_CUTS):
            picked = tris[owner == i]
            if len(picked) < 4:
                continue
            tower_pieces[name].append((positions, picked, part.uvs, part.material))

        remaining = tris[owner < 0]
        if len(remaining) == 0:
            continue
        children.append(_add_part(glb, part.name, positions, remaining.reshape(-1),
                                  part.uvs, material_index(part.material)))

    # One node per tower, named so the game can switch it off when it falls.
    for name, pieces in tower_pieces.items():
        if not pieces:
            print(f"warning: no geometry captured for {name}")
            continue
        kids = [_add_part(glb, f"{name}#{k}", positions, picked.reshape(-1), uvs,
                          material_index(material))
                for k, (positions, picked, uvs, material) in enumerate(pieces)]
        node = glb.add_node(f"Tower_{name}", children=kids)
        children.append(node)
        print(f"  {name}: {sum(len(p[1]) for p in pieces)} tris in its own node")

    glb.set_children(root, children)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    glb.save(out_path)
    size = os.path.getsize(out_path) / 1e6
    print(f"{out_path}: {len(kept)} parts, "
          f"{sum(len(p.indices) // 3 for p in kept)} tris, {size:.1f} MB")
    if dropped:
        print("removed:", ", ".join(sorted(dropped)))
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--out", default="web/assets/arena.glb")
    parser.add_argument("-g", "--group", default="all", choices=sorted(GROUPS))
    parser.add_argument("--keep-only", nargs="*", default=None)
    parser.add_argument("--no-remove", action="store_true")
    args = parser.parse_args()
    build(args.out, args.group, () if args.no_remove else REMOVE_PARTS, args.keep_only)
