#!/usr/bin/env bash
# MyMeshy one-time setup (Linux / macOS). Run from the repo root: ./scripts/setup.sh
# Installs uv (if missing), creates a Python 3.11 venv, installs base backend
# deps + MCP deps, and installs frontend npm packages.
# (Windows users: use scripts\setup.ps1 instead.)
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

# --- uv (manages its own Python toolchains; system Python version is irrelevant)
if ! command -v uv >/dev/null 2>&1; then
    echo ">> Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# --- backend venv (Python 3.11 — the ML ecosystem's sweet spot)
echo ">> Creating backend venv (Python 3.11)..."
uv venv --python 3.11 "$root/.venv"
uv pip install --python "$root/.venv/bin/python" -r "$root/backend/requirements.txt"
uv pip install --python "$root/.venv/bin/python" -r "$root/mcp/requirements.txt"

# --- frontend
echo ">> Installing frontend packages..."
( cd "$root/frontend" && npm install )

echo ""
echo "Setup complete. Start the app with: ./scripts/dev.sh"
echo "The app runs in MOCK mode until you install real models (README: 'Installing real models')."
echo "Note: real generation needs an NVIDIA GPU + CUDA. macOS runs in mock mode only."
