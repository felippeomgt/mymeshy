"""Mock adapters — fully local, CPU-only, no model weights.

These exist so the entire application (jobs, mesh processing, UVs, PBR baking,
viewer, exports, MCP) works end-to-end before any multi-gigabyte model is
installed. The image-to-3D mock performs classic "silhouette inflation": it
builds an occupancy volume from the image's alpha mask, runs marching cubes,
smooths the result and projects the image colors onto the surface. The output
genuinely resembles the input image's shape — good enough for placeholder
assets and for validating the pipeline.
"""
from __future__ import annotations

import colorsys
import hashlib
import math
from typing import Optional, Sequence

import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

from ..base import (
    GenOptions,
    ImageTo3DAdapter,
    MeshResult,
    ProgressFn,
    TextToImageAdapter,
    TexturingAdapter,
)


def _ensure_mask(img: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """Return (rgb float array HxWx3 in 0..1, mask float HxW in 0..1)."""
    rgba = img.convert("RGBA")
    arr = np.asarray(rgba, dtype=np.float32) / 255.0
    rgb, alpha = arr[..., :3], arr[..., 3]
    if alpha.min() > 0.95:  # no alpha — assume light background
        lum = rgb.mean(axis=-1)
        mask = (np.abs(lum - np.median([lum[0, 0], lum[0, -1], lum[-1, 0], lum[-1, -1]])) > 0.12).astype(np.float32)
        mask = ndimage.binary_closing(mask, iterations=3).astype(np.float32)
        mask = ndimage.binary_fill_holes(mask).astype(np.float32)
    else:
        mask = (alpha > 0.5).astype(np.float32)
    if mask.sum() < 16:  # degenerate input: fall back to a centered disk
        h, w = mask.shape
        yy, xx = np.mgrid[0:h, 0:w]
        mask = (((yy - h / 2) ** 2 + (xx - w / 2) ** 2) < (min(h, w) / 3) ** 2).astype(np.float32)
    return rgb, mask


class MockImageTo3D(ImageTo3DAdapter):
    name = "mock"
    description = "Procedural silhouette inflation (no GPU, placeholder quality)"

    def probe(self) -> tuple[bool, str]:
        return True, ""

    def generate(
        self, images: Sequence[Image.Image], opts: GenOptions, progress: ProgressFn
    ) -> MeshResult:
        from skimage import measure

        img = images[0]
        progress(0.05, "Building silhouette mask")
        rgb, mask = _ensure_mask(img)

        # Work on a square grid for an isotropic volume.
        res = 128
        m = Image.fromarray((mask * 255).astype(np.uint8)).resize((res, res), Image.BILINEAR)
        mask_s = np.asarray(m, dtype=np.float32) / 255.0
        mask_b = mask_s > 0.5

        progress(0.2, "Inflating silhouette into a volume")
        dist = ndimage.distance_transform_edt(mask_b)
        if dist.max() <= 0:
            raise ValueError("Empty silhouette — cannot build a mesh from this image")
        # Inflation profile: thickness grows with distance from the contour.
        height = np.sqrt(dist / dist.max())  # 0..1

        depth = res // 2
        zz = np.linspace(-1.0, 1.0, depth, dtype=np.float32)
        # volume[y, x, z] occupied where |z| < height(y, x)
        vol = np.abs(zz[None, None, :]) < (height[:, :, None] * 0.92 + 0.02)
        vol &= mask_b[:, :, None]
        vol = ndimage.binary_closing(vol, iterations=1)

        progress(0.45, "Extracting surface (marching cubes)")
        verts, faces, _, _ = measure.marching_cubes(vol.astype(np.float32), level=0.5)
        # verts are (y, x, z) in grid units -> normalized model space, y up, image upright
        v = np.empty_like(verts)
        v[:, 0] = verts[:, 1] / res - 0.5          # x
        v[:, 1] = 0.5 - verts[:, 0] / res          # y (flip image rows)
        v[:, 2] = (verts[:, 2] / depth - 0.5) * 0.6  # z (thinner than wide)
        mesh = trimesh.Trimesh(vertices=v, faces=faces, process=True)

        progress(0.65, "Smoothing")
        trimesh.smoothing.filter_taubin(mesh, lamb=0.5, nu=-0.53, iterations=12)

        progress(0.8, "Projecting image colors")
        h, w = rgb.shape[:2]
        px = np.clip(((mesh.vertices[:, 0] + 0.5) * (w - 1)).astype(int), 0, w - 1)
        py = np.clip(((0.5 - mesh.vertices[:, 1]) * (h - 1)).astype(int), 0, h - 1)
        colors = rgb[py, px]
        # Pull colors slightly inward from the silhouette edge to avoid halo pixels.
        eroded = ndimage.grey_erosion(rgb * mask[..., None], size=(3, 3, 1))
        edge = mask[py, px] < 0.99
        colors[edge] = eroded[py[edge], px[edge]]
        mesh.visual = trimesh.visual.ColorVisuals(
            mesh, vertex_colors=(np.clip(colors, 0, 1) * 255).astype(np.uint8)
        )
        progress(1.0, "Mock mesh ready")
        return MeshResult(mesh=mesh, textured=False)


class MockTextToImage(TextToImageAdapter):
    name = "mock"
    description = "Procedural prompt-seeded reference image (no GPU)"

    def probe(self) -> tuple[bool, str]:
        return True, ""

    def generate(self, prompt: str, opts: GenOptions, progress: ProgressFn) -> Image.Image:
        progress(0.1, "Rendering procedural reference image")
        seed = opts.seed if opts.seed is not None else int(
            hashlib.sha1(prompt.encode()).hexdigest()[:8], 16
        )
        rng = np.random.default_rng(seed)
        size = 512
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        hue = rng.random()
        n_blobs = int(5 + rng.integers(0, 6))
        cx, cy = size / 2, size / 2
        for i in range(n_blobs):
            ang = rng.random() * math.tau
            dist = rng.random() * size * 0.18
            r = size * (0.12 + rng.random() * 0.16) * (1.0 - i / (n_blobs * 2))
            x, y = cx + math.cos(ang) * dist, cy + math.sin(ang) * dist + i * 6
            col = colorsys.hsv_to_rgb((hue + rng.random() * 0.15) % 1.0,
                                      0.45 + rng.random() * 0.4,
                                      0.55 + rng.random() * 0.4)
            draw.ellipse(
                [x - r, y - r, x + r, y + r],
                fill=tuple(int(c * 255) for c in col) + (255,),
            )
        img = img.filter(ImageFilter.GaussianBlur(3))
        # Re-threshold alpha after blur so the silhouette stays crisp.
        a = np.asarray(img)
        alpha = (a[..., 3] > 96).astype(np.uint8) * 255
        a = a.copy()
        a[..., 3] = alpha
        progress(1.0, "Reference image ready")
        return Image.fromarray(a)


class MockTexturing(TexturingAdapter):
    name = "mock"
    description = "Procedural prompt-seeded albedo for existing meshes (no GPU)"

    def probe(self) -> tuple[bool, str]:
        return True, ""

    def generate(
        self,
        mesh: trimesh.Trimesh,
        prompt: Optional[str],
        image: Optional[Image.Image],
        opts: GenOptions,
        progress: ProgressFn,
    ) -> MeshResult:
        progress(0.2, "Generating procedural albedo")
        size = opts.texture_size
        seed = int(hashlib.sha1((prompt or "texture").encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed if opts.seed is None else opts.seed)

        hue = rng.random()
        base = np.array(colorsys.hsv_to_rgb(hue, 0.5, 0.6))
        accent = np.array(colorsys.hsv_to_rgb((hue + 0.45) % 1.0, 0.55, 0.75))

        # Multi-octave value noise.
        noise = np.zeros((size, size), dtype=np.float32)
        for octave in range(4):
            n = rng.random((8 * 2**octave, 8 * 2**octave)).astype(np.float32)
            noise += np.asarray(
                Image.fromarray(n, mode="F").resize((size, size), Image.BILINEAR)
            ) / 2**octave
        noise = (noise - noise.min()) / (np.ptp(noise) + 1e-6)

        albedo = base[None, None] * (1 - noise[..., None]) + accent[None, None] * noise[..., None]
        if image is not None:
            # Tint with the reference image's mean color.
            ref = np.asarray(image.convert("RGB"), dtype=np.float32).reshape(-1, 3).mean(0) / 255.0
            albedo = albedo * 0.5 + ref[None, None] * 0.5
        tex = Image.fromarray((np.clip(albedo, 0, 1) * 255).astype(np.uint8))

        progress(0.9, "Applying texture")
        return MeshResult(mesh=mesh, albedo=tex, textured=False)
