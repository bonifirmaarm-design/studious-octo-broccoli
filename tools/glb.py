"""Minimal glTF 2.0 / GLB writer with support for textures, skins and animations.

Written for this project so the asset pipeline has no heavy 3D dependencies:
only numpy is required.
"""

import json
import struct

import numpy as np

# glTF component types
BYTE, UBYTE, SHORT, USHORT, UINT, FLOAT = 5120, 5121, 5122, 5123, 5125, 5126

_NP_TO_COMPONENT = {
    np.dtype("int8"): BYTE,
    np.dtype("uint8"): UBYTE,
    np.dtype("int16"): SHORT,
    np.dtype("uint16"): USHORT,
    np.dtype("uint32"): UINT,
    np.dtype("float32"): FLOAT,
}

_SHAPE_TO_TYPE = {(): "SCALAR", (1,): "SCALAR", (2,): "VEC2", (3,): "VEC3", (4,): "VEC4", (16,): "MAT4"}

ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963


class GLB:
    def __init__(self):
        self.gltf = {
            "asset": {"version": "2.0", "generator": "clash-royale-3d asset pipeline"},
            "scenes": [{"nodes": []}],
            "scene": 0,
            "nodes": [],
            "meshes": [],
            "materials": [],
            "textures": [],
            "images": [],
            "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
            "accessors": [],
            "bufferViews": [],
        }
        self._blob = bytearray()

    # ---------------------------------------------------------------- buffers

    def _append(self, data: bytes, alignment: int = 4) -> int:
        while len(self._blob) % alignment:
            self._blob.append(0)
        offset = len(self._blob)
        self._blob.extend(data)
        return offset

    def add_buffer_view(self, data: bytes, target=None) -> int:
        offset = self._append(data)
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        self.gltf["bufferViews"].append(view)
        return len(self.gltf["bufferViews"]) - 1

    def add_accessor(self, array: np.ndarray, target=None, normalized=False) -> int:
        array = np.ascontiguousarray(array)
        component = _NP_TO_COMPONENT[array.dtype]
        shape = array.shape[1:]
        type_ = _SHAPE_TO_TYPE[shape]
        count = array.shape[0]
        view = self.add_buffer_view(array.tobytes(), target)
        flat = array.reshape(count, -1)
        accessor = {
            "bufferView": view,
            "componentType": component,
            "count": count,
            "type": type_,
            "min": [float(v) for v in flat.min(axis=0)],
            "max": [float(v) for v in flat.max(axis=0)],
        }
        if normalized:
            accessor["normalized"] = True
        self.gltf["accessors"].append(accessor)
        return len(self.gltf["accessors"]) - 1

    # --------------------------------------------------------------- textures

    def add_image(self, path: str, mime: str = None) -> int:
        with open(path, "rb") as fh:
            data = fh.read()
        if mime is None:
            mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
        view = self.add_buffer_view(data)
        self.gltf["images"].append({"bufferView": view, "mimeType": mime})
        return len(self.gltf["images"]) - 1

    def add_image_bytes(self, data: bytes, mime: str = "image/jpeg") -> int:
        view = self.add_buffer_view(data)
        self.gltf["images"].append({"bufferView": view, "mimeType": mime})
        return len(self.gltf["images"]) - 1

    def add_texture(self, image: int) -> int:
        self.gltf["textures"].append({"sampler": 0, "source": image})
        return len(self.gltf["textures"]) - 1

    def add_material(self, name, base_color_texture=None, base_color=(1, 1, 1, 1),
                     metallic=0.0, roughness=0.8, double_sided=True,
                     metallic_roughness_texture=None, alpha_mode=None, emissive=None) -> int:
        pbr = {
            "baseColorFactor": list(base_color),
            "metallicFactor": metallic,
            "roughnessFactor": roughness,
        }
        if base_color_texture is not None:
            pbr["baseColorTexture"] = {"index": base_color_texture}
        if metallic_roughness_texture is not None:
            pbr["metallicRoughnessTexture"] = {"index": metallic_roughness_texture}
        material = {"name": name, "pbrMetallicRoughness": pbr, "doubleSided": double_sided}
        if alpha_mode:
            material["alphaMode"] = alpha_mode
        if emissive:
            material["emissiveFactor"] = list(emissive)
        self.gltf["materials"].append(material)
        return len(self.gltf["materials"]) - 1

    # ------------------------------------------------------------------ mesh

    def add_mesh(self, name, positions, indices, normals=None, uvs=None,
                 material=None, joints=None, weights=None) -> int:
        attributes = {"POSITION": self.add_accessor(positions.astype(np.float32), ARRAY_BUFFER)}
        if normals is not None:
            attributes["NORMAL"] = self.add_accessor(normals.astype(np.float32), ARRAY_BUFFER)
        if uvs is not None:
            attributes["TEXCOORD_0"] = self.add_accessor(uvs.astype(np.float32), ARRAY_BUFFER)
        if joints is not None:
            attributes["JOINTS_0"] = self.add_accessor(joints.astype(np.uint16), ARRAY_BUFFER)
            attributes["WEIGHTS_0"] = self.add_accessor(weights.astype(np.float32), ARRAY_BUFFER)

        index_dtype = np.uint16 if positions.shape[0] < 65536 else np.uint32
        primitive = {
            "attributes": attributes,
            "indices": self.add_accessor(indices.astype(index_dtype).reshape(-1), ELEMENT_ARRAY_BUFFER),
            "mode": 4,
        }
        if material is not None:
            primitive["material"] = material
        self.gltf["meshes"].append({"name": name, "primitives": [primitive]})
        return len(self.gltf["meshes"]) - 1

    # ------------------------------------------------------------------ nodes

    def add_node(self, name, mesh=None, translation=None, rotation=None, scale=None,
                 children=None, skin=None, root=False) -> int:
        node = {"name": name}
        if mesh is not None:
            node["mesh"] = mesh
        if skin is not None:
            node["skin"] = skin
        if translation is not None:
            node["translation"] = [float(v) for v in translation]
        if rotation is not None:
            node["rotation"] = [float(v) for v in rotation]
        if scale is not None:
            node["scale"] = [float(v) for v in scale]
        if children:
            node["children"] = list(children)
        self.gltf["nodes"].append(node)
        index = len(self.gltf["nodes"]) - 1
        if root:
            self.gltf["scenes"][0]["nodes"].append(index)
        return index

    def set_children(self, node: int, children):
        self.gltf["nodes"][node]["children"] = list(children)

    # ------------------------------------------------------------------ skins

    def add_skin(self, name, joints, inverse_bind_matrices: np.ndarray, skeleton=None) -> int:
        # glTF expects column-major 4x4 matrices, flattened.
        flat = np.ascontiguousarray(
            inverse_bind_matrices.transpose(0, 2, 1).reshape(-1, 16).astype(np.float32)
        )
        skin = {
            "name": name,
            "joints": list(joints),
            "inverseBindMatrices": self.add_accessor(flat),
        }
        if skeleton is not None:
            skin["skeleton"] = skeleton
        self.gltf.setdefault("skins", []).append(skin)
        return len(self.gltf["skins"]) - 1

    # ------------------------------------------------------------- animations

    def add_animation(self, name, channels) -> int:
        """channels: list of (node, path, times[N], values[N, k])."""
        samplers, gltf_channels = [], []
        for node, path, times, values in channels:
            sampler = {
                "input": self.add_accessor(np.asarray(times, dtype=np.float32)),
                "output": self.add_accessor(np.asarray(values, dtype=np.float32)),
                "interpolation": "LINEAR",
            }
            gltf_channels.append({"sampler": len(samplers), "target": {"node": node, "path": path}})
            samplers.append(sampler)
        self.gltf.setdefault("animations", []).append(
            {"name": name, "samplers": samplers, "channels": gltf_channels}
        )
        return len(self.gltf["animations"]) - 1

    # ------------------------------------------------------------------ write

    def save(self, path: str):
        self.gltf["buffers"] = [{"byteLength": len(self._blob)}]
        for key in ("materials", "textures", "images", "skins", "animations"):
            if key in self.gltf and not self.gltf[key]:
                del self.gltf[key]

        json_bytes = json.dumps(self.gltf, separators=(",", ":")).encode("utf-8")
        json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)
        bin_bytes = bytes(self._blob)
        bin_bytes += b"\x00" * ((4 - len(bin_bytes) % 4) % 4)

        total = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
        with open(path, "wb") as fh:
            fh.write(struct.pack("<III", 0x46546C67, 2, total))
            fh.write(struct.pack("<II", len(json_bytes), 0x4E4F534A))
            fh.write(json_bytes)
            fh.write(struct.pack("<II", len(bin_bytes), 0x004E4942))
            fh.write(bin_bytes)
        return path


