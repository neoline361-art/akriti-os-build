#!/usr/bin/env bash
# ==============================================================================
# Akriti OS - Remastering Script 01: Extract Base ISO & RootFS
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config/base.env
source "${SCRIPT_DIR}/../config/base.env"

if [[ $EUID -ne 0 ]]; then
    echo -e "${CLR_RED}Error: This script must be run as root (sudo).${CLR_RESET}" >&2
    exit 1
fi

echo -e "${CLR_CYAN}${CLR_BOLD}=== Stage 1: Base ISO Extraction & Preparation ===${CLR_RESET}"

mkdir -p "${BUILD_DIR}" "${CACHE_DIR}" "${ROOTFS_DIR}" "${ISO_EXTRACT_DIR}" "${OUTPUT_DIR}"

BASE_ISO_PATH="${CACHE_DIR}/${BASE_ISO_NAME}"

# 1. Download Base ISO if not already cached
if [[ ! -f "${BASE_ISO_PATH}" ]]; then
    echo -e "${CLR_YELLOW}Base ISO not found in cache. Attempting download...${CLR_RESET}"
    if curl -fL --retry 3 "${BASE_ISO_URL}" -o "${BASE_ISO_PATH}"; then
        echo -e "${CLR_GREEN}Downloaded ${BASE_ISO_NAME} successfully.${CLR_RESET}"
    else
        echo -e "${CLR_YELLOW}Upstream Linux Lite download unavailable, falling back to Ubuntu 24.04 LTS...${CLR_RESET}"
        BASE_ISO_PATH="${CACHE_DIR}/${BASE_ISO_FALLBACK_NAME}"
        if [[ ! -f "${BASE_ISO_PATH}" ]]; then
            curl -fL --retry 3 "${BASE_ISO_FALLBACK_URL}" -o "${BASE_ISO_PATH}"
        fi
    fi
fi

# 2. Mount and extract ISO filesystem
MNT_ISO="$(mktemp -d /tmp/akriti-iso-mnt.XXXXXX)"
cleanup() {
    if mountpoint -q "${MNT_ISO}"; then
        umount "${MNT_ISO}" || true
    fi
    rm -rf "${MNT_ISO}"
}
trap cleanup EXIT INT TERM

echo -e "${CLR_CYAN}Mounting base ISO: ${BASE_ISO_PATH}...${CLR_RESET}"
mount -o loop,ro "${BASE_ISO_PATH}" "${MNT_ISO}"

echo -e "${CLR_CYAN}Extracting ISO boot structure to: ${ISO_EXTRACT_DIR}...${CLR_RESET}"
rm -rf "${ISO_EXTRACT_DIR}"
mkdir -p "${ISO_EXTRACT_DIR}"
# Copy everything except casper filesystem.squashfs first for speed
rsync -a --exclude="casper/filesystem.squashfs" "${MNT_ISO}/" "${ISO_EXTRACT_DIR}/"

# 3. Extract Squashfs RootFS
SQUASHFS_SOURCE=""
if [[ -f "${MNT_ISO}/casper/filesystem.squashfs" ]]; then
    SQUASHFS_SOURCE="${MNT_ISO}/casper/filesystem.squashfs"
elif [[ -f "${MNT_ISO}/live/filesystem.squashfs" ]]; then
    SQUASHFS_SOURCE="${MNT_ISO}/live/filesystem.squashfs"
else
    echo -e "${CLR_RED}Error: Could not locate filesystem.squashfs inside ISO.${CLR_RESET}" >&2
    exit 1
fi

echo -e "${CLR_CYAN}Unsquashing rootfs (${SQUASHFS_SOURCE}) into ${ROOTFS_DIR}...${CLR_RESET}"
rm -rf "${ROOTFS_DIR}"
unsquashfs -d "${ROOTFS_DIR}" "${SQUASHFS_SOURCE}"

echo -e "${CLR_GREEN}${CLR_BOLD}Stage 1 Extraction Complete!${CLR_RESET}"
