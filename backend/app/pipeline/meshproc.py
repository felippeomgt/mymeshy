"""Mesh post-processing: cleanup, decimation, UV unwrapping, texture baking
and geometry-derived ambient occlusion.

Works on any ``trimesh.Trimesh`` regardless of which adapter produced it, so
every generated asset comes out clean, UV-mapped and game-ready.
"""
from __future__ import annotations

import numpy as np
import trimesh
from PIL import Image

from .base import ProgressFn


def _noop(_p: float, _m: str) -> None:
    pass


# --------------------------------------------------------------------------
# Cleanup / decimation
# --------------------------------------------------------------------------

def cleanup(mesh: trimesh.Trimesh, keep_components_ratio: float = 0.02) -> trimesh.Trimesh:
    """Merge vertices, drop degenerate faces and dust components, fix winding."""
    mesh = mesh.copy()
    mesh.merge_vertices()
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.update_faces(mesh.unique_faces())
    mesh.remove_unreferenced_vertices()

    # Drop floating dust: keep components with a meaningful share of faces.
    components = mesh.split(only_watertight=False)
    if len(components) > 1:
        threshold = max(int(len(mesh.faces) * keep_components_ratio), 16)
        kept = [c for c in components if len(c.faces) >= threshold]
        if kept:
            mesh = trimesh.util.concatenate(kept)

    trimesh.repair.fix_normals(mesh)
    return mesh


def normalize_scale(mesh: trimesh.Trimesh, target: float = 1.0) -> trimesh.Trimesh:
    """Center on origin (sit on y=0 ground plane) and fit the largest extent to ``target``."""
    mesh = mesh.copy()
    extents = mesh.bounding_box.extents
    scale = target / max(extents.max(), 1e-9)
    mesh.apply_scale(scale)
    lo, hi = mesh.bounds
    mesh.apply_translation([-(lo[0] + hi[0]) / 2, -lo[1], -(lo[2] + hi[2]) / 2])
    return mesh


def decimate(mesh: trimesh.Trimesh, target_faces: int) -> trimesh.Trimesh:
    """Quadric decimation via fast-simplification; preserves vertex colors by
    re-sampling them from the original mesh afterwards."""
    if len(mesh.faces) <= target_faces:
        return mesh
    import fast_simplification

    v, f = fast_simplification.simplify(
        mesh.vertices.astype(np.float32),
        mesh.faces.astype(np.int64),
        target_count=target_faces,
    )
    out = trimesh.Trimesh(vertices=v, faces=f, process=True)

    if _has_vertex_colors(mesh):
        out.visual = trimesh.visual.ColorVisuals(
            out, vertex_colors=_sample_vertex_colors(mesh, out.vertices)
        )
    return out


def _has_vertex_colors(mesh: trimesh.Trimesh) -> bool:
    visual = getattr(mesh, "visual", None)
    return (
        isinstance(visual, trimesh.visual.ColorVisuals)
        and visual.kind == "vertex"
    )


