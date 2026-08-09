"""Build every roster entry into a rigged, animated GLB.

    python3 tools/build_unit.py             # everything
    python3 tools/build_unit.py archer_blue # one unit
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import anatomy
import anim2
import archetypes
import objmesh
import rig2
from glb import GLB, compute_normals
from roster import ROSTER

OUT_DIR = "web/assets/units"


def load_clean(src, keep_pedestal=False):
    """OBJ -> plinth removed -> normalised to 1 unit tall, feet on y = 0."""
    positions, uvs, faces = objmesh.load_obj(os.path.join(src, "output.obj"))
    positions, uvs, indices = objmesh.unify(positions, uvs, faces)
    before = len(positions)
    cut = None
    if not keep_pedestal:
        positions, uvs, indices, cut = anatomy.cut_pedestal(positions, uvs, indices)
    positions, _ = anatomy.normalise(positions)
    return positions, uvs, indices, cut, before


def rest_correction(archetype, landmarks):
    """How far the arms must drop out of the scanned pose to look natural.

    The T-posed models need about 55 degrees; the Mega Knights were scanned
    with their arms already low and need almost none, so the angle is measured
    rather than assumed.
    """
    if archetype not in ("biped", "mega") or "arm_span" not in landmarks:
        return None
    horizontal = max(landmarks["arm_span"] * 0.90 - landmarks["shoulder_x"], 1e-3)
    vertical = landmarks["shoulder_y"] - landmarks["hand_y"]
    current = np.degrees(np.arctan2(vertical, horizontal))
    # A relaxed arm hangs about 78 degrees below the horizontal. Targeting 52
    # left the T-posed models with their arms still sticking out sideways.
    drop = float(np.clip(78.0 - current, 0.0, 88.0))
    return anim2.arm_drop_base(drop)


def build(key, out_dir=OUT_DIR):
    entry = ROSTER[key]
    src = os.path.join("assets_raw", entry["src"])
    positions, uvs, indices, cut, before = load_clean(src)

    joints, landmarks = archetypes.BUILDERS[entry["archetype"]](positions)
    skeleton = rig2.Skeleton(joints)
    welded = objmesh.weld(positions)
    joint_index, weights = rig2.skin(positions, indices, skeleton, welded,
                                     exclusive_sides=archetypes.EXCLUSIVE)

    glb = GLB()
    texture = glb.add_texture(glb.add_image(os.path.join(src, "textured_mesh.jpg")))
    material = glb.add_material(key, base_color_texture=texture,
                               metallic=0.03, roughness=0.75, double_sided=False)
    mesh = glb.add_mesh(f"{key}_body", positions.astype(np.float32), indices,
                        normals=compute_normals(positions, indices), uvs=uvs,
                        material=material, joints=joint_index, weights=weights)

    translations, rotations = skeleton.local_transforms()
    nodes = [glb.add_node(name, translation=translations[i], rotation=rotations[i])
             for i, name in enumerate(skeleton.names)]
    for i in range(skeleton.count):
        if skeleton.children[i]:
            glb.set_children(nodes[i], [nodes[c] for c in skeleton.children[i]])

    skin_index = glb.add_skin(f"{key}_skin", nodes, skeleton.inverse_bind_matrices(),
                              skeleton=nodes[0])
    mesh_node = glb.add_node(key, mesh=mesh, skin=skin_index)
    glb.add_node(f"{key}_root", children=[nodes[0], mesh_node], root=True)

    clip_set = anim2.clip_set(entry["archetype"],
                              reach=entry.get("reach", 0.5 if entry["archetype"] == "mega" else 1.0),
                              base=rest_correction(entry["archetype"], landmarks))
    names = set(skeleton.names)
    written = []
    for clip_name in entry["clips"]:
        clip = clip_set[clip_name]()
        times, rotation_tracks, root_pos, root_scale = clip.sample(names)
        channels = [(nodes[skeleton.index[j]], "rotation", times, values)
                    for j, values in rotation_tracks.items()]
        root_node = nodes[skeleton.index["Root"]]
        if np.abs(root_pos).max() > 1e-6:
            channels.append((root_node, "translation", times,
                             root_pos + skeleton.rest[skeleton.index["Root"]]))
        if np.abs(root_scale - 1).max() > 1e-6:
            channels.append((root_node, "scale", times, root_scale))
        glb.add_animation(clip.name, channels)
        written.append(clip.name)

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{key}.glb")
    glb.save(path)
    print(f"{key:<18} {before:>6} -> {len(positions):>6} verts, {skeleton.count:>2} bones, "
          f"clips={','.join(written)}, plinth={'-' if cut is None else round(cut, 3)}, "
          f"{os.path.getsize(path)/1e6:.1f} MB")
    return path


if __name__ == "__main__":
    keys = sys.argv[1:] or list(ROSTER)
    for key in keys:
        build(key)
