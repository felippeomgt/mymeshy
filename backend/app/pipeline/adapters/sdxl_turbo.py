"""SDXL-Turbo text-to-image adapter (stage 1 of text-to-3D).

Generates a single, centered, white-background concept image suitable for
image-to-3D reconstruction. ~7 GB VRAM in fp16; runs in seconds on an RTX 3060.
"""
from __future__ import annotations

import importlib.util

from PIL import Image

from ..base import (
    GenOptions,
    ProgressFn,
    TextToImageAdapter,
    _torch_cuda_probe,
    apply_vram_budget,
    free_cuda_memory,
    low_vram,
)

PROMPT_TEMPLATE = (
    "{prompt}, 3d asset, single object, full object in frame, centered, "
    "plain solid white background, soft studio lighting, no shadows on background, "
    "high detail, video game asset"
)
NEGATIVE = "cropped, cut off, multiple objects, scene, text, watermark, frame, border"


class SdxlTurboTextToImage(TextToImageAdapter):
    name = "sdxl_turbo"
    description = "Stability AI SDXL-Turbo (1-4 step diffusion, ~7GB VRAM)"

    def __init__(self) -> None:
        self._pipe = None

    def probe(self) -> tuple[bool, str]:
        ok, reason = _torch_cuda_probe()
        if not ok:
            return False, reason
        if importlib.util.find_spec("diffusers") is None:
            return False, "diffusers not installed (see requirements-ml.txt)"
        return True, ""

    def _load(self, progress: ProgressFn):
        if self._pipe is None:
            import torch
            from diffusers import AutoPipelineForText2Image

            apply_vram_budget()
            progress(0.05, "Loading SDXL-Turbo (first run downloads ~7GB)")
            self._pipe = AutoPipelineForText2Image.from_pretrained(
                "stabilityai/sdxl-turbo", torch_dtype=torch.float16, variant="fp16"
            )
            if low_vram():
                # Streams weights layer-by-layer through the GPU: <3GB VRAM,
                # noticeably slower — exactly the low-budget trade-off.
                self._pipe.enable_sequential_cpu_offload()
                self._pipe.enable_attention_slicing()
            else:
                self._pipe.enable_model_cpu_offload()
        return self._pipe

    def generate(self, prompt: str, opts: GenOptions, progress: ProgressFn) -> Image.Image:
        import torch

        pipe = self._load(progress)
        generator = (
            torch.Generator("cuda").manual_seed(opts.seed) if opts.seed is not None else None
        )
        size = 768 if low_vram() else 1024
        progress(0.3, "Generating reference image")
        image = pipe(
            prompt=PROMPT_TEMPLATE.format(prompt=prompt),
            negative_prompt=NEGATIVE,
            num_inference_steps=4,
            guidance_scale=0.0,
            width=size,
            height=size,
            generator=generator,
        ).images[0]
        progress(1.0, "Reference image ready")
        return image

    def unload(self) -> None:
        if self._pipe is not None:
            self._pipe = None
            free_cuda_memory()
