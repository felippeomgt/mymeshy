"""Pipeline orchestration: turns job requests into finished assets.

Stage chain (text-to-3D):
  prompt -> text-to-image -> background removal -> image-to-3D
         -> cleanup -> decimate -> UV unwrap -> texture bake -> PBR maps -> GLB

Image-to-3D and texturing jobs enter the same chain at later stages.
Every stage reports progress through the job's callback and checks for
cancellation between stages.
"""
from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

import numpy as np
import trimesh
from PIL import Image

from .. import store
from . import meshproc, pbr, registry
from .base import GenOptions, MeshResult, low_vram

log = logging.getLogger("mymeshy.pipeline")

# (stage_key, label, weight) — weights drive the aggregate progress bar.
@dataclass
class StageReporter:
    progress_cb: Callable[[float, str, str], None]  # (overall 0..1, stage, message)
    cancelled: Callable[[], bool]
    stages: Sequence[tuple[str, float]]
    done_weight: float = 0.0
    _idx: int = -1

    def enter(self, stage_key: str) -> Callable[[float, str], None]:
        if self.cancelled():
            raise JobCancelled()
        self._idx += 1
        self.done_weight = sum(w for _, w in self.stages[: self._idx])
        key, weight = self.stages[self._idx]
        assert key == stage_key, f"stage order mismatch: {key} != {stage_key}"

        def report(frac: float, message: str) -> None:
            if self.cancelled():
                raise JobCancelled()
            overall = self.done_weight + max(0.0, min(frac, 1.0)) * weight
            self.progress_cb(min(overall, 0.999), stage_key, message)

        report(0.0, stage_key.replace("_", " ").capitalize())
        return report


class JobCancelled(Exception):
    pass


# --------------------------------------------------------------------------
# Background removal (rembg, optional)
# --------------------------------------------------------------------------

_rembg_session = None


def remove_background(image: Image.Image) -> Image.Image:
    """Isolate the subject. Uses rembg (u2net, CPU) when installed; otherwise
    passes through (the mock adapter estimates a mask itself)."""
    if importlib.util.find_spec("rembg") is None:
        return image
    global _rembg_session
    try:
        from rembg import new_session, remove

        if _rembg_session is None:
            _rembg_session = new_session("u2net")
        return remove(image, session=_rembg_session)
    except Exception as exc:  # rembg failure must not kill the job
        log.warning("rembg failed, continuing without background removal: %s", exc)
        return image


# --------------------------------------------------------------------------
# Shared post-processing: raw MeshResult -> finished asset folder
# --------------------------------------------------------------------------

POST_STAGES: list[tuple[str, float]] = [
    ("mesh_cleanup", 0.10),
    ("retopology", 0.15),
    ("uv_unwrap", 0.15),
    ("texture_bake", 0.30),
    ("pbr_maps", 0.20),
    ("export", 0.10),
]


