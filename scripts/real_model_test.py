"""Direct pipeline test for the real (GPU) adapters, with VRAM monitoring.

    python scripts/real_model_test.py triposr|hunyuan3d [image|text]

Peaks above the configured budget mean offloading isn't holding.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time

sys.path.insert(0, "backend")

from app.config import get_settings  # noqa: E402  (sets HF_HOME etc.)

settings = get_settings()
print(f"VRAM budget: {settings.vram_budget_gb} GB")

peak = {"used": 0, "baseline": 0}
stop = threading.Event()


def _gpu_used() -> int:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=5,
    )
    return int(out.stdout.strip().splitlines()[0])


def monitor():
    while not stop.is_set():
        try:
            peak["used"] = max(peak["used"], _gpu_used())
        except Exception:
            pass
        time.sleep(1)


def main():
    adapter = sys.argv[1] if len(sys.argv) > 1 else "triposr"
    mode = sys.argv[2] if len(sys.argv) > 2 else "image"

    from PIL import Image, ImageDraw

    from app.pipeline.base import GenOptions
    from app.pipeline.runner import run_image_to_3d, run_text_to_3d

    try:
        peak["baseline"] = _gpu_used()
    except Exception:
        pass
    print(f"GPU baseline (other processes): {peak['baseline']} MiB")
    threading.Thread(target=monitor, daemon=True).start()
    t0 = time.time()

    last = {"stage": None}

    def cb(p, stage, msg):
        if stage != last["stage"]:
            last["stage"] = stage
            print(f"  [{time.time()-t0:6.0f}s] [{p:4.2f}] {stage}: {msg}", flush=True)

    opts = GenOptions(adapter=adapter, target_polycount=20000, texture_size=1024)

    if mode == "text":
        meta = run_text_to_3d("a wooden treasure chest with brass fittings", opts, cb, lambda: False)
    else:
        # synthetic test subject: a simple potion-bottle silhouette
        img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([196, 60, 316, 150], radius=20, fill=(160, 120, 70, 255))   # cork
        d.ellipse([130, 130, 382, 430], fill=(90, 40, 130, 255))                        # body
        d.ellipse([180, 180, 280, 280], fill=(140, 80, 190, 255))                       # highlight
        p = settings.uploads_dir / "test_potion.png"
        img.save(p)
        meta = run_image_to_3d([p], opts, cb, lambda: False)

    stop.set()
    print(f"\nDONE in {time.time()-t0:.0f}s — asset {meta['id']}")
    print("stats:", meta["stats"], "| textures:", meta["textures"])
    ours = peak["used"] - peak["baseline"]
    print(f"PEAK GPU MEMORY: {peak['used']} MiB total, ~{ours} MiB ours "
          f"(budget {settings.vram_budget_gb*1024:.0f} MiB)")


if __name__ == "__main__":
    main()
