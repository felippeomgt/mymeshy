"""Asset export: GLB (native), GLTF + OBJ (zipped with textures), FBX via a
headless Blender conversion (auto-detected, including Steam installs)."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import trimesh

from .config import detect_blender
from .store import asset_dir

FORMATS = ("glb", "gltf", "obj", "fbx")

_BLENDER_SCRIPT = r"""
import sys
import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
src, dst = argv

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
bpy.ops.export_scene.fbx(
    filepath=dst,
    use_selection=False,
    path_mode="COPY",
    embed_textures=True,
    bake_space_transform=True,
)
"""


def export_asset(asset_id: str, fmt: str, out_dir: Path) -> Path:
    """Produce the export file in ``out_dir`` and return its path."""
    fmt = fmt.lower()
    if fmt not in FORMATS:
        raise ValueError(f"Unsupported format '{fmt}' (use one of {FORMATS})")

    glb = asset_dir(asset_id) / "model.glb"
    if not glb.is_file():
        raise FileNotFoundError("Asset has no model.glb")

    if fmt == "glb":
        dst = out_dir / f"{asset_id}.glb"
        shutil.copyfile(glb, dst)
        return dst

    if fmt == "fbx":
        blender = detect_blender()
        if not blender:
            raise RuntimeError(
                "FBX export requires Blender. Install it (Steam or blender.org) or set "
                "MYMESHY_BLENDER_PATH to blender.exe."
            )
        dst = out_dir / f"{asset_id}.fbx"
        with tempfile.TemporaryDirectory() as td:
            script = Path(td) / "convert_fbx.py"
            script.write_text(_BLENDER_SCRIPT, encoding="utf-8")
            proc = subprocess.run(
                [blender, "-b", "--factory-startup", "-noaudio",
                 "--python", str(script), "--", str(glb), str(dst)],
                capture_output=True, text=True, timeout=300,
            )
        if not dst.is_file():
            tail = (proc.stdout + proc.stderr)[-2000:]
            raise RuntimeError(f"Blender FBX conversion failed:\n{tail}")
        return dst

    # gltf / obj: trimesh re-export, zipped because they are multi-file.
    mesh = trimesh.load(glb, force="mesh")
    dst = out_dir / f"{asset_id}_{fmt}.zip"
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        if fmt == "gltf":
            mesh.export(tdp / "model.gltf")
        else:
            mesh.export(tdp / "model.obj", include_texture=True)
        # Ship the individual PBR maps alongside (OBJ/MTL can't reference them all).
        tex_src = asset_dir(asset_id) / "textures"
        for t in tex_src.glob("*.png"):
            shutil.copyfile(t, tdp / t.name)
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(tdp.iterdir()):
                zf.write(f, f.name)
    return dst
