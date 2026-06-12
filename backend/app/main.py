"""MyMeshy backend entry point.

Run with:  uvicorn app.main:app --host 127.0.0.1 --port 8420
(or simply: python -m app.main)
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api import router
from .config import detect_blender, detect_gpu, get_settings
from .jobs import get_job_manager
from .pipeline import registry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("mymeshy")

app = FastAPI(title="MyMeshy", version=__version__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
def startup() -> None:
    settings = get_settings()
    settings.ensure_dirs()
    get_job_manager()  # start the worker thread

    gpu = detect_gpu()
    blender = detect_blender()
    active = registry.active_names()
    log.info("MyMeshy %s", __version__)
    log.info("GPU: %s", f"{gpu['name']} ({gpu['vram_mb']} MB)" if gpu else "none detected")
    log.info("Blender: %s", blender or "not found (FBX export disabled)")
    log.info("Active adapters: %s", active)
    if active["image_to_3d"] == "mock":
        log.warning(
            "Running in MOCK mode — no ML models installed. The full pipeline works "
            "but produces placeholder meshes. See README 'Installing real models'."
        )


if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, reload=False)