def postprocess_to_asset(
    result: MeshResult,
    opts: GenOptions,
    reporter: StageReporter,
    asset_id: str,
    asset_path: Path,
    meta: dict,
    keep_source_uvs: bool = False,
    fallback_image: Optional[Image.Image] = None,
) -> dict:
    raw = result.mesh

    # Geometry-only adapters (e.g. Hunyuan shape without the paint pipeline)
    # still get a real albedo: project the reference image onto the mesh.
    if (
        fallback_image is not None
        and result.albedo is None
        and not result.textured
        and not meshproc._has_vertex_colors(raw)
    ):
        raw = meshproc.project_image_colors(raw, fallback_image)
        result = MeshResult(mesh=raw, textured=False)
        meta["albedo_source"] = "reference_projection"

    # ---- cleanup ---------------------------------------------------------
    # Cleanup and decimation rebuild vertex order, which destroys existing
    # UVs — when keeping source UVs (texture jobs) those stages are skipped.
    rep = reporter.enter("mesh_cleanup")
    if keep_source_uvs:
        mesh = raw
        source_for_transfer = None
        rep(1.0, "Skipped (preserving existing UV layout)")
    else:
        rep(0.1, f"Cleaning mesh ({len(raw.faces):,} faces)")
        source_textured = (
            result.textured and hasattr(raw.visual, "uv") and raw.visual.uv is not None
        )
        source_for_transfer = raw.copy() if source_textured else None
        mesh = meshproc.cleanup(raw)
        mesh = meshproc.normalize_scale(mesh)
        if source_for_transfer is not None:
            source_for_transfer = meshproc.normalize_scale(source_for_transfer)
        rep(1.0, f"Clean: {len(mesh.faces):,} faces")

    # ---- decimation / retopology ----------------------------------------
    rep = reporter.enter("retopology")
    if not keep_source_uvs and opts.decimate and len(mesh.faces) > opts.target_polycount:
        rep(0.2, f"Decimating {len(mesh.faces):,} -> {opts.target_polycount:,} faces")
        mesh = meshproc.decimate(mesh, opts.target_polycount)
    rep(1.0, f"Topology: {len(mesh.faces):,} faces")

    # ---- UV unwrap -------------------------------------------------------
    rep = reporter.enter("uv_unwrap")
    if keep_source_uvs and hasattr(mesh.visual, "uv") and mesh.visual.uv is not None:
        uvs = np.asarray(mesh.visual.uv)
        rep(1.0, "Kept existing UVs")
    else:
        rep(0.2, "Generating UV atlas (xatlas)")
        mesh, uvs = meshproc.unwrap(mesh)
        rep(1.0, f"UV atlas ready ({len(mesh.vertices):,} verts after seams)")

    # ---- albedo bake -----------------------------------------------------
    rep = reporter.enter("texture_bake")
    size = opts.texture_size
    if result.albedo is not None and keep_source_uvs:
        albedo = result.albedo.convert("RGB").resize((size, size), Image.LANCZOS)
        rep(1.0, "Used adapter-provided albedo")
    elif source_for_transfer is not None:
        albedo = meshproc.bake_texture_to_atlas(
            source_for_transfer, mesh, uvs, size,
            lambda p, m: rep(p * 0.95, m),
        )
        rep(1.0, "Source texture re-baked to atlas")
    else:
        albedo = meshproc.bake_vertex_colors(mesh, uvs, size, lambda p, m: rep(p * 0.95, m))
        rep(1.0, "Albedo baked from vertex colors")

    tex_dir = asset_path / "textures"
    albedo.save(tex_dir / "albedo.png")

    # ---- PBR maps --------------------------------------------------------
    rep = reporter.enter("pbr_maps")
    textures = ["albedo"]
    material_kwargs: dict = {}
    if opts.generate_pbr:
        rep(0.1, "Computing geometry ambient occlusion")
        ao_vals = meshproc.vertex_ao(mesh, progress=lambda p, m: rep(0.1 + p * 0.4, m))
        ao_img_raw, covered = meshproc._rasterize_attribute(
            uvs, mesh.faces, ao_vals[:, None], size
        )
        geo_ao = Image.fromarray(
            (np.clip(meshproc._dilate(ao_img_raw, covered)[..., 0], 0, 1) * 255).astype(np.uint8),
            mode="L",
        )
        rep(0.6, "Deriving normal / roughness / metallic maps")
        normal = pbr.smooth_seams(pbr.normal_from_albedo(albedo))
        roughness = pbr.roughness_from_albedo(albedo)
        metallic = pbr.metallic_from_albedo(albedo)
        ao = pbr.ao_map(albedo, geo_ao)

        normal.save(tex_dir / "normal.png")
        roughness.save(tex_dir / "roughness.png")
        metallic.save(tex_dir / "metallic.png")
        ao.save(tex_dir / "ao.png")
        textures += ["normal", "roughness", "metallic", "ao"]

        orm = pbr.pack_orm(ao, roughness, metallic, size)
        material_kwargs = {
            "metallicRoughnessTexture": orm,
            "occlusionTexture": orm,
            "normalTexture": normal,
        }
        rep(1.0, "PBR maps ready")
    else:
        rep(1.0, "PBR maps skipped")

    # ---- assemble + export ----------------------------------------------
    rep = reporter.enter("export")
    material = trimesh.visual.material.PBRMaterial(
        name="mymeshy_material",
        baseColorTexture=albedo,
        metallicFactor=1.0 if opts.generate_pbr else 0.0,
        roughnessFactor=1.0,
        **material_kwargs,
    )
    mesh.visual = trimesh.visual.TextureVisuals(uv=uvs, material=material)
    rep(0.3, "Writing GLB")
    mesh.export(asset_path / "model.glb")

    meta["stats"] = {
        "vertices": int(len(mesh.vertices)),
        "triangles": int(len(mesh.faces)),
        "materials": 1,
        "texture_size": size,
        "has_uv": True,
    }
    meta["textures"] = textures
    rep(1.0, "Asset exported")
    return store.write_meta(asset_id, meta)


# --------------------------------------------------------------------------
# Job entry points
# --------------------------------------------------------------------------

