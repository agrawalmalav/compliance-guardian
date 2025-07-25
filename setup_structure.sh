#!/bin/bash
# Script to create project folder structure for Compliance Guardian

set -e

BASE_DIR="$(dirname "$0")"

mkdir -p "$BASE_DIR/compliance_guardian/agents"
mkdir -p "$BASE_DIR/compliance_guardian/config/rules"
mkdir -p "$BASE_DIR/compliance_guardian/datasets"
mkdir -p "$BASE_DIR/compliance_guardian/logs"
mkdir -p "$BASE_DIR/compliance_guardian/reports"
mkdir -p "$BASE_DIR/compliance_guardian/utils"

touch "$BASE_DIR/compliance_guardian/agents/__init__.py"
touch "$BASE_DIR/compliance_guardian/utils/__init__.py"
touch "$BASE_DIR/README.md"
touch "$BASE_DIR/requirements.txt"

if [ ! -f "$BASE_DIR/.gitignore" ]; then
  cat > "$BASE_DIR/.gitignore" <<'GI'
__pycache__/
*.py[cod]
.venv/
venv/
.env
GI
fi
