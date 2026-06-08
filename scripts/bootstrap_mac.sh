#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
cd frontend
npm install
npm run build
cd ..
echo "Done. Start Danaleo with: source .venv/bin/activate && danaleo"
