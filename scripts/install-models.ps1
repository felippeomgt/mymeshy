# Installs the real AI generation stack (run after scripts\setup.ps1):
#   - CUDA PyTorch + diffusers/transformers  -> enables SDXL-Turbo (text-to-image)
#   - Hunyuan3D-2 repo                       -> enables hunyuan3d (image-to-3D shape)
#   - TripoSR repo                           -> enables triposr (fast image-to-3D)
# Model weights themselves download from Hugging Face on first generation,
# into data\caches\hf (kept off C:).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = "$root\.venv\Scripts\python.exe"
$env:UV_CACHE_DIR = "$root\data\uv-cache"

Write-Host ">> Installing CUDA PyTorch (cu124, ~2.5GB download)..." -ForegroundColor Cyan
uv pip install --python $py torch torchvision --index-url https://download.pytorch.org/whl/cu124
uv pip install --python $py -r "$root\backend\requirements-ml.txt"

Write-Host ">> Cloning model repos into external\ ..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force "$root\external" | Out-Null
if (-not (Test-Path "$root\external\Hunyuan3D-2")) {
    git clone --depth 1 https://github.com/Tencent-Hunyuan/Hunyuan3D-2 "$root\external\Hunyuan3D-2"
}
if (-not (Test-Path "$root\external\TripoSR")) {
    git clone --depth 1 https://github.com/VAST-AI-Research/TripoSR "$root\external\TripoSR"
}

Write-Host ">> Installing adapter dependencies..." -ForegroundColor Cyan
# NOTE: intentionally NOT installing the repos' own requirements.txt files —
# they pin old versions and torchmcubes (needs the CUDA toolkit to compile).
# MyMeshy ships a scikit-image torchmcubes shim instead.
uv pip install --python $py ninja pybind11 opencv-python pymeshlab pygltflib imageio moderngl

Write-Host ""
Write-Host "Done. Restart the backend, then check the adapter status:" -ForegroundColor Green
Write-Host "  irm http://127.0.0.1:8420/api/system | ConvertTo-Json -Depth 5"
Write-Host "First generation downloads model weights (~2GB TripoSR, ~4GB Hunyuan mini, ~7GB SDXL-Turbo)." -ForegroundColor Yellow
