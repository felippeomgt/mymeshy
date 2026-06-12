"""REST API routes."""
from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import __version__, export, store
from .config import detect_blender, detect_gpu, get_settings
from .jobs import get_job_manager
from .pipeline import registry, runner
from .pipeline.base import GenOptions

router = APIRouter(prefix="/api")

ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
ALLOWED_MESH_EXT = {".glb", ".gltf", ".obj", ".ply", ".stl"}


def _save_upload(up: UploadFile, allowed: set[str]) -> Path:
    suffix = Path(up.filename or "file").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"Unsupported file type '{suffix}' (allowed: {sorted(allowed)})")
    safe = f"{uuid.uuid4().hex[:8]}_{store.slugify(Path(up.filename or 'file').stem)}{suffix}"
    dst = get_settings().uploads_dir / safe
    dst.write_bytes(up.file.read())
    return dst


def _parse_options(options: Optional[str]) -> GenOptions:
    settings = get_settings()
    base = GenOptions(
        target_polycount=settings.default_target_polycount,
        texture_size=settings.default_texture_size,
    )
    if not options:
        return base
    try:
        d = json.loads(options)
    except json.JSONDecodeError:
        raise HTTPException(400, "options must be a JSON object")
    for k, v in (d or {}).items():
        if k in GenOptions.__dataclass_fields__ and v is not None:
            setattr(base, k, v)
    if base.texture_size not in (256, 512, 1024, 2048, 4096):
        raise HTTPException(400, "texture_size must be one of 256/512/1024/2048/4096")
    base.target_polycount = max(500, min(int(base.target_polycount), 500_000))
    return base


# --------------------------------------------------------------------------
# System
# --------------------------------------------------------------------------

@router.get("/system")
def system_info() -> dict:
    active = registry.active_names()
    return {
        "version": __version__,
        "gpu": detect_gpu(),
        "blender": detect_blender() is not None,
        "adapters": {stage: registry.describe(stage) for stage in
                     ("image_to_3d", "text_to_image", "texturing")},
        "active": active,
        "mock_mode": active["image_to_3d"] == "mock",
    }


# --------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------

class TextTo3DRequest(BaseModel):
    prompt: str
    options: Optional[dict] = None


@router.post("/jobs/text-to-3d")
def create_text_to_3d(req: TextTo3DRequest) -> dict:
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(400, "prompt is required")
    opts = _parse_options(json.dumps(req.options) if req.options else None)

    def work(job, progress_cb, cancelled):
        return runner.run_text_to_3d(prompt, opts, progress_cb, cancelled)

    job = get_job_manager().submit("text_to_3d", {"prompt": prompt, **opts.__dict__}, work)
    return job.public()


@router.post("/jobs/image-to-3d")
def create_image_to_3d(
    images: list[UploadFile] = File(...),
    options: Optional[str] = Form(None),
) -> dict:
    if not images:
        raise HTTPException(400, "at least one image is required")
    opts = _parse_options(options)
    paths = [_save_upload(up, ALLOWED_IMAGE_EXT) for up in images]

    def work(job, progress_cb, cancelled):
        return runner.run_image_to_3d(paths, opts, progress_cb, cancelled)

    job = get_job_manager().submit(
        "image_to_3d", {"images": [p.name for p in paths], **opts.__dict__}, work
    )
    return job.public()


@router.post("/jobs/texture")
def create_texture(
    asset_id: Optional[str] = Form(None),
    mesh: Optional[UploadFile] = File(None),
    prompt: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    options: Optional[str] = Form(None),
) -> dict:
    if not asset_id and mesh is None:
        raise HTTPException(400, "provide either asset_id or a mesh file")
    if not (prompt and prompt.strip()) and image is None:
        raise HTTPException(400, "provide a prompt and/or a reference image")
    opts = _parse_options(options)

    if asset_id:
        meta = store.read_meta(asset_id)
        if meta is None:
            raise HTTPException(404, f"asset '{asset_id}' not found")
        mesh_path = store.asset_dir(asset_id) / "model.glb"
        source_name = meta.get("name", "textured")
    else:
        mesh_path = _save_upload(mesh, ALLOWED_MESH_EXT)
        source_name = Path(mesh.filename or "mesh").stem

    image_path = _save_upload(image, ALLOWED_IMAGE_EXT) if image is not None else None
    clean_prompt = prompt.strip() if prompt else None

    def work(job, progress_cb, cancelled):
        return runner.run_texture(
            mesh_path, clean_prompt, image_path, opts, progress_cb, cancelled,
            source_name=source_name,
        )

    job = get_job_manager().submit(
        "texture",
        {"asset_id": asset_id, "prompt": clean_prompt, **opts.__dict__},
        work,
    )
    return job.public()


@router.get("/jobs")
def list_jobs() -> list[dict]:
    return get_job_manager().list()


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = get_job_manager().get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job.public()


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    job = get_job_manager().cancel(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job.public()


# --------------------------------------------------------------------------
# Assets
# --------------------------------------------------------------------------

@router.get("/assets")
def list_assets() -> list[dict]:
    return store.list_assets()


@router.get("/assets/{asset_id}")
def get_asset(asset_id: str) -> dict:
    meta = store.read_meta(asset_id)
    if meta is None:
        raise HTTPException(404, "asset not found")
    return meta


@router.delete("/assets/{asset_id}")
def delete_asset(asset_id: str) -> dict:
    if not store.delete_asset(asset_id):
        raise HTTPException(404, "asset not found")
    return {"deleted": asset_id}


class RenameRequest(BaseModel):
    name: str


@router.post("/assets/{asset_id}/rename")
def rename_asset(asset_id: str, req: RenameRequest) -> dict:
    meta = store.read_meta(asset_id)
    if meta is None:
        raise HTTPException(404, "asset not found")
    meta["name"] = req.name.strip()[:80] or meta["name"]
    return store.write_meta(asset_id, meta)


@router.get("/assets/{asset_id}/model.glb")
def get_model(asset_id: str) -> FileResponse:
    p = store.asset_dir(asset_id) / "model.glb"
    if not p.is_file():
        raise HTTPException(404, "model not found")
    return FileResponse(p, media_type="model/gltf-binary")


@router.get("/assets/{asset_id}/textures/{map_name}.png")
def get_texture(asset_id: str, map_name: str) -> FileResponse:
    if map_name not in store.TEXTURE_MAPS:
        raise HTTPException(404, "unknown texture map")
    p = store.asset_dir(asset_id) / "textures" / f"{map_name}.png"
    if not p.is_file():
        raise HTTPException(404, "texture not found")
    return FileResponse(p, media_type="image/png")


@router.get("/assets/{asset_id}/export")
def export_asset(asset_id: str, format: str = "glb") -> FileResponse:
    if store.read_meta(asset_id) is None:
        raise HTTPException(404, "asset not found")
    out_dir = Path(tempfile.mkdtemp(prefix="mymeshy_export_"))
    try:
        path = export.export_asset(asset_id, format, out_dir)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))
    return FileResponse(path, filename=path.name)
