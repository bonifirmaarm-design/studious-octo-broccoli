"""Strip the ground plate off a generated character mesh so it can be rigged.

The image-to-3D models come out standing on a flat, textured slab that is welded
to the character's feet. That slab has to go before the mesh can be skinned and
animated. This script finds the slab, cuts it away, closes the holes it leaves
under the soles, and moves the origin to the feet so the model drops straight
onto the arena floor at y = 0.

Usage:
    python3 tools/clean_pedestal.py <source.zip|source_dir> <out_dir> [name]

The source is one of the raw generator outputs (a zip, or a directory holding
output.obj / output.mtl / textured_mesh.jpg / the metallic-roughness map).
Writes model.obj + model.mtl + model.glb + albedo.jpg + orm.jpg into out_dir.
"""
import os
import shutil
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import trimesh
from PIL import Image

from objtool import boundary_loops, read_obj, weld, write_obj

ORM_SIZE = 2048  # the 4k metallic/roughness map is downsized on the way out


def find_plate_top(U, Fw):
    """Return the y of the top of the ground slab, or None if there isn't one.

    The slab (plus whatever surface relief was baked onto it) is the only thing
    near the bottom of the mesh that spans the model's whole X/Z footprint - the
    character itself covers less than a tenth of it - so walk up in thin slices
    and take the highest slice that is still full width.
    """
    cen = U[Fw].mean(1)

    lo, hi = U[:, 1].min(), U[:, 1].max()
    span = hi - lo
    ext = U.max(0) - U.min(0)
    footprint = ext[0] * ext[2]

    plate_top = None
    edges = np.linspace(lo, lo + 0.35 * span, 71)
    for y0, y1 in zip(edges[:-1], edges[1:]):
        sel = (cen[:, 1] >= y0) & (cen[:, 1] < y1)
        if sel.sum() < 200:
            continue
        xz = cen[sel][:, [0, 2]]
        cover = np.prod(xz.max(0) - xz.min(0)) / footprint
        if cover > 0.5:
            plate_top = y1
    return plate_top


def clean(src_dir, out_dir, name='unit', y_cut=None):
    obj = os.path.join(src_dir, 'output.obj')
    V, VT, VN, F, _mtllib, _usemtl, _o = read_obj(obj)
    U, _inv, Fw = weld(V, F)

    if y_cut is None:
        plate_top = find_plate_top(U, Fw)
        if plate_top is None:
            raise SystemExit(f'{obj}: no ground plate found - pass y_cut explicitly')
        y_cut = plate_top + 0.002 * (U[:, 1].max() - U[:, 1].min())

    # 1. drop every face that belongs to the slab
    keep = U[Fw].mean(1)[:, 1] > y_cut
    Fw_k, F_k = Fw[keep], F[keep]

    # 2. drop small islands left floating after the cut (texture debris on the slab)
    tm = trimesh.Trimesh(U, Fw_k, process=False)
    comps = trimesh.graph.connected_components(tm.face_adjacency, nodes=np.arange(len(Fw_k)))
    big = [c for c in comps if len(c) >= 30]
    keep_faces = np.sort(np.concatenate(big)) if big else np.arange(len(Fw_k))
    dropped = len(Fw_k) - len(keep_faces)
    Fw_k, F_k = Fw_k[keep_faces], F_k[keep_faces]

    # 3. cap the holes the cut opened under the soles (and under the cape hem)
    loops = boundary_loops(Fw_k)
    Ul, VTl = list(U), list(VT)
    uv_of_vert = {}
    for tri_w, tri_o in zip(Fw_k, F_k):
        for wi, corner in zip(tri_w, tri_o):
            uv_of_vert.setdefault(int(wi), int(corner[1]))

    new_faces = []
    for loop in loops:
        ci = len(Ul)
        Ul.append(np.array([U[i] for i in loop]).mean(0))
        ti_c = len(VTl)
        VTl.append(np.array([VT[uv_of_vert[i]] for i in loop]).mean(0))
        for k in range(len(loop)):
            a, b = loop[k], loop[(k + 1) % len(loop)]
            new_faces.append(((ci, ti_c, -1), (b, uv_of_vert[b], -1), (a, uv_of_vert[a], -1)))

    U2, VT2 = np.array(Ul), np.array(VTl)
    faces = [tuple((int(w), int(o[1]), -1) for w, o in zip(tw, to)) for tw, to in zip(Fw_k, F_k)]
    faces.extend(new_faces)
    Fo = np.array(faces, dtype=np.int64)

    # 4. compact positions and UVs
    used = np.unique(Fo[:, :, 0])
    remap = np.zeros(len(U2), np.int64)
    remap[used] = np.arange(len(used))
    U3 = U2[used]
    Fo[:, :, 0] = remap[Fo[:, :, 0]]

    usedt = np.unique(Fo[:, :, 1])
    remapt = np.zeros(len(VT2), np.int64)
    remapt[usedt] = np.arange(len(usedt))
    VT3 = VT2[usedt]
    Fo[:, :, 1] = remapt[Fo[:, :, 1]]

    # 5. origin between the feet, on the ground
    c = (U3.min(0) + U3.max(0)) / 2
    U3[:, 0] -= c[0]
    U3[:, 2] -= c[2]
    U3[:, 1] -= U3[:, 1].min()

    os.makedirs(out_dir, exist_ok=True)
    write_obj(os.path.join(out_dir, 'model.obj'), U3, VT3, Fo,
              mtllib='model.mtl', usemtl=name, oname=name)
    with open(os.path.join(out_dir, 'model.mtl'), 'w') as fh:
        fh.write(f'newmtl {name}\n'
                 'Kd 1.000000 1.000000 1.000000\n'
                 'Ks 0.500000 0.500000 0.500000\n'
                 'Ns 50.0\nNi 1.500000\nd 1.000000\nillum 2\n'
                 'Pr 0.500000\nPm 0.000000\n'
                 'map_Kd albedo.jpg\n')

    albedo = Image.open(os.path.join(src_dir, 'textured_mesh.jpg')).convert('RGB')
    albedo.save(os.path.join(out_dir, 'albedo.jpg'), quality=92)
    orm_src = os.path.join(src_dir, 'textured_mesh_metallic.jpg-textured_mesh_roughness.png')
    if os.path.exists(orm_src):
        Image.open(orm_src).convert('RGB').resize((ORM_SIZE, ORM_SIZE), Image.LANCZOS) \
             .save(os.path.join(out_dir, 'orm.jpg'), quality=92)

    uv = np.zeros((len(U3), 2))
    uv[Fo[:, :, 0].ravel()] = VT3[Fo[:, :, 1].ravel()]
    glb = trimesh.Trimesh(U3, Fo[:, :, 0], process=False)
    glb.visual = trimesh.visual.TextureVisuals(uv=uv, image=albedo)
    glb.export(os.path.join(out_dir, 'model.glb'))

    return dict(y_cut=round(float(y_cut), 4), faces=len(Fo), verts=len(U3),
                holes_capped=len(loops), islands_dropped=dropped,
                size=np.round(U3.max(0) - U3.min(0), 3).tolist())


def main(argv):
    if len(argv) < 3:
        raise SystemExit(__doc__)
    src, out = argv[1], argv[2]
    name = argv[3] if len(argv) > 3 else 'unit'
    tmp = None
    if zipfile.is_zipfile(src):
        tmp = tempfile.mkdtemp()
        with zipfile.ZipFile(src) as z:
            z.extractall(tmp)
        src = tmp
    try:
        print(clean(src, out, name))
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main(sys.argv)
