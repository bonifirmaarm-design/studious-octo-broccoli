"""Turn a raw Mega Knight scan (OBJ + textures) into a rigged, animated GLB.

    python3 tools/build_knight.py assets_raw/mk1 web/assets/knight_blue.glb

Steps: drop the display plinth, normalise the scale, generate a skeleton,
skin the mesh to it, then bake the animation clips from tools/anim.py.
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import anatomy
import anim
import objmesh
import rig
from glb import GLB, compute_normals


def build(src, out, height=1.0, clips=None, keep_pedestal=False):
    positions, uvs, faces = objmesh.load_obj(os.path.join(src, "output.obj"))
    positions, uvs, indices = objmesh.unify(positions, uvs, faces)
    raw_tris = len(indices) // 3

    cut = None
    if not keep_pedestal:
        positions, uvs, indices, cut = anatomy.cut_pedestal(positions, uvs, indices)
    positions, _ = anatomy.normalise(positions, height)

    skeleton = rig.Skeleton(height=height)
    welded = objmesh.weld(positions)
    joints, weights = rig.skin(positions, indices, skeleton, welded)

    glb = GLB()
    texture = glb.add_texture(glb.add_image(os.path.join(src, "textured_mesh.jpg")))
    material = glb.add_material("MegaKnight", base_color_texture=texture,
                                metallic=0.05, roughness=0.72, double_sided=False)
    mesh = glb.add_mesh("MegaKnightBody", positions.astype(np.float32), indices,
                        normals=compute_normals(positions, indices), uvs=uvs,
                        material=material, joints=joints, weights=weights)

    # Joint nodes, parents first so children already exist when we link them.
    local = skeleton.local_rest()
    joint_nodes = [glb.add_node(name, translation=local[i]) for i, name in enumerate(skeleton.names)]
    for i in range(skeleton.count):
        if skeleton.children[i]:
            glb.set_children(joint_nodes[i], [joint_nodes[c] for c in skeleton.children[i]])

    skin_index = glb.add_skin("MegaKnightSkin", joint_nodes,
                              rig.inverse_bind_matrices(skeleton), skeleton=joint_nodes[0])
    mesh_node = glb.add_node("MegaKnight", mesh=mesh, skin=skin_index)
    glb.add_node("MegaKnightRoot", children=[joint_nodes[0], mesh_node], root=True)

    for factory in (clips or anim.ALL_CLIPS):
        clip = factory()
        times, quats, root_pos, root_scale = clip.sample()
        channels = []
        for name, values in quats.items():
            if name not in skeleton.index:
                raise KeyError(f"clip {clip.name!r} animates unknown joint {name!r}")
            channels.append((joint_nodes[skeleton.index[name]], "rotation", times, values))
        root_node = joint_nodes[skeleton.index["Root"]]
        if np.abs(root_pos).max() > 1e-6:
            channels.append((root_node, "translation", times, root_pos * height))
        if np.abs(root_scale - 1).max() > 1e-6:
            channels.append((root_node, "scale", times, root_scale))
        glb.add_animation(clip.name, channels)

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    glb.save(out)
    print(f"{out}: {len(positions)} verts, {raw_tris} -> {len(indices)//3} tris, "
          f"{skeleton.count} bones, {len(clips or anim.ALL_CLIPS)} clips, "
          f"pedestal cut at y={cut if cut is None else round(cut, 4)}, "
          f"{os.path.getsize(out)/1e6:.1f} MB")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("out")
    parser.add_argument("--height", type=float, default=1.0)
    parser.add_argument("--keep-pedestal", action="store_true")
    args = parser.parse_args()
    build(args.src, args.out, args.height, keep_pedestal=args.keep_pedestal)
