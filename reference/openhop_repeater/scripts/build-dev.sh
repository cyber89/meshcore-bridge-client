#!/bin/bash
# Build development .deb package for openhop-repeater
# Allows building from untagged commits with ~dev version suffix

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Change to project root
cd "$(dirname "$0")/.."
PROJECT_ROOT=$(pwd)

log_info "Building development .deb package for openhop-repeater..."
log_info "Project root: $PROJECT_ROOT"

# Check if we're in a git repository
if [ ! -d .git ]; then
    log_error "Not in a git repository. Cannot use setuptools_scm."
    exit 1
fi

# Get version from setuptools_scm
log_step "Detecting version from git..."
if ! command -v python3 &> /dev/null; then
    log_error "python3 not found. Please install python3."
    exit 1
fi

# Try to get version from setuptools_scm
VERSION=$(python3 -m setuptools_scm 2>/dev/null || echo "")

if [ -z "$VERSION" ]; then
    log_error "Failed to get version from setuptools_scm."
    log_error "Make sure setuptools_scm is installed: pip3 install setuptools_scm"
    exit 1
fi

log_info "Detected version: $VERSION"

# Convert version to Debian format
# setuptools_scm format: 1.0.5.post3.dev0 or 1.0.5.dev3+g123abc
# Debian format: 1.0.5~dev3
DEBIAN_VERSION=$(echo "$VERSION" | sed -E 's/\.post([0-9]+).*$/~dev\1/' | sed -E 's/\.dev([0-9]+).*$/~dev\1/' | sed -E 's/\+.*$//')

log_info "Debian version: $DEBIAN_VERSION"

# Update debian/changelog
log_step "Updating debian/changelog..."
CHANGELOG_DATE=$(date -R)
cat > debian/changelog << EOF
openhop-repeater ($DEBIAN_VERSION) unstable; urgency=medium

  * Development build from git commit $(git rev-parse --short HEAD)
  * Version: $VERSION

 -- Rightup <rightup@pymc.dev>  $CHANGELOG_DATE
EOF

log_info "Changelog updated with version $DEBIAN_VERSION"

# Clean previous builds
log_step "Cleaning previous builds..."
rm -rf debian/openhop-repeater/
rm -rf debian/.debhelper/
rm -rf debian/files
rm -f debian/openhop-repeater.*.debhelper
rm -f debian/openhop-repeater.substvars
rm -f debian/*.log
rm -rf .pybuild/
rm -rf build/
rm -rf *.egg-info/
rm -f repeater/_version.py
rm -f ../*.deb
rm -f ../*.buildinfo
rm -f ../*.changes

# Build the package
log_step "Building .deb package..."
log_info "This may take a few minutes..."

# Build without signing (development builds don't need to be signed)
if debuild -us -uc -b 2>&1 | tee /tmp/debuild-dev.log; then
    log_info "Build successful!"
else
    log_error "Build failed. Check /tmp/debuild-dev.log for details."
    exit 1
fi

# Find and display the built package
DEB_FILE=$(find .. -maxdepth 1 -name "openhop-repeater_${DEBIAN_VERSION}_*.deb" -type f | head -n 1)

if [ -n "$DEB_FILE" ]; then
    log_info ""
    log_info "════════════════════════════════════════════════════════════"
    log_info "Build complete!"
    log_info "Package: $(basename "$DEB_FILE")"
    log_info "Location: $DEB_FILE"
    log_info "Size: $(du -h "$DEB_FILE" | cut -f1)"
    log_info "════════════════════════════════════════════════════════════"
    log_info ""
    log_info "To install:"
    log_info "  sudo dpkg -i $DEB_FILE"
    log_info ""
    log_info "To inspect package contents:"
    log_info "  dpkg-deb -c $DEB_FILE"
    log_info ""
    log_info "To check package info:"
    log_info "  dpkg-deb -I $DEB_FILE"
else
    log_warn "Built package not found in expected location"
    log_info "Searching for .deb files in parent directory..."
    ls -lh ../*.deb 2>/dev/null || log_warn "No .deb files found"
fi
