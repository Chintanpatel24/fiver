#!/usr/bin/env bash
# fiver updater script
# Usage:
#   ./update.sh
# Or via CLI:
#   fiver --update
set -euo pipefail

REPO_URL="${FIVER_REPO:-https://github.com/Chintanpatel24/fiver.git}"
REF="${FIVER_REF:-main}"

info() { printf '==> %s\n' "$*"; }
warn() { printf '!!  %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

info "Checking for fiver updates..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# If running inside a git repo clone
if [[ -d "$SCRIPT_DIR/.git" ]]; then
  info "Updating local git repository in $SCRIPT_DIR..."
  cd "$SCRIPT_DIR"
  git fetch origin main || true
  git pull origin main || warn "git pull failed; continuing with install"
  if command -v pipx >/dev/null 2>&1; then
    info "Reinstalling package with pipx..."
    pipx install --force .
  else
    info "Reinstalling package in user environment..."
    python3 -m pip install --upgrade --user .
  fi
else
  # Running from standalone install
  if command -v pipx >/dev/null 2>&1; then
    info "Upgrading fiver via pipx..."
    pipx install --force "git+${REPO_URL}@${REF}"
  else
    info "Upgrading fiver via pip/venv..."
    python3 -m pip install --upgrade --user "git+${REPO_URL}@${REF}"
  fi
fi

info "fiver successfully updated!"
if command -v fiver >/dev/null 2>&1; then
  fiver --version || true
fi