def _sample_vertex_colors(source: trimesh.Trimesh, points: np.ndarray) -> np.ndarray:
    """Closest-point color transfer from ``source`` (with vertex colors)."""
    closest, _dist, tri_id = trimesh.proximity.closest_point(source, points)
    tris = source.faces[tri_id]
    bary = trimesh.triangles.points_to_barycentric(source.vertices[tris], closest)
    colors = source.visual.vertex_colors[tris][..., :4].astype(np.float64)  # (n,3,4)
    return np.clip((colors * bary[..., None]).sum(axis=1), 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------
# UV unwrap (xatlas)
# --------------------------------------------------------------------------

def unwrap(mesh: trimesh.Trimesh) -> tuple[trimesh.Trimesh, np.ndarray]:
    """Generate a UV atlas with xatlas. Returns (new_mesh, uv) where the new
    mesh has re-indexed vertices (xatlas splits verts along seams) and any
    source vertex colors carried over."""
    import xatlas

    vmapping, indices, uvs = xatlas.parametrize(
        mesh.vertices.astype(np.float32), mesh.faces.astype(np.uint32)
    )
    out = trimesh.Trimesh(
        vertices=mesh.vertices[vmapping], faces=indices.astype(np.int64), process=False
    )
    if _has_vertex_colors(mesh):
        out.visual = trimesh.visual.ColorVisuals(
            out, vertex_colors=mesh.visual.vertex_colors[vmapping]
        )
    return out, uvs.astype(np.float64)


# --------------------------------------------------------------------------
# Rasterization helpers (UV-space baking)
# --------------------------------------------------------------------------

def _rasterize_attribute(
    uvs: np.ndarray,
    faces: np.ndarray,
    vertex_attr: np.ndarray,
    size: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Bake a per-vertex attribute (N, C) into a (size, size, C) image by
    scanline-rasterizing each UV triangle with barycentric interpolation.
    Returns (image float array, coverage mask)."""
    channels = vertex_attr.shape[1]
    img = np.zeros((size, size, channels), dtype=np.float64)
    covered = np.zeros((size, size), dtype=bool)

    # UV -> pixel space; flip v so row 0 is the top of the image.
    px = uvs[:, 0] * (size - 1)
    py = (1.0 - uvs[:, 1]) * (size - 1)

    for face in faces:
        x, y = px[face], py[face]
        x0, x1 = int(np.floor(x.min())), int(np.ceil(x.max()))
        y0, y1 = int(np.floor(y.min())), int(np.ceil(y.max()))
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, size - 1), min(y1, size - 1)
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        gx, gy = gx.ravel().astype(np.float64), gy.ravel().astype(np.float64)

        # Barycentric coordinates of each pixel center in this triangle.
        d = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
        if abs(d) < 1e-12:
            continue
        w0 = ((y[1] - y[2]) * (gx - x[2]) + (x[2] - x[1]) * (gy - y[2])) / d
        w1 = ((y[2] - y[0]) * (gx - x[2]) + (x[0] - x[2]) * (gy - y[2])) / d
        w2 = 1.0 - w0 - w1
        eps = -1e-4
        inside = (w0 >= eps) & (w1 >= eps) & (w2 >= eps)
        if not inside.any():
            continue
        ix = gx[inside].astype(int)
        iy = gy[inside].astype(int)
        w = np.stack([w0[inside], w1[inside], w2[inside]], axis=1)
        img[iy, ix] = w @ vertex_attr[face]
        covered[iy, ix] = True
    return img, covered


def _dilate(img: np.ndarray, covered: np.ndarray, iterations: int = 6) -> np.ndarray:
    """Edge-pad UV islands so bilinear sampling at seams doesn't pick up
    background texels. Morphological dilation of covered texels into empty ones."""
    from scipy import ndimage

    out = img.copy()
    mask = covered.copy()
    for _ in range(iterations):
        grown = ndimage.binary_dilation(mask)
        ring = grown & ~mask
        if not ring.any():
            break
        # Average of covered neighbours via convolution.
        kernel = np.ones((3, 3))
        for c in range(out.shape[2]):
            s = ndimage.convolve(out[..., c] * mask, kernel, mode="constant")
            n = ndimage.convolve(mask.astype(np.float64), kernel, mode="constant")
            out[..., c][ring] = (s[ring] / np.maximum(n[ring], 1e-9))
        mask = grown
    return out


def bake_vertex_colors(
    mesh: trimesh.Trimesh, uvs: np.ndarray, size: int, progress: ProgressFn = _noop
) -> Image.Image:
    """Bake per-vertex colors into an albedo texture on the UV atlas."""
    progress(0.0, "Baking albedo from vertex colors")
    if _has_vertex_colors(mesh):
        colors = mesh.visual.vertex_colors[:, :3].astype(np.float64) / 255.0
    else:
        colors = np.full((len(mesh.vertices), 3), 0.8)
    img, covered = _rasterize_attribute(uvs, mesh.faces, colors, size)
    img = _dilate(img, covered)
    return Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))


def bake_texture_to_atlas(
    source: trimesh.Trimesh,
    target: trimesh.Trimesh,
    target_uvs: np.ndarray,
    size: int,
    progress: ProgressFn = _noop,
) -> Image.Image:
    """Re-bake an existing texture from ``source`` (TextureVisuals with UVs)
    onto the new UV atlas of ``target`` via closest-point transfer.

    Used when an adapter ships its own texture but we re-unwrapped the mesh
    (e.g. after decimation)."""
    progress(0.0, "Transferring source texture to new UV atlas")
    sv = source.visual
    tex = np.asarray(sv.material.baseColorTexture.convert("RGB"), dtype=np.float64) / 255.0
    th, tw = tex.shape[:2]

    closest, _d, tri_id = trimesh.proximity.closest_point(source, target.vertices)
    tris = source.faces[tri_id]
    bary = trimesh.triangles.points_to_barycentric(source.vertices[tris], closest)
    uv = (np.asarray(sv.uv)[tris] * bary[..., None]).sum(axis=1)
    ix = np.clip((uv[:, 0] % 1.0) * (tw - 1), 0, tw - 1).astype(int)
    iy = np.clip((1.0 - uv[:, 1] % 1.0) * (th - 1), 0, th - 1).astype(int)
    vertex_colors = tex[iy, ix]

    img, covered = _rasterize_attribute(target_uvs, target.faces, vertex_colors, size)
    img = _dilate(img, covered)
    return Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))


# --------------------------------------------------------------------------
# Reference-image projection texturing
# --------------------------------------------------------------------------

def project_image_colors(mesh: trimesh.Trimesh, image: "Image.Image") -> trimesh.Trimesh:
    """Color vertices by projecting the (front-view) reference image along -Z.

    Fallback albedo for adapters that produce geometry without appearance
    (e.g. Hunyuan3D shape-only when the paint pipeline isn't available):
    every vertex samples the image at its normalized (x, y); back faces reuse
    the mirrored front, and colors near the silhouette are pulled inward to
    avoid background bleed. Assumes the mesh faces the reference view, which
    image-to-3D models guarantee."""
    from scipy import ndimage

    rgba = image.convert("RGBA")
    arr = np.asarray(rgba, dtype=np.float64) / 255.0
    rgb, alpha = arr[..., :3], arr[..., 3]
    if alpha.min() < 0.95:  # pull edge colors inward where alpha masks the subject
        filled = rgb * (alpha[..., None] > 0.5)
        for _ in range(8):
            grown = ndimage.grey_dilation(filled, size=(3, 3, 1))
            empty = (alpha < 0.5)
            filled[empty] = grown[empty]
        rgb = filled

    h, w = rgb.shape[:2]
    lo, hi = mesh.bounds
    span = np.maximum(hi - lo, 1e-9)
    u = (mesh.vertices[:, 0] - lo[0]) / span[0]
    v = (mesh.vertices[:, 1] - lo[1]) / span[1]
    px = np.clip(u * (w - 1), 0, w - 1).astype(int)
    py = np.clip((1.0 - v) * (h - 1), 0, h - 1).astype(int)
    colors = rgb[py, px]

    # Slightly darken faces pointing away from the projection to fake shading
    # variation instead of a perfect front/back mirror.
    facing = mesh.vertex_normals[:, 2]
    colors *= (0.82 + 0.18 * np.clip(facing, 0, 1))[:, None]

    out = mesh.copy()
    out.visual = trimesh.visual.ColorVisuals(
        out, vertex_colors=(np.clip(colors, 0, 1) * 255).astype(np.uint8)
    )
    return out


# --------------------------------------------------------------------------
# Ambient occlusion (voxel-based, fast and dependency-free)
# --------------------------------------------------------------------------

def vertex_ao(mesh: trimesh.Trimesh, resolution: int = 96, n_dirs: int = 20,
              steps: int = 12, progress: ProgressFn = _noop) -> np.ndarray:
    """Approximate per-vertex AO by marching rays through a voxel occupancy
    grid. Returns values in 0..1 (1 = fully open)."""
    progress(0.0, "Voxelizing for ambient occlusion")
    lo, hi = mesh.bounds
    span = (hi - lo).max() + 1e-9
    pitch = span / resolution
    try:
        vox = mesh.voxelized(pitch)
        occ = vox.matrix
        origin = vox.transform[:3, 3]
    except Exception:
        return np.ones(len(mesh.vertices))

    # Fibonacci hemisphere-ish direction set over the full sphere, biased up.
    i = np.arange(n_dirs, dtype=np.float64) + 0.5
    phi = np.arccos(1 - 1.6 * i / n_dirs)  # bias toward upper hemisphere
    theta = np.pi * (1 + 5**0.5) * i
    dirs = np.stack(
        [np.sin(phi) * np.cos(theta), np.cos(phi), np.sin(phi) * np.sin(theta)], axis=1
    )

    progress(0.3, "Marching occlusion rays")
    # Start just off the surface along the normal to avoid self-occlusion.
    starts = mesh.vertices + mesh.vertex_normals * pitch * 1.5
    grid_shape = np.array(occ.shape)
    open_frac = np.zeros(len(mesh.vertices), dtype=np.float64)

    normals = mesh.vertex_normals
    for d in dirs:
        # Only directions in the normal hemisphere contribute for each vertex.
        facing = (normals @ d) > 0.0
        hit = np.zeros(len(starts), dtype=bool)
        p = starts.copy()
        for _ in range(steps):
            p = p + d * pitch * 1.4
            idx = np.floor((p - origin) / pitch).astype(int)
            valid = ((idx >= 0) & (idx < grid_shape)).all(axis=1)
            inside = np.zeros(len(starts), dtype=bool)
            vi = idx[valid]
            inside[valid] = occ[vi[:, 0], vi[:, 1], vi[:, 2]]
            hit |= inside
        open_frac += facing * (~hit)
        open_frac += (~facing) * 0.5  # neutral contribution for back-facing dirs

    ao = open_frac / n_dirs
    ao = np.clip((ao - ao.min()) / max(np.ptp(ao), 1e-6) * 0.7 + 0.3, 0, 1)
    progress(1.0, "AO done")
    return ao
