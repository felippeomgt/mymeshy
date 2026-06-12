"""Tencent Hunyuan3D-2 adapters: shape generation + texture painting.

Recommended primary on 12GB cards: the *2mini* shape model runs in ~5-6GB and
the paint pipeline produces genuinely good textures for arbitrary meshes —
which also powers the "texture an existing mesh" feature.

Install the ``hy3dgen`` package from the Hunyuan3D-2 repo (see README).
"""
from __future__ import annotations

import importlib.util
import os
from typing import Optional, Sequence

import trimesh
from PIL import Image

from ..base import (
    GenOptions,
    ImageTo3DAdapter,
    MeshResult,
    ProgressFn,
    TexturingAdapter,
    _torch_cuda_probe,
    apply_vram_budget,
    free_cuda_memory,
    low_vram,
)

# Overridable for the bigger model: tencent/Hunyuan3D-2
SHAPE_MODEL = os.environ.get("MYMESHY_HUNYUAN_SHAPE_MODEL", "tencent/Hunyuan3D-2mini")
PAINT_MODEL = os.environ.get("MYMESHY_HUNYUAN_PAINT_MODEL", "tencent/Hunyuan3D-2")

# Each HF repo nests its DiT weights in a differently named subfolder.
_SHAPE_SUBFOLDERS = {
    "Hunyuan3D-2": "hunyuan3d-dit-v2-0",
    "Hunyuan3D-2mini": "hunyuan3d-dit-v2-mini",
    "Hunyuan3D-2mv": "hunyuan3d-dit-v2-mv",
}
SHAPE_SUBFOLDER = os.environ.get(
    "MYMESHY_HUNYUAN_SHAPE_SUBFOLDER",
    _SHAPE_SUBFOLDERS.get(SHAPE_MODEL.split("/")[-1], "hunyuan3d-dit-v2-0"),
)


def _hy3dgen_probe() -> tuple[bool, str]:
    ok, reason = _torch_cuda_probe()
    if not ok:
        return False, reason
    if importlib.util.find_spec("hy3dgen") is None:
        return False, "hy3dgen not installed (see README: Installing real models)"
    return True, ""


def _paint_available() -> tuple[bool, str]:
    """The paint pipeline needs the compiled custom_rasterizer CUDA extension
    (requires the CUDA toolkit + MSVC to build) and roughly 10-12GB of VRAM."""
    if importlib.util.find_spec("custom_rasterizer") is None:
        return False, "custom_rasterizer not compiled (needs CUDA toolkit; see README)"
    if low_vram():
        return False, "paint pipeline does not fit the configured VRAM budget (needs ~10-12GB)"
    return True, ""


