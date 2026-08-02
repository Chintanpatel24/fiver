#!/usr/bin/env bash
# fiver one-line installer
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Chintanpatel24/fiver/main/install.sh | bash
# Or from a local clone:
#   ./install.sh
set -euo pipefail

REPO_URL="${FIVER_REPO:-https://github.com/Chintanpatel24/fiver.git}"
REF="${FIVER_REF:-main}"

info() { printf '==> %s\n' "$*"; }
warn() { printf '!!  %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

need_python() {
  if command -v python3 >/dev/null 2>&1; then
    PY=python3
  elif command -v python >/dev/null 2>&1; then
    PY=python
  else
    die "Python 3.9+ is required. Install python3, then re-run this installer."
  fi
  ver="$($PY -c 'import sys; print("%d.%d"%sys.version_info[:2])')"
  $PY -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' \
    || die "Python 3.9+ required (found $ver)"
  info "Python $ver ($PY)"
}

install_fiver() {
  need_python

  # Prefer pipx (best for CLI apps on modern distros / PEP 668)
  if command -v pipx >/dev/null 2>&1; then
    info "Installing with pipx..."
    if [[ -f pyproject.toml ]]; then
      UV_VENV_CLEAR=1 pipx install --force .
    else
      UV_VENV_CLEAR=1 pipx install --force "git+${REPO_URL}@${REF}"
    fi
    return 0
  fi

  # Fallback: dedicated venv + symlink into ~/.local/bin (no system site-packages)
  info "pipx not found — installing into a user venv"
  local venv_dir="${XDG_DATA_HOME:-$HOME/.local/share}/fiver-venv"
  local bindir="${XDG_BIN_HOME:-$HOME/.local/bin}"
  mkdir -p "$bindir"

  if [[ ! -d "$venv_dir" ]]; then
    $PY -m venv "$venv_dir"
  fi
  # shellcheck disable=SC1091
  source "$venv_dir/bin/activate"
  python -m pip install -U pip setuptools wheel >/dev/null

  if [[ -f pyproject.toml ]]; then
    python -m pip install --upgrade --force-reinstall .
  else
    python -m pip install --upgrade --force-reinstall "git+${REPO_URL}@${REF}"
  fi

  ln -sfn "$venv_dir/bin/fiver" "$bindir/fiver"
  info "Linked $bindir/fiver -> $venv_dir/bin/fiver"

  if [[ ":$PATH:" != *":$bindir:"* ]]; then
    warn "Add to PATH:  export PATH=\"$bindir:\$PATH\""
  fi

  warn "Tip: install pipx for cleaner upgrades:  sudo pacman -S python-pipx   # or apt install pipx"
}

check_host_tools() {
  info "Checking host tools (adb + scrcpy)..."
  miss=0
  command -v adb >/dev/null 2>&1 || miss=1
  command -v scrcpy >/dev/null 2>&1 || miss=1
  if [[ "$miss" -ne 0 ]]; then
    warn "adb and/or scrcpy not found. Install them next:"
    cat <<'EOF'
  Arch / CachyOS:  sudo pacman -S scrcpy android-tools
  Debian / Ubuntu: sudo apt update && sudo apt install -y scrcpy adb
  Fedora:          sudo dnf install -y scrcpy android-tools
  macOS:           brew install scrcpy android-platform-tools
  Windows:         winget install Genymobile.scrcpy Google.PlatformTools
EOF
  else
    info "Found adb and scrcpy"
  fi
}

main() {
  info "fiver installer"
  install_fiver
  check_host_tools

  if command -v fiver >/dev/null 2>&1; then
    info "Installed: $(command -v fiver)"
    fiver --version || true
  else
    warn "fiver binary not on PATH yet — open a new shell or fix PATH (see above)"
  fi

  cat <<'EOF'

Next:
  fiver --doctor
  fiver --init
  fiver --start

Phone (one-time): enable USB debugging, plug in, tap Allow.
Stop anytime:     fiver --stop
EOF
}

main "$@"
