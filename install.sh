#!/usr/bin/env bash
# CrabPot Installer — curl -fsSL https://crabpot.run/install.sh | sh
set -euo pipefail

CRABPOT_VERSION="1.0.0"
CRABPOT_HOME="${CRABPOT_HOME:-$HOME/.crabpot}"
REPO_URL="https://github.com/OWNER/crabpot"  # TODO: set real repo

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[info]${NC}  $*"; }
ok()    { echo -e "${GREEN}[ok]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC}  $*"; }
fail()  { echo -e "${RED}[fail]${NC}  $*"; exit 1; }

echo ""
echo -e "${CYAN}CrabPot v${CRABPOT_VERSION} — Secure OpenClaw Sandbox${NC}"
echo "================================================"
echo ""

# ── 1. Check platform ────────────────────────────────────────────────
if [[ "$(uname -s)" != "Linux" ]]; then
    fail "CrabPot requires Linux or WSL2. Detected: $(uname -s)"
fi

ARCH="$(uname -m)"
if [[ "$ARCH" != "x86_64" && "$ARCH" != "aarch64" ]]; then
    fail "Unsupported architecture: $ARCH (need x86_64 or aarch64)"
fi

IS_WSL=false
if grep -qi microsoft /proc/version 2>/dev/null; then
    IS_WSL=true
    info "WSL2 detected"
else
    info "Native Linux detected"
fi

# ── 2. Check / install Docker ────────────────────────────────────────
if command -v docker &>/dev/null; then
    ok "Docker found: $(docker --version)"
else
    info "Installing Docker..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq ca-certificates curl gnupg
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
        sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update -qq
    sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    sudo usermod -aG docker "$USER"
    ok "Docker installed (you may need to log out/in for group changes)"
fi

# ── 3. Check / install Python 3.8+ ──────────────────────────────────
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
    if [[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 8 ]]; then
        ok "Python $PY_VERSION found"
    else
        fail "Python 3.8+ required, found $PY_VERSION"
    fi
else
    info "Installing Python 3..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3 python3-pip python3-venv
    ok "Python 3 installed"
fi

# ── 4. Create CrabPot home directory ─────────────────────────────────
info "Creating $CRABPOT_HOME ..."
mkdir -p "$CRABPOT_HOME"/{bin,venv,config,data}
ok "Directory structure created"

# ── 5. Create Python virtual environment ─────────────────────────────
info "Setting up Python virtual environment..."
python3 -m venv "$CRABPOT_HOME/venv"
"$CRABPOT_HOME/venv/bin/pip" install --upgrade pip -q
ok "Virtual environment created"

# ── 6. Install crabpot package ───────────────────────────────────────
info "Installing CrabPot..."

# For local development: install from local source if available
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/pyproject.toml" ]]; then
    info "Installing from local source..."
    "$CRABPOT_HOME/venv/bin/pip" install "$SCRIPT_DIR" -q
else
    # Production: download release tarball
    TARBALL_URL="${REPO_URL}/releases/download/v${CRABPOT_VERSION}/crabpot-${CRABPOT_VERSION}.tar.gz"
    info "Downloading crabpot v${CRABPOT_VERSION}..."
    "$CRABPOT_HOME/venv/bin/pip" install "$TARBALL_URL" -q
fi
ok "CrabPot installed"

# ── 7. Create wrapper script ─────────────────────────────────────────
cat > "$CRABPOT_HOME/bin/crabpot" << 'WRAPPER'
#!/usr/bin/env bash
exec "$HOME/.crabpot/venv/bin/python" -m crabpot "$@"
WRAPPER
chmod +x "$CRABPOT_HOME/bin/crabpot"
ok "Wrapper script created"

# ── 8. Add to PATH ──────────────────────────────────────────────────
PATH_LINE='export PATH="$HOME/.crabpot/bin:$PATH"'
ADDED_PATH=false

for rcfile in "$HOME/.bashrc" "$HOME/.zshrc"; do
    if [[ -f "$rcfile" ]]; then
        if ! grep -qF '.crabpot/bin' "$rcfile"; then
            echo "" >> "$rcfile"
            echo "# CrabPot" >> "$rcfile"
            echo "$PATH_LINE" >> "$rcfile"
            ADDED_PATH=true
        fi
    fi
done

if $ADDED_PATH; then
    ok "Added to PATH in shell config"
else
    ok "PATH already configured"
fi

# ── 9. Done ──────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  CrabPot v${CRABPOT_VERSION} installed!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "Next steps:"
echo "  1. Restart your shell or run:"
echo -e "     ${CYAN}export PATH=\"\$HOME/.crabpot/bin:\$PATH\"${NC}"
echo ""
echo "  2. Initialize and set up:"
echo -e "     ${CYAN}crabpot init${NC}     # Verify prerequisites"
echo -e "     ${CYAN}crabpot setup${NC}    # Build image + onboarding"
echo -e "     ${CYAN}crabpot start${NC}    # Launch everything"
echo ""
