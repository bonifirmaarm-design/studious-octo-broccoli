"""Remove the two hot-air balloons hovering over the Royal Arena battlefield.

They sit right on the playable field and would get in the way of unit placement
and the camera, so they are dropped from the scene. The four meshes listed below
contain nothing but the balloons (envelope, basket, ropes and rope anchors), so
removing the prims is enough - no geometry surgery required, and the rest of the
arena is bit-for-bit untouched.

Usage:
    python3 tools/clean_arena.py <source.usdz> <out.usdz>
"""
import os
import shutil
import sys
import tempfile
import zipfile

from pxr import Sdf, Usd, UsdGeom, UsdUtils

BALLOON_MESHES = [
    'MAPA3_mergedObject_Material_027_0',   # basket
    'MAPA3_mergedObject_Material_028_0',   # envelope
    'MAPA3_mergedObject_Material_029_0',   # ropes and rings
    'MAPA3_mergedObject_Material_030_0',   # rope anchors
]


def build(src, out):
    work = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(src) as z:
            for name in z.namelist():
                dst = os.path.join(work, name)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, 'wb') as fh:
                    fh.write(z.read(name))

        # Edit the packaged crate layer directly rather than flattening the stage;
        # flattening rewrites every prim and nearly doubles the file size.
        scene = os.path.join(work, 'scene.usdc')
        layer = Sdf.Layer.FindOrOpen(scene)
        stage = Usd.Stage.Open(layer)

        removed = []
        for prim in stage.Traverse():
            if prim.GetName() in BALLOON_MESHES and prim.IsA(UsdGeom.Mesh):
                parent = prim.GetParent()
                target = parent if parent.GetName() == prim.GetName() else prim
                removed.append(str(target.GetPath()))
        for path in removed:
            spec = layer.GetPrimAtPath(path)
            if spec:
                del spec.nameParent.nameChildren[spec.name]
        layer.Save()

        out = os.path.abspath(out)
        if os.path.exists(out):
            os.remove(out)
        cwd = os.getcwd()
        os.chdir(work)
        try:
            UsdUtils.CreateNewUsdzPackage(Sdf.AssetPath('scene.usdc'), out)
        finally:
            os.chdir(cwd)
        return out, removed
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    path, prims = build(sys.argv[1], sys.argv[2])
    for p in prims:
        print('removed', p)
    print('->', path, os.path.getsize(path) // 1024, 'KB')
