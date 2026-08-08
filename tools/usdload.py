"""Read a USDZ into plain numpy arrays (world-space points, triangles, UVs, textures)."""
import io
import zipfile

import numpy as np
from PIL import Image
from pxr import Usd, UsdGeom, UsdShade


def _diffuse_texture_path(mat):
    if not mat:
        return None
    surf = mat.GetSurfaceOutput()
    if not surf or not surf.HasConnectedSource():
        return None
    shader = UsdShade.Shader(surf.GetConnectedSource()[0].GetPrim())
    inp = shader.GetInput('diffuseColor')
    if not inp:
        return None
    src = inp.GetConnectedSource()
    if not src:
        return None
    f = UsdShade.Shader(src[0].GetPrim()).GetInput('file')
    return f.Get().path if f and f.Get() else None


def load_full(usdz_path):
    """Return one dict per mesh: world points V, triangles F, face-corner index C,
    uv array + interpolation, and the decoded diffuse texture."""
    stage = Usd.Stage.Open(usdz_path)
    xform_cache = UsdGeom.XformCache()
    package = zipfile.ZipFile(usdz_path)
    textures = {}

    def texture(name):
        if name is None:
            return None
        key = name.lstrip('./')
        if key not in textures:
            try:
                textures[key] = np.asarray(Image.open(io.BytesIO(package.read(key))).convert('RGB'))
            except Exception:
                textures[key] = None
        return textures[key]

    out = []
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        mesh = UsdGeom.Mesh(prim)
        pts = mesh.GetPointsAttr().Get()
        if not pts:
            continue
        counts = np.array(mesh.GetFaceVertexCountsAttr().Get())
        indices = np.array(mesh.GetFaceVertexIndicesAttr().Get())
        M = np.array(xform_cache.GetLocalToWorldTransform(prim), dtype=np.float64)
        V = np.array(pts, dtype=np.float64) @ M[:3, :3] + M[3, :3]

        primvars = UsdGeom.PrimvarsAPI(prim)
        uv = uv_interp = uv_idx = None
        for nm in ('st', 'st0', 'UVMap', 'uv'):
            pv = primvars.GetPrimvar(nm)
            if pv and pv.HasValue():
                uv = np.array(pv.Get(), dtype=np.float64)
                uv_interp = pv.GetInterpolation()
                ii = pv.GetIndices()
                uv_idx = np.array(ii) if ii else None
                break

        tris, corners, off = [], [], 0
        for c in counts:
            face = indices[off:off + c]
            for k in range(1, c - 1):
                tris.append((face[0], face[k], face[k + 1]))
                corners.append((off, off + k, off + k + 1))
            off += c

        bound = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
        out.append(dict(
            path=str(prim.GetPath()), name=prim.GetName(), V=V,
            F=np.array(tris, dtype=np.int64) if tris else np.zeros((0, 3), np.int64),
            C=np.array(corners, dtype=np.int64) if corners else np.zeros((0, 3), np.int64),
            uv=uv, uvinterp=uv_interp, uvidx=uv_idx,
            tex=texture(_diffuse_texture_path(bound)) if bound else None,
            mat=str(bound.GetPath()) if bound else None))
    return out
