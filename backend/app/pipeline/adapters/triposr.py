"""Stability AI TripoSR image-to-3D adapter.

The fast option: a single feed-forward pass (~seconds on an RTX 3060, ~6GB
VRAM). Lower fidelity than TRELLIS/Hunyuan but great for quick blockout
assets. Install from the TripoSR repo (exposes the ``tsr`` package).
"""
from __future__ import annotations

import importlib.util
from typing import Sequence

import numpy as np
import trimesh
from PIL import Image

from ..base import (
    GenOptions,
    ImageTo3DAdapter,
    MeshResult,
    ProgressFn,
    _torch_cuda_probe,
    apply_vram_budget,
    free_cuda_memory,
    low_vram,
)


def _install_torchmcubes_shim() -> None:
    """TripoSR depends on torchmcubes, a CUDA extension that needs the full
    CUDA toolkit to build on Windows. When it isn't installed, register a
    drop-in CPU implementation backed by scikit-image so no compiler is
    needed. Mimics torchmcubes' (z, y, x) vertex order, which TripoSR
    reorders right after the call (isosurface.py)."""
    import sys

    if importlib.util.find_spec("torchmcubes") is not None:
        return
    import types

    import numpy as np
    import torch
    from skimage import measure

    def marching_cubes(vol, thresh=0.0):
        v = vol.detach().cpu().numpy()
        verts, faces, _normals, _vals = measure.marching_cubes(v, level=float(thresh))
        verts = np.ascontiguousarray(verts[:, ::-1])  # index order -> (z, y, x)
        return (
            torch.from_numpy(verts.astype(np.float32)),
            torch.from_numpy(faces.astype(np.int64)),
        )

    shim = types.ModuleType("torchmcubes")
    shim.marching_cubes = marching_cubes
    sys.modules["torchmcubes"] = shim


class TripoSRImageTo3D(ImageTo3DAdapter):
    name = "triposr"
    description = "Stability AI TripoSR (fastest, ~6GB VRAM, blockout quality)"

    def __init__(self) -> None:
        self._model = None

    def probe(self) -> tuple[bool, str]:
        ok, reason = _torch_cuda_probe()
        if not ok:
            return False, reason
        if importlib.util.find_spec("tsr") is None:
            return False, "TripoSR repo not installed (see README: Installing real models)"
        return True, ""

    def _load(self, progress: ProgressFn):
        if self._model is None:
            _install_torchmcubes_shim()
            from tsr.system import TSR

            apply_vram_budget()
            progress(0.05, "Loading TripoSR (first run downloads ~2GB)")
            model = TSR.from_pretrained(
                "stabilityai/TripoSR", config_name="config.yaml", weight_name="model.ckpt"
            )
            # Smaller chunks trade speed for a lower VRAM peak.
            model.renderer.set_chunk_size(2048 if low_vram() else 8192)
            model.to("cuda")
            self._model = model
        return self._model

    def generate(
        self, images: Sequence[Image.Image], opts: GenOptions, progress: ProgressFn
    ) -> MeshResult:
        import torch

        model = self._load(progress)
        image = images[0].convert("RGB")

        progress(0.3, "Running TripoSR reconstruction")
        with torch.no_grad():
            scene_codes = model([image], device="cuda")
            progress(0.6, "Extracting mesh")
            meshes = model.extract_mesh(
                scene_codes, has_vertex_color=True,
                resolution=192 if low_vram() else 256,
            )
        m = meshes[0]
        mesh = trimesh.Trimesh(
            vertices=np.asarray(m.vertices),
            faces=np.asarray(m.faces),
            vertex_colors=(np.clip(np.asarray(m.visual.vertex_colors if hasattr(m, "visual") else m.vertex_colors), 0, 255)).astype(np.uint8)
            if hasattr(m, "visual") or hasattr(m, "vertex_colors")
            else None,
            process=True,
        )
        # TripoSR outputs z-up; rotate to y-up.
        mesh.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))
        progress(1.0, "TripoSR mesh ready")
        return MeshResult(mesh=mesh, textured=False)

    def unload(self) -> None:
        if self._model is not None:
            self._model = None
            free_cuda_memory()
