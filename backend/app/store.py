"""Asset store: each asset is a folder under data/assets/{id} containing
meta.json, model.glb, textures/*.png and the source inputs."""
from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from .config import get_settings

TEXTURE_MAPS = ["albedo", "normal", "roughness", "metallic", "ao"]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def slugify(text: str, fallback: str = "asset") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48]
    return slug or fallback


def asset_dir(asset_id: str) -> Path:
    d = get_settings().assets_dir / asset_id
    if not d.resolve().is_relative_to(get_settings().assets_dir.resolve()):
        raise ValueError("invalid asset id")
    return d


def new_asset(name: str) -> tuple[str, Path]:
    asset_id = f"{slugify(name)}-{uuid.uuid4().hex[:8]}"
    d = asset_dir(asset_id)
    (d / "textures").mkdir(parents=True, exist_ok=True)
    (d / "source").mkdir(parents=True, exist_ok=True)
    return asset_id, d


def write_meta(asset_id: str, meta: dict) -> dict:
    meta = {**meta, "id": asset_id, "updated_at": _now_iso()}
    meta.setdefault("created_at", meta["updated_at"])
    (asset_dir(asset_id) / "meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    return meta


def read_meta(asset_id: str) -> Optional[dict]:
    p = asset_dir(asset_id) / "meta.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def list_assets() -> list[dict]:
    out = []
    root = get_settings().assets_dir
    for d in root.iterdir():
        if d.is_dir():
            meta = read_meta(d.name)
            if meta:
                out.append(meta)
    out.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return out


def delete_asset(asset_id: str) -> bool:
    d = asset_dir(asset_id)
    if d.is_dir():
        shutil.rmtree(d, ignore_errors=True)
        return True
    return False


def texture_names(asset_id: str) -> list[str]:
    tdir = asset_dir(asset_id) / "textures"
    return [m for m in TEXTURE_MAPS if (tdir / f"{m}.png").is_file()]