# ------------------------------------------------------------------ utilities


def compute_normals(positions: np.ndarray, indices: np.ndarray) -> np.ndarray:
    """Area-weighted smooth vertex normals."""
    tris = indices.reshape(-1, 3)
    p0, p1, p2 = positions[tris[:, 0]], positions[tris[:, 1]], positions[tris[:, 2]]
    face = np.cross(p1 - p0, p2 - p0)
    normals = np.zeros_like(positions, dtype=np.float64)
    for k in range(3):
        np.add.at(normals, tris[:, k], face)
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    length[length == 0] = 1.0
    return (normals / length).astype(np.float32)


def trs_matrix(translation=(0, 0, 0), rotation=(0, 0, 0, 1), scale=(1, 1, 1)) -> np.ndarray:
    x, y, z, w = rotation
    rot = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    matrix = np.eye(4)
    matrix[:3, :3] = rot * np.asarray(scale)
    matrix[:3, 3] = translation
    return matrix


def quat_from_euler(x=0.0, y=0.0, z=0.0) -> np.ndarray:
    """Intrinsic XYZ euler angles (radians) to quaternion (x, y, z, w)."""
    cx, sx = np.cos(x / 2), np.sin(x / 2)
    cy, sy = np.cos(y / 2), np.sin(y / 2)
    cz, sz = np.cos(z / 2), np.sin(z / 2)
    return np.array([
        sx * cy * cz + cx * sy * sz,
        cx * sy * cz - sx * cy * sz,
        cx * cy * sz + sx * sy * cz,
        cx * cy * cz - sx * sy * sz,
    ])
