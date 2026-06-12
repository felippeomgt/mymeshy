"""Adapter interfaces for the generation pipeline.

Every AI model is wrapped in an adapter with a uniform interface so models can
be swapped or upgraded independently:

* ``TextToImageAdapter``  — prompt -> reference image (stage 1 of text-to-3D)
* ``ImageTo3DAdapter``    — image(s) -> raw 3D mesh (possibly textured)
* ``TexturingAdapter``    — mesh + prompt/image -> textured mesh

Adapters declare availability via :meth:`probe` so the registry can fall back
gracefully (e.g. to the mock pipeline when no GPU stack is installed) and the
UI can show what is installed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

import trimesh
from PIL import Image

# progress(fraction_0_to_1, message)
ProgressFn = Callable[[float, str], None]


@dataclass
class GenOptions:
    adapter: Optional[str] = None
    target_polycount: int = 30000
    texture_size: int = 1024
    generate_pbr: bool = True
    seed: Optional[int] = None
    # Skip decimation when the raw mesh is already below target.
    decimate: bool = True

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "GenOptions":
        d = d or {}
        known = {f for f in cls.__dataclass_fields__}  # noqa: F841
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__ and v is not None})


@dataclass
class MeshResult:
    """Raw output of an image-to-3D adapter, before post-processing."""
    mesh: trimesh.Trimesh
    # Albedo texture if the model produced one (mesh.visual should reference it
    # too, but keeping an explicit handle survives processing steps).
    albedo: Optional[Image.Image] = None
    # True if mesh.visual has usable UVs + texture already.
    textured: bool = False
    extras: dict = field(default_factory=dict)


class Adapter:
    name: str = "base"
    description: str = ""

    def probe(self) -> tuple[bool, str]:
        """Return (available, reason). Must be cheap — no model loading."""
        raise NotImplementedError

    def unload(self) -> None:
        """Free GPU memory if the adapter keeps a loaded model."""


class TextToImageAdapter(Adapter):
    def generate(self, prompt: str, opts: GenOptions, progress: ProgressFn) -> Image.Image:
        raise NotImplementedError


class ImageTo3DAdapter(Adapter):
    def generate(
        self, images: Sequence[Image.Image], opts: GenOptions, progress: ProgressFn
    ) -> MeshResult:
        raise NotImplementedError


class TexturingAdapter(Adapter):
    def generate(
        self,
        mesh: trimesh.Trimesh,
        prompt: Optional[str],
        image: Optional[Image.Image],
        opts: GenOptions,
        progress: ProgressFn,
    ) -> MeshResult:
        raise NotImplementedError


def _torch_cuda_probe() -> tuple[bool, str]:
    """Shared helper: is a CUDA-enabled torch importable?"""
    try:
        import torch  # noqa: F401
    except ImportError:
        return False, "PyTorch not installed (see requirements-ml.txt)"
    import torch
    if not torch.cuda.is_available():
        return False, "PyTorch installed but CUDA is not available"
    return True, ""


# --------------------------------------------------------------------------
# VRAM budget
# --------------------------------------------------------------------------

def vram_budget_gb() -> float:
    """Configured GPU memory budget (0 = unlimited)."""
    from ..config import get_settings

    return float(get_settings().vram_budget_gb or 0)


def low_vram() -> bool:
    """True when a budget of 8GB or less is configured — adapters switch to
    offloading/chunking and the runner unloads models between stages."""
    b = vram_budget_gb()
    return 0 < b <= 8


# CUDA context + cuDNN workspace etc. live outside torch's allocator but
# still count against real GPU memory — reserve room for them in the budget.
_CUDA_OVERHEAD_GB = 0.9


def apply_vram_budget() -> None:
    """Hard-cap torch CUDA allocations so total process usage (allocator +
    CUDA context overhead) stays within the configured budget. Called by
    adapters right before loading a model. Safe to call repeatedly."""
    budget = vram_budget_gb()
    if budget <= 0:
        return
    import os

    # Must be set before CUDA init; reduces fragmentation so the capped
    # allocator can actually use its full budget.
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    import torch

    if not torch.cuda.is_available():
        return
    total_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
    allocator_budget = max(budget - _CUDA_OVERHEAD_GB, 1.0)
    fraction = min(allocator_budget / total_gb, 1.0)
    torch.cuda.set_per_process_memory_fraction(fraction, 0)


def free_cuda_memory() -> None:
    import gc

    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except ImportError:
        pass
