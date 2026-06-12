"""End-to-end smoke test against a running backend (mock or real adapters).

    python scripts/smoke_test.py

Exercises: system info, text-to-3D, image-to-3D, texturing an existing asset,
GLB validity, texture endpoints, and every export format (FBX skipped when
Blender is absent).
"""
from __future__ import annotations

import io
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8420"


def req(method: str, path: str, json_body=None, multipart=None, raw=False):
    url = BASE + path
    headers = {}
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif multipart is not None:
        boundary = "----mymeshysmoke"
        buf = io.BytesIO()
        for name, value in multipart:
            buf.write(f"--{boundary}\r\n".encode())
            if isinstance(value, tuple):
                fname, content, ctype = value
                buf.write(
                    f'Content-Disposition: form-data; name="{name}"; filename="{fname}"\r\n'
                    f"Content-Type: {ctype}\r\n\r\n".encode()
                )
                buf.write(content)
            else:
                buf.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
                buf.write(str(value).encode())
            buf.write(b"\r\n")
        buf.write(f"--{boundary}--\r\n".encode())
        data = buf.getvalue()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=600) as resp:
        body = resp.read()
        return body if raw else json.loads(body)


def wait_job(job_id: str, label: str) -> dict:
    while True:
        job = req("GET", f"/api/jobs/{job_id}")
        if job["status"] in ("done", "error", "cancelled"):
            if job["status"] != "done":
                print(f"FAIL {label}: {job['status']} — {job.get('error')}")
                sys.exit(1)
            print(f"  ok   {label} -> asset {job['asset_id']}")
            return job
        time.sleep(1)


def main() -> None:
    print("== system ==")
    info = req("GET", "/api/system")
    print(f"  gpu={info['gpu']} blender={info['blender']} active={info['active']}")

    print("== text-to-3d ==")
    job = req("POST", "/api/jobs/text-to-3d", json_body={
        "prompt": "smoke test crate", "options": {"target_polycount": 5000, "texture_size": 256},
    })
    job = wait_job(job["id"], "text-to-3d")
    asset_id = job["asset_id"]

    print("== asset endpoints ==")
    meta = req("GET", f"/api/assets/{asset_id}")
    assert meta["stats"]["has_uv"], "asset missing UVs"
    glb = req("GET", f"/api/assets/{asset_id}/model.glb", raw=True)
    assert glb[:4] == b"glTF", "model.glb is not a valid GLB"
    print(f"  ok   GLB valid ({len(glb):,} bytes), stats={meta['stats']}")
    for t in meta["textures"]:
        png = req("GET", f"/api/assets/{asset_id}/textures/{t}.png", raw=True)
        assert png[:8] == b"\x89PNG\r\n\x1a\n", f"{t}.png invalid"
    print(f"  ok   textures: {meta['textures']}")

    print("== image-to-3d ==")
    # tiny synthetic image: red circle on transparent bg
    from PIL import Image, ImageDraw  # available in the backend venv

    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([48, 48, 208, 208], fill=(200, 40, 40, 255))
    b = io.BytesIO()
    img.save(b, "PNG")
    job = req("POST", "/api/jobs/image-to-3d", multipart=[
        ("images", ("red_ball.png", b.getvalue(), "image/png")),
        ("options", json.dumps({"target_polycount": 4000, "texture_size": 256})),
    ])
    wait_job(job["id"], "image-to-3d")

    print("== texture existing asset ==")
    job = req("POST", "/api/jobs/texture", multipart=[
        ("asset_id", asset_id),
        ("prompt", "weathered painted metal"),
        ("options", json.dumps({"texture_size": 256})),
    ])
    wait_job(job["id"], "texture")

    print("== exports ==")
    formats = ["glb", "gltf", "obj"] + (["fbx"] if info["blender"] else [])
    for fmt in formats:
        data = req("GET", f"/api/assets/{asset_id}/export?format={fmt}", raw=True)
        print(f"  ok   export {fmt}: {len(data):,} bytes")
    if not info["blender"]:
        print("  skip export fbx (no Blender detected)")

    print("\nALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} on {e.url}\n{e.read().decode()[:2000]}")
        sys.exit(1)
