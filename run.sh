#!/usr/bin/env bash
set -e

# conv dev framework — Quick Start
# =====================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
VENV_DIR="$BACKEND_DIR/venv"

echo "╔═══════════════════════════════════════════════════╗"
echo "║       conv dev framework — Quick Start        ║"
echo "╚═══════════════════════════════════════════════════╝"

# 1. Check prerequisites
echo ""
echo "── Prerequisites ──────────────────────────────────"

# Python
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "ERROR: Python 3 not found. Install Python 3.10+."
    exit 1
fi
echo "[OK] Python: $($PYTHON --version 2>&1)"

# Virtual env
if [ -f "$VENV_DIR/bin/activate" ]; then
    echo "[OK] Virtual environment found at $VENV_DIR"
else
    echo "[SETUP] Creating virtual environment..."
    $PYTHON -m venv "$VENV_DIR"
    echo "[OK] Virtual environment created"
fi

# Activate venv
source "$VENV_DIR/bin/activate"

# Dependencies
if [ -f "$BACKEND_DIR/requirements.txt" ]; then
    echo "[SETUP] Checking dependencies..."
    pip install -q -r "$BACKEND_DIR/requirements.txt" 2>/dev/null || pip install -r "$BACKEND_DIR/requirements.txt"
    echo "[OK] Dependencies installed"
fi

# 2. Check LM Studio
echo ""
echo "── LM Studio Check ────────────────────────────────"
if curl -sf http://localhost:1234/v1/models > /dev/null 2>&1; then
    MODEL_NAME=$(curl -sf http://localhost:1234/v1/models | $PYTHON -c "import sys,json; d=json.load(sys.stdin); print(d['data'][0]['id'])" 2>/dev/null || echo "unknown")
    echo "[OK] LM Studio is running (model: $MODEL_NAME)"
else
    echo "[WARN] LM Studio not detected on http://localhost:1234"
    echo "       Start LM Studio and load a model before running tasks."
    echo "       The server will still start, but agents won't work."
fi

# 3. Start the server
echo ""
echo "── Starting Server ────────────────────────────────"
echo "     Backend: $BACKEND_DIR"
echo "     Frontend: $SCRIPT_DIR/frontend"
echo "     URL: http://localhost:8000"
echo ""

cd "$BACKEND_DIR"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
