"""PBR map derivation.

Given a baked albedo (+ optionally geometry AO), derive the remaining PBR
maps locally with classic image-processing techniques — the same approach
used by texture tools like Materialize:

* normal     — height-from-luminance + Sobel gradients
* roughness  — inverse-brightness/saturation heuristic + high-frequency detail
* metallic   — conservative default (0) with a heuristic for grey/saturated-dark areas
* AO         — geometry-derived (voxel ray-march, baked per-vertex) multiplied
               with albedo cavity detail
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage


def _luminance(albedo: np.ndarray) -> np.ndarray:
    return albedo @ np.array([0.2126, 0.7152, 0.0722])


def normal_from_albedo(albedo_img: Image.Image, strength: float = 2.0) -> Image.Image:
    """Tangent-space normal map from albedo luminance treated as a height field."""
    a = np.asarray(albedo_img.convert("RGB"), dtype=np.float64) / 255.0
    height = ndimage.gaussian_filter(_luminance(a), sigma=1.2)

    gx = ndimage.sobel(height, axis=1) * strength
    gy = ndimage.sobel(height, axis=0) * strength
    nz = np.ones_like(height)
    n = np.stack([-gx, gy, nz], axis=-1)  # OpenGL convention (+Y up), matches glTF
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    rgb = ((n * 0.5 + 0.5) * 255).astype(np.uint8)
    return Image.fromarray(rgb)


def roughness_from_albedo(albedo_img: Image.Image) -> Image.Image:
    """Heuristic roughness: darker, low-saturation surfaces lean rough; add
    high-frequency luminance detail so the map is not flat."""
    a = np.asarray(albedo_img.convert("RGB"), dtype=np.float64) / 255.0
    lum = _luminance(a)
    sat = a.max(-1) - a.min(-1)

    base = np.clip(0.85 - lum * 0.35 - sat * 0.25, 0.15, 0.95)
    detail = lum - ndimage.gaussian_filter(lum, sigma=3.0)
    rough = np.clip(base + detail * 0.6, 0.05, 1.0)
    return Image.fromarray((rough * 255).astype(np.uint8), mode="L")


def metallic_from_albedo(albedo_img: Image.Image) -> Image.Image:
    """Conservative metallic estimate: near-neutral mid/dark pixels with low
    saturation get a small metallic push; everything else is dielectric."""
    a = np.asarray(albedo_img.convert("RGB"), dtype=np.float64) / 255.0
    lum = _luminance(a)
    sat = a.max(-1) - a.min(-1)
    metal = np.clip((0.18 - sat) * 3.0, 0, 1) * np.clip((lum - 0.25) * 2.0, 0, 1) * 0.6
    metal = ndimage.gaussian_filter(metal, sigma=2.0)
    # Threshold softly: mostly 0 unless the heuristic is confident.
    metal = np.where(metal > 0.25, metal, 0.0)
    return Image.fromarray((np.clip(metal, 0, 1) * 255).astype(np.uint8), mode="L")


def ao_map(albedo_img: Image.Image, geometry_ao: Image.Image | None) -> Image.Image:
    """Combine geometry AO (baked per-vertex, rasterized to the atlas) with
    albedo cavity detail."""
    a = np.asarray(albedo_img.convert("RGB"), dtype=np.float64) / 255.0
    lum = _luminance(a)
    cavity = np.clip(1.0 - (ndimage.gaussian_filter(lum, 4.0) - lum) * 1.5, 0.0, 1.0)
    out = np.clip(cavity * 0.4 + 0.6, 0, 1)
    if geometry_ao is not None:
        g = np.asarray(geometry_ao.convert("L"), dtype=np.float64) / 255.0
        if g.shape != out.shape:
            g = np.asarray(
                geometry_ao.convert("L").resize(out.shape[::-1], Image.BILINEAR),
                dtype=np.float64,
            ) / 255.0
        out = out * (g * 0.7 + 0.3)
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8), mode="L")


def pack_orm(ao: Image.Image, roughness: Image.Image, metallic: Image.Image,
             size: int) -> Image.Image:
    """glTF-style packed texture: R=occlusion, G=roughness, B=metallic. One
    image can then serve as both occlusionTexture and metallicRoughnessTexture."""
    r = np.asarray(ao.convert("L").resize((size, size), Image.BILINEAR))
    g = np.asarray(roughness.convert("L").resize((size, size), Image.BILINEAR))
    b = np.asarray(metallic.convert("L").resize((size, size), Image.BILINEAR))
    return Image.fromarray(np.stack([r, g, b], axis=-1))


def smooth_seams(img: Image.Image) -> Image.Image:
    """Tiny blur pass used on derived maps to soften rasterization stairsteps."""
    return img.filter(ImageFilter.GaussianBlur(0.6))