def run_text_to_3d(
    prompt: str,
    opts: GenOptions,
    progress_cb: Callable[[float, str, str], None],
    cancelled: Callable[[], bool],
) -> dict:
    stages = [("text_to_image", 0.15), ("background_removal", 0.05),
              ("image_to_3d", 0.30)] + [(k, w * 0.5) for k, w in POST_STAGES]
    reporter = StageReporter(progress_cb, cancelled, stages)

    t2i = registry.resolve("text_to_image")
    rep = reporter.enter("text_to_image")
    ref_image = t2i.generate(prompt, opts, rep)
    if low_vram():
        t2i.unload()

    asset_id, asset_path = store.new_asset(prompt)
    ref_image.save(asset_path / "source" / "reference.png")
    (asset_path / "source" / "prompt.txt").write_text(prompt, encoding="utf-8")

    rep = reporter.enter("background_removal")
    rep(0.2, "Removing background")
    ref_image = remove_background(ref_image)
    ref_image.save(asset_path / "source" / "reference_cutout.png")

    i23d = registry.resolve("image_to_3d", opts.adapter)
    rep = reporter.enter("image_to_3d")
    result = i23d.generate([ref_image], opts, rep)
    if low_vram():
        i23d.unload()

    meta = {
        "name": store.slugify(prompt).replace("-", " ") or "asset",
        "source": {"type": "text", "prompt": prompt},
        "adapter": i23d.name,
    }
    return postprocess_to_asset(result, opts, reporter, asset_id, asset_path, meta,
                                keep_source_uvs=False, fallback_image=ref_image)


def run_image_to_3d(
    image_paths: Sequence[Path],
    opts: GenOptions,
    progress_cb: Callable[[float, str, str], None],
    cancelled: Callable[[], bool],
) -> dict:
    stages = [("background_removal", 0.05), ("image_to_3d", 0.35)] + [
        (k, w * 0.6) for k, w in POST_STAGES
    ]
    reporter = StageReporter(progress_cb, cancelled, stages)

    name = image_paths[0].stem
    asset_id, asset_path = store.new_asset(name)

    rep = reporter.enter("background_removal")
    images = []
    for i, p in enumerate(image_paths):
        rep(i / max(len(image_paths), 1), f"Removing background ({p.name})")
        img = Image.open(p)
        img.load()
        cut = remove_background(img)
        cut.save(asset_path / "source" / f"input_{i}_{store.slugify(p.stem)}.png")
        images.append(cut)

    i23d = registry.resolve("image_to_3d", opts.adapter)
    rep = reporter.enter("image_to_3d")
    result = i23d.generate(images, opts, rep)
    if low_vram():
        i23d.unload()

    meta = {
        "name": name,
        "source": {"type": "image", "image_names": [p.name for p in image_paths]},
        "adapter": i23d.name,
    }
    return postprocess_to_asset(result, opts, reporter, asset_id, asset_path, meta,
                                keep_source_uvs=False, fallback_image=images[0])


def run_texture(
    mesh_path: Path,
    prompt: Optional[str],
    image_path: Optional[Path],
    opts: GenOptions,
    progress_cb: Callable[[float, str, str], None],
    cancelled: Callable[[], bool],
    source_name: str = "textured",
) -> dict:
    stages = [("load_mesh", 0.05), ("texturing", 0.45)] + [
        (k, w * 0.5) for k, w in POST_STAGES
    ]
    reporter = StageReporter(progress_cb, cancelled, stages)

    rep = reporter.enter("load_mesh")
    rep(0.2, f"Loading {mesh_path.name}")
    loaded = trimesh.load(mesh_path, force="mesh")
    if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) == 0:
        raise ValueError(f"Could not load a triangle mesh from {mesh_path.name}")

    has_uv = hasattr(loaded.visual, "uv") and loaded.visual.uv is not None
    if not has_uv:
        rep(0.6, "Mesh has no UVs — unwrapping first")
        loaded, uvs = meshproc.unwrap(meshproc.cleanup(loaded))
        loaded.visual = trimesh.visual.TextureVisuals(uv=uvs)

    image = None
    if image_path is not None:
        image = Image.open(image_path)
        image.load()

    tex = registry.resolve("texturing", opts.adapter)
    rep = reporter.enter("texturing")
    result = tex.generate(loaded, prompt, image, opts, rep)
    if low_vram():
        tex.unload()

    asset_id, asset_path = store.new_asset(prompt or source_name)
    if prompt:
        (asset_path / "source" / "prompt.txt").write_text(prompt, encoding="utf-8")
    if image is not None:
        image.save(asset_path / "source" / "reference.png")

    meta = {
        "name": (prompt or source_name)[:48],
        "source": {"type": "texture", "prompt": prompt},
        "adapter": tex.name,
    }
    # The texturing adapter worked with the mesh's existing UVs; keep them.
    keep = hasattr(result.mesh.visual, "uv") and result.mesh.visual.uv is not None
    return postprocess_to_asset(result, opts, reporter, asset_id, asset_path, meta,
                                keep_source_uvs=keep)