class Hunyuan3DImageTo3D(ImageTo3DAdapter):
    name = "hunyuan3d"
    description = "Tencent Hunyuan3D-2 (shape + paint, ~6-12GB VRAM, Windows-friendly)"

    def __init__(self) -> None:
        self._shape = None
        self._paint = None

    def probe(self) -> tuple[bool, str]:
        return _hy3dgen_probe()

    def _load_shape(self, progress: ProgressFn):
        if self._shape is None:
            from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

            apply_vram_budget()
            progress(0.02, f"Loading Hunyuan3D shape model ({SHAPE_MODEL})")
            self._shape = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
                SHAPE_MODEL, subfolder=SHAPE_SUBFOLDER
            )
            if low_vram():
                try:
                    self._shape.enable_flashvdm(mc_algo="mc")
                except Exception:
                    pass
        return self._shape

    def _load_paint(self, progress: ProgressFn):
        if self._paint is None:
            from hy3dgen.texgen import Hunyuan3DPaintPipeline

            apply_vram_budget()
            progress(0.5, f"Loading Hunyuan3D paint model ({PAINT_MODEL})")
            self._paint = Hunyuan3DPaintPipeline.from_pretrained(PAINT_MODEL)
        return self._paint

    def _unload_shape(self) -> None:
        self._shape = None
        free_cuda_memory()

    def generate(
        self, images: Sequence[Image.Image], opts: GenOptions, progress: ProgressFn
    ) -> MeshResult:
        import torch

        image = images[0].convert("RGBA")
        shape = self._load_shape(progress)
        progress(0.1, "Generating shape (flow-matching diffusion)")
        generator = (
            torch.Generator().manual_seed(opts.seed) if opts.seed is not None else None
        )
        kwargs = {}
        if low_vram():
            # Coarser decode volume and smaller query batches: the biggest
            # VRAM lever in the shape VAE, modest quality cost.
            kwargs = {"octree_resolution": 256, "num_chunks": 4000}
        mesh = shape(image=image, generator=generator, **kwargs)[0]
        if not isinstance(mesh, trimesh.Trimesh):
            mesh = trimesh.Trimesh(vertices=mesh.vertices, faces=mesh.faces, process=True)

        # Hunyuan's own cleanup helpers before painting.
        try:
            from hy3dgen.shapegen import FaceReducer, FloaterRemover, DegenerateFaceRemover

            progress(0.4, "Hunyuan mesh cleanup")
            mesh = FloaterRemover()(mesh)
            mesh = DegenerateFaceRemover()(mesh)
            mesh = FaceReducer()(mesh, max_facenum=max(opts.target_polycount, 40000))
        except Exception:
            pass  # cleanup is best-effort; our own pipeline cleans up too

        paint_ok, paint_reason = _paint_available()
        if not paint_ok:
            # Geometry-only result: the runner projects the reference image
            # onto the mesh as fallback albedo.
            progress(1.0, f"Shape ready (paint skipped: {paint_reason})")
            return MeshResult(mesh=mesh, textured=False)

        if low_vram():
            # Shape and paint models never share the GPU within the budget.
            self._unload_shape()

        paint = self._load_paint(progress)
        progress(0.6, "Painting texture from reference image")
        mesh = paint(mesh, image=image)

        albedo = None
        material = getattr(getattr(mesh, "visual", None), "material", None)
        if material is not None:
            albedo = getattr(material, "baseColorTexture", None) or getattr(material, "image", None)
        progress(1.0, "Hunyuan3D mesh ready")
        return MeshResult(mesh=mesh, albedo=albedo, textured=albedo is not None)

    def unload(self) -> None:
        self._shape = None
        self._paint = None
        free_cuda_memory()


class HunyuanPaintTexturing(TexturingAdapter):
    name = "hunyuan_paint"
    description = "Hunyuan3D-2 paint pipeline for texturing existing meshes"

    def __init__(self) -> None:
        self._paint = None
        self._t2i = None

    def probe(self) -> tuple[bool, str]:
        ok, reason = _hy3dgen_probe()
        if not ok:
            return False, reason
        return _paint_available()

    def generate(
        self,
        mesh: trimesh.Trimesh,
        prompt: Optional[str],
        image: Optional[Image.Image],
        opts: GenOptions,
        progress: ProgressFn,
    ) -> MeshResult:
        if image is None:
            if not prompt:
                raise ValueError("Texturing needs a prompt or a reference image")
            # Hunyuan paint is image-conditioned: synthesize the reference first.
            from .sdxl_turbo import SdxlTurboTextToImage

            if self._t2i is None:
                self._t2i = SdxlTurboTextToImage()
            ok, reason = self._t2i.probe()
            if not ok:
                raise RuntimeError(f"Text-conditioned texturing needs SDXL-Turbo: {reason}")
            image = self._t2i.generate(prompt, opts, lambda p, m: progress(p * 0.3, m))
            if low_vram():
                self._t2i.unload()

        if self._paint is None:
            from hy3dgen.texgen import Hunyuan3DPaintPipeline

            apply_vram_budget()
            progress(0.35, f"Loading Hunyuan3D paint model ({PAINT_MODEL})")
            self._paint = Hunyuan3DPaintPipeline.from_pretrained(PAINT_MODEL)

        progress(0.5, "Painting texture")
        painted = self._paint(mesh, image=image.convert("RGBA"))
        albedo = None
        material = getattr(getattr(painted, "visual", None), "material", None)
        if material is not None:
            albedo = getattr(material, "baseColorTexture", None) or getattr(material, "image", None)
        progress(1.0, "Texture ready")
        return MeshResult(mesh=painted, albedo=albedo, textured=albedo is not None)

    def unload(self) -> None:
        self._paint = None
        self._t2i = None
        free_cuda_memory()
