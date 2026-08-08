"""Render the generated skeleton on top of a knight so joint placement can be checked."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import anatomy
import objmesh
import rig
from glb import GLB, compute_normals

CUBE_V = np.array([[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
                   [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]], dtype=np.float64)
CUBE_I = np.array([0, 1, 2, 0, 2, 3, 5, 4, 7, 5, 7, 6, 4, 0, 3, 4, 3, 7,
                   1, 5, 6, 1, 6, 2, 3, 2, 6, 3, 6, 7, 4, 5, 1, 4, 1, 0], dtype=np.int64)


def marker(centre, size):
    return CUBE_V * size + centre


def load_knight(src):
    positions, uvs, faces = objmesh.load_obj(os.path.join(src, "output.obj"))
    positions, uvs, indices = objmesh.unify(positions, uvs, faces)
    positions, uvs, indices, cut = anatomy.cut_pedestal(positions, uvs, indices)
    positions, _ = anatomy.normalise(positions)
    return positions, uvs, indices, cut


def main(src, out, show_weights=None):
    positions, uvs, indices, cut = load_knight(src)
    skeleton = rig.Skeleton()

    glb = GLB()
    if show_weights is None:
        texture = glb.add_texture(glb.add_image(os.path.join(src, "textured_mesh.jpg")))
        body_material = glb.add_material("body", base_color_texture=texture, roughness=0.8,
                                         base_color=(1, 1, 1, 0.28), alpha_mode="BLEND")
        body_uv = uvs
    else:
        welded = objmesh.weld(positions)
        joints, weights = rig.skin(positions, indices, skeleton, welded)
        target = skeleton.index[show_weights]
        value = np.zeros(len(positions), dtype=np.float32)
        for k in range(joints.shape[1]):
            value[joints[:, k] == target] += weights[joints[:, k] == target, k]
        body_uv = np.stack([np.clip(value, 0, 1), np.full(len(value), 0.5)], axis=1).astype(np.float32)
        ramp = np.zeros((1, 256, 3), dtype=np.uint8)
        ramp[0, :, 0] = np.linspace(30, 255, 256)
        ramp[0, :, 2] = np.linspace(120, 20, 256)
        import io

        from PIL import Image
        buf = io.BytesIO()
        Image.fromarray(np.repeat(ramp, 8, axis=0)).save(buf, format="PNG")
        texture = glb.add_texture(glb.add_image_bytes(buf.getvalue(), "image/png"))
        body_material = glb.add_material("weights", base_color_texture=texture, roughness=0.9)

    body = glb.add_mesh("body", positions.astype(np.float32), indices,
                        normals=compute_normals(positions, indices),
                        uvs=body_uv, material=body_material)
    nodes = [glb.add_node("Body", mesh=body, root=True)]

    joint_material = glb.add_material("joint", base_color=(1.0, 0.15, 0.6, 1.0),
                                      roughness=0.4, metallic=0.0, emissive=(0.6, 0.0, 0.25))
    bone_material = glb.add_material("bone", base_color=(0.1, 1.0, 0.4, 1.0),
                                     roughness=0.4, emissive=(0.0, 0.4, 0.15))
    for i, name in enumerate(skeleton.names):
        points = marker(skeleton.rest[i], 0.018)
        mesh = glb.add_mesh(f"J_{name}", points.astype(np.float32), CUBE_I,
                            normals=compute_normals(points, CUBE_I), material=joint_material)
        nodes.append(glb.add_node(f"J_{name}", mesh=mesh, root=True))

    for i, p in enumerate(skeleton.parents):
        if p < 0:
            continue
        for t in np.linspace(0.15, 0.85, 5):
            points = marker(skeleton.rest[p] * (1 - t) + skeleton.rest[i] * t, 0.007)
            mesh = glb.add_mesh("bone", points.astype(np.float32), CUBE_I,
                                normals=compute_normals(points, CUBE_I), material=bone_material)
            nodes.append(glb.add_node("bone", mesh=mesh, root=True))

    glb.save(out)
    print(f"{out}  cut={cut:.4f}  verts={len(positions)}")
    return out


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
