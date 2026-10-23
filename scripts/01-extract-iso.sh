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
# Copy ISO filesystem structure excluding all .squashfs files
rsync -a --exclude="*.squashfs" "${MNT_ISO}/" "${ISO_EXTRACT_DIR}/"

# 3. Discover and Extract Squashfs RootFS layers
echo -e "${CLR_CYAN}Discovering SquashFS layers inside mounted ISO...${CLR_RESET}"
mapfile -t SQUASHFS_FILES < <(find "${MNT_ISO}" -type f -name "*.squashfs" | sort)

if [[ ${#SQUASHFS_FILES[@]} -eq 0 ]]; then
    echo -e "${CLR_RED}Error: Could not locate any .squashfs files inside ISO.${CLR_RESET}" >&2
    exit 1
fi

echo -e "${CLR_COPPER}Found ${#SQUASHFS_FILES[@]} SquashFS file(s):${CLR_RESET}"
for sq in "${SQUASHFS_FILES[@]}"; do
    echo "  - $(basename "${sq}") ($(du -h "${sq}" | cut -f1))"
done

# Prepare clean ROOTFS_DIR
rm -rf "${ROOTFS_DIR}"
mkdir -p "${ROOTFS_DIR}"

# Categorize base rootfs vs overlay layers
PRIMARY_SQUASH=""
OVERLAY_SQUASHES=()

for sq in "${SQUASHFS_FILES[@]}"; do
    fname="$(basename "${sq}")"
    if [[ "${fname}" == "filesystem.squashfs" || "${fname}" == "minimal.squashfs" || "${fname}" =~ minimal\.standard\.squashfs ]]; then
        PRIMARY_SQUASH="${sq}"
    else
        OVERLAY_SQUASHES+=("${sq}")
    fi
done

# If no named primary matched, pick the largest squashfs file
if [[ -z "${PRIMARY_SQUASH}" ]]; then
    PRIMARY_SQUASH="${SQUASHFS_FILES[0]}"
    OVERLAY_SQUASHES=("${SQUASHFS_FILES[@]:1}")
fi

echo -e "${CLR_CYAN}Unsquashing primary rootfs (${PRIMARY_SQUASH}) into ${ROOTFS_DIR}...${CLR_RESET}"
unsquashfs -f -d "${ROOTFS_DIR}" "${PRIMARY_SQUASH}"

# Unpack any auxiliary layers (live session tools, overlays) on top
for ov in "${OVERLAY_SQUASHES[@]}"; do
    echo -e "${CLR_CYAN}Unsquashing overlay layer (${ov}) into ${ROOTFS_DIR}...${CLR_RESET}"
    unsquashfs -f -d "${ROOTFS_DIR}" "${ov}"
done

echo -e "${CLR_GREEN}${CLR_BOLD}Stage 1 Extraction Complete!${CLR_RESET}"
