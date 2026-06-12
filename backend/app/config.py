"""Application configuration.

Everything is overridable through environment variables prefixed with
``MYMESHY_`` (e.g. ``MYMESHY_I23D_ADAPTER=trellis``) or a ``.env`` file placed
next to the repo root.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MYMESHY_", env_file=REPO_ROOT / ".env", extra="ignore"
    )

    host: str = "127.0.0.1"
    port: int = 8420

    data_dir: Path = REPO_ROOT / "data"

    # GPU memory budget in GB. 0 = unlimited. When set, torch allocations are
    # hard-capped to this amount and the pipeline switches to low-VRAM mode:
    # sequential CPU offloading, smaller inference chunks, and models are
    # loaded one stage at a time and unloaded between stages (slower, but the
    # GPU stays usable for everything else).
    vram_budget_gb: float = 0

    # Adapter selection. "auto" picks the best available, preferring real
    # models over the mock pipeline.
    i23d_adapter: str = "auto"      # trellis | hunyuan3d | triposr | mock | auto
    t2i_adapter: str = "auto"       # sdxl_turbo | mock | auto
    texture_adapter: str = "auto"   # hunyuan_paint | mock | auto

    # Path to blender.exe for FBX export. Auto-detected if empty.
    blender_path: str = ""

    # Default generation options
    default_texture_size: int = 1024
    default_target_polycount: int = 30000

    # Hugging Face cache lives wherever HF_HOME points; models are large.
    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def jobs_file(self) -> Path:
        return self.data_dir / "jobs.json"

    def ensure_dirs(self) -> None:
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        # Keep multi-GB model caches on this drive instead of filling C:.
        caches = self.data_dir / "caches"
        for var, sub in (("HF_HOME", "hf"), ("TORCH_HOME", "torch"), ("U2NET_HOME", "u2net")):
            path = caches / sub
            path.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault(var, str(path))
        if self.vram_budget_gb:
            # Must be set before the CUDA allocator initializes.
            os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


# --------------------------------------------------------------------------
# Environment probes
# --------------------------------------------------------------------------

@lru_cache
def detect_blender() -> Optional[str]:
    """Find blender.exe: explicit setting > PATH > Steam libraries > standard installs."""
    s = get_settings()
    if s.blender_path and Path(s.blender_path).is_file():
        return s.blender_path

    on_path = shutil.which("blender")
    if on_path:
        return on_path

    candidates: list[Path] = []

    # Steam libraries (Blender is distributed on Steam). Parse libraryfolders.vdf
    # so non-default library drives are found too.
    steam_roots = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Steam",
    ]
    library_dirs = list(steam_roots)
    for root in steam_roots:
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if vdf.is_file():
            try:
                for m in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(errors="ignore")):
                    library_dirs.append(Path(m.group(1).replace("\\\\", "\\")))
            except OSError:
                pass
    for lib in library_dirs:
        candidates.append(lib / "steamapps" / "common" / "Blender" / "blender.exe")

    # Standard installer locations
    bf = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Blender Foundation"
    if bf.is_dir():
        for sub in sorted(bf.iterdir(), reverse=True):
            candidates.append(sub / "blender.exe")

    for c in candidates:
        if c.is_file():
            return str(c)
    return None


@lru_cache
def detect_gpu() -> Optional[dict]:
    """Return {'name': ..., 'vram_mb': ...} via nvidia-smi, or None."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        name, mem = out.stdout.strip().splitlines()[0].rsplit(",", 1)
        return {"name": name.strip(), "vram_mb": int(float(mem.strip()))}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
