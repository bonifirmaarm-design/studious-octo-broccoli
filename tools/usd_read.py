"""Read meshes + materials out of the Arena USDZ into plain numpy arrays."""

import os
import zipfile

import numpy as np
from pxr import Gf, Usd, UsdGeom, UsdShade

USDZ = "Arena_7_-_Royal_Arena_Clash_Royale.usdz"


class Part:
    """One triangulated, de-indexed mesh with a material name."""

    def __init__(self, name, positions, uvs, indices, material):
        self.name = name
        self.positions = positions
        self.uvs = uvs
        self.indices = indices
        self.material = material

    @property
    def bounds(self):
        return self.positions.min(0), self.positions.max(0)

    def __repr__(self):
        lo, hi = self.bounds
        return f"<Part {self.name} v={len(self.positions)} tri={len(self.indices)//3} mat={self.material}>"


def _material_of(prim):
    binding = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
    return binding.GetPrim().GetName() if binding else None


def read_materials(stage):
    """material name -> {'texture': str|None, 'color': (r,g,b), 'metallic':, 'roughness':}"""
    out = {}
    for prim in stage.Traverse():
        if prim.GetTypeName() != "Material":
            continue
        info = {"texture": None, "color": (0.8, 0.8, 0.8), "metallic": 0.0, "roughness": 0.7}
        for child in Usd.PrimRange(prim):
            if child.GetTypeName() != "Shader":
                continue
            shader = UsdShade.Shader(child)
            shader_id = shader.GetIdAttr().Get()
            if shader_id == "UsdPreviewSurface":
                diffuse = shader.GetInput("diffuseColor")
                if diffuse:
                    value = diffuse.Get()
                    if isinstance(value, Gf.Vec3f):
                        info["color"] = (value[0], value[1], value[2])
                for key in ("metallic", "roughness"):
                    inp = shader.GetInput(key)
                    if inp and isinstance(inp.Get(), float):
                        info[key] = inp.Get()
            elif shader_id == "UsdUVTexture":
                file_input = shader.GetInput("file")
                asset = file_input.Get() if file_input else None
                if asset is None:
                    continue
                path = asset.path
                # only treat it as base colour if it feeds the surface's diffuse
                if "normal" in path.lower():
                    continue
                info["texture"] = path
        out[prim.GetName()] = info
    return out


def triangulate(counts, indices):
    """Fan-triangulate arbitrary polygons into a flat triangle index list."""
    tris = []
    cursor = 0
    for count in counts:
        face = indices[cursor:cursor + count]
        for k in range(1, count - 1):
            tris.append((face[0], face[k], face[k + 1]))
        cursor += count
    return np.asarray(tris, dtype=np.int64).reshape(-1, 3)


def read_parts(usdz=USDZ, scale=1.0):
    stage = Usd.Stage.Open(usdz)
    cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    parts = []
    for prim in stage.Traverse():
        if prim.GetTypeName() != "Mesh":
            continue
        mesh = UsdGeom.Mesh(prim)
        points = np.asarray(mesh.GetPointsAttr().Get(), dtype=np.float64)
        counts = np.asarray(mesh.GetFaceVertexCountsAttr().Get(), dtype=np.int64)
        vidx = np.asarray(mesh.GetFaceVertexIndicesAttr().Get(), dtype=np.int64)
        if points is None or len(points) == 0:
            continue

        world = np.asarray(cache.GetLocalToWorldTransform(prim), dtype=np.float64).T
        homogeneous = np.hstack([points, np.ones((len(points), 1))])
        points = (homogeneous @ world.T)[:, :3] * scale

        tris = triangulate(counts, vidx)

        # UVs: usually face-varying, so de-index into per-corner vertices.
        uv_values, uv_indices, interp = None, None, None
        primvars = UsdGeom.PrimvarsAPI(prim)
        for pv in primvars.GetPrimvars():
            if pv.GetTypeName().role == "TextureCoordinate" or pv.GetBaseName() in ("st", "st0", "UVMap"):
                uv_values = np.asarray(pv.Get(), dtype=np.float32)
                uv_indices = pv.GetIndices()
                interp = pv.GetInterpolation()
                break

        if uv_values is not None and interp == UsdGeom.Tokens.faceVarying:
            corner_uv_index = np.asarray(uv_indices, dtype=np.int64) if uv_indices else np.arange(len(vidx))
            corner_tris = triangulate(counts, np.arange(len(vidx)))
            flat_corners = corner_tris.reshape(-1)
            positions = points[tris.reshape(-1)]
            uvs = uv_values[corner_uv_index[flat_corners]]
            indices = np.arange(len(positions), dtype=np.int64)
        else:
            positions = points
            if uv_values is not None and len(uv_values) == len(points):
                uvs = uv_values
            else:
                uvs = np.zeros((len(points), 2), dtype=np.float32)
            indices = tris.reshape(-1)

        uvs = uvs.copy()
        uvs[:, 1] = 1.0 - uvs[:, 1]  # USD -> glTF texture origin

        parts.append(Part(prim.GetParent().GetName(), positions.astype(np.float32),
                          uvs.astype(np.float32), indices.astype(np.int64), _material_of(prim)))
    return parts, read_materials(stage)


def extract_textures(usdz=USDZ, out_dir="assets_raw/arena"):
    os.makedirs(out_dir, exist_ok=True)
    with zipfile.ZipFile(usdz) as zf:
        for name in zf.namelist():
            if name.lower().endswith((".jpg", ".png", ".jpeg")):
                target = os.path.join(out_dir, name)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "wb") as fh:
                    fh.write(zf.read(name))
    return out_dir
