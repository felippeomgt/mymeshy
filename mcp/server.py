"""MyMeshy MCP server.

Exposes the local generation backend as MCP tools so coding agents
(Claude Code, Cursor, ...) can request game assets while you develop:

    "Generate a low-poly health potion for my dungeon crawler and export it
     as GLB into ./game/assets/props"

Run the MyMeshy backend first, then register this server (see README).
Transport: stdio.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

BACKEND = os.environ.get("MYMESHY_URL", "http://127.0.0.1:8420")

mcp = FastMCP(
    "mymeshy",
    instructions=(
        "Local AI 3D asset generator. Generation runs on the local GPU and takes "
        "from seconds (mock/triposr) to several minutes (trellis/hunyuan3d). "
        "Submit a job, then poll with get_job or block with wait_for_job. "
        "Finished assets are GLB files with PBR textures; use export_asset to "
        "copy them into a game project in glb/gltf/obj/fbx format."
    ),
)


def _client() -> httpx.Client:
    return httpx.Client(base_url=BACKEND, timeout=120)


def _check(resp: httpx.Response) -> dict | list:
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise RuntimeError(f"MyMeshy backend error {resp.status_code}: {detail}")
    return resp.json()


def _wait(job_id: str, timeout_s: float) -> dict:
    deadline = time.monotonic() + timeout_s
    with _client() as c:
        while True:
            job = _check(c.get(f"/api/jobs/{job_id}"))
            if job["status"] in ("done", "error", "cancelled"):
                return job
            if time.monotonic() > deadline:
                job["note"] = f"still {job['status']} after {timeout_s:.0f}s — poll get_job later"
                return job
            time.sleep(2)


def _options(target_polycount: Optional[int], texture_size: Optional[int],
             adapter: Optional[str], seed: Optional[int]) -> dict:
    return {k: v for k, v in {
        "target_polycount": target_polycount,
        "texture_size": texture_size,
        "adapter": adapter,
        "seed": seed,
    }.items() if v is not None}


@mcp.tool()
def system_status() -> dict:
    """Backend status: GPU, which AI adapters are installed/active, whether FBX
    export (Blender) is available, and whether the app is in mock mode."""
    with _client() as c:
        return _check(c.get("/api/system"))


@mcp.tool()
def text_to_3d(
    prompt: str,
    target_polycount: int = 30000,
    texture_size: int = 1024,
    adapter: Optional[str] = None,
    seed: Optional[int] = None,
    wait_seconds: float = 600,
) -> dict:
    """Generate a textured 3D asset from a text description (e.g. "rusty
    medieval barrel with iron bands, game prop"). Describe one single object.
    Returns the finished job including asset_id, or the in-progress job if it
    exceeds wait_seconds. Pass wait_seconds=0 to return immediately."""
    with _client() as c:
        job = _check(c.post("/api/jobs/text-to-3d", json={
            "prompt": prompt,
            "options": _options(target_polycount, texture_size, adapter, seed),
        }))
    return _wait(job["id"], wait_seconds) if wait_seconds > 0 else job


@mcp.tool()
def image_to_3d(
    image_paths: list[str],
    target_polycount: int = 30000,
    texture_size: int = 1024,
    adapter: Optional[str] = None,
    seed: Optional[int] = None,
    wait_seconds: float = 600,
) -> dict:
    """Reconstruct a textured 3D asset from one or more local reference images
    (absolute paths). The first image is the primary view."""
    files = []
    for p in image_paths:
        path = Path(p)
        if not path.is_file():
            raise FileNotFoundError(f"Image not found: {p}")
        files.append(("images", (path.name, path.read_bytes())))
    import json as _json

    with _client() as c:
        job = _check(c.post(
            "/api/jobs/image-to-3d",
            files=files,
            data={"options": _json.dumps(_options(target_polycount, texture_size, adapter, seed))},
        ))
    return _wait(job["id"], wait_seconds) if wait_seconds > 0 else job


@mcp.tool()
def texture_mesh(
    prompt: Optional[str] = None,
    asset_id: Optional[str] = None,
    mesh_path: Optional[str] = None,
    image_path: Optional[str] = None,
    texture_size: int = 1024,
    wait_seconds: float = 600,
) -> dict:
    """(Re)texture a mesh. Target either an existing MyMeshy asset (asset_id)
    or a local mesh file (mesh_path: .glb/.obj/.ply/.stl). Condition on a text
    prompt and/or a reference image."""
    if not asset_id and not mesh_path:
        raise ValueError("Provide asset_id or mesh_path")
    import json as _json

    data: dict = {"options": _json.dumps({"texture_size": texture_size})}
    if asset_id:
        data["asset_id"] = asset_id
    if prompt:
        data["prompt"] = prompt
    files = []
    if mesh_path:
        p = Path(mesh_path)
        if not p.is_file():
            raise FileNotFoundError(f"Mesh not found: {mesh_path}")
        files.append(("mesh", (p.name, p.read_bytes())))
    if image_path:
        p = Path(image_path)
        if not p.is_file():
            raise FileNotFoundError(f"Image not found: {image_path}")
        files.append(("image", (p.name, p.read_bytes())))

    with _client() as c:
        job = _check(c.post("/api/jobs/texture", files=files or None, data=data))
    return _wait(job["id"], wait_seconds) if wait_seconds > 0 else job


@mcp.tool()
def get_job(job_id: str) -> dict:
    """Status of a generation job (status, stage, progress 0-1, asset_id when done)."""
    with _client() as c:
        return _check(c.get(f"/api/jobs/{job_id}"))


@mcp.tool()
def wait_for_job(job_id: str, timeout_seconds: float = 600) -> dict:
    """Block until a job finishes (or the timeout passes) and return it."""
    return _wait(job_id, timeout_seconds)


@mcp.tool()
def list_assets() -> list:
    """All generated assets with stats (vertices, triangles, textures, source prompt)."""
    with _client() as c:
        return _check(c.get("/api/assets"))


@mcp.tool()
def export_asset(asset_id: str, output_path: str, format: str = "glb") -> dict:
    """Export a generated asset into a game project. format: glb | gltf | obj |
    fbx (fbx needs Blender installed). output_path may be a target file or an
    existing directory; gltf/obj arrive as a .zip containing mesh + textures."""
    with _client() as c:
        resp = c.get(f"/api/assets/{asset_id}/export", params={"format": format})
        if resp.status_code >= 400:
            _check(resp)
        suggested = resp.headers.get("content-disposition", "")
        name = suggested.split("filename=")[-1].strip('"') if "filename=" in suggested else f"{asset_id}.{format}"

        out = Path(output_path)
        if out.is_dir():
            out = out / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(resp.content)
    return {"saved_to": str(out.resolve()), "bytes": out.stat().st_size}


@mcp.tool()
def get_texture_maps(asset_id: str, output_dir: str) -> dict:
    """Save an asset's PBR texture maps (albedo/normal/roughness/metallic/ao)
    as PNGs into output_dir. Returns the saved file paths."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    with _client() as c:
        meta = _check(c.get(f"/api/assets/{asset_id}"))
        for m in meta.get("textures", []):
            resp = c.get(f"/api/assets/{asset_id}/textures/{m}.png")
            if resp.status_code == 200:
                p = out_dir / f"{asset_id}_{m}.png"
                p.write_bytes(resp.content)
                saved.append(str(p.resolve()))
    return {"saved": saved}


if __name__ == "__main__":
    mcp.run()
