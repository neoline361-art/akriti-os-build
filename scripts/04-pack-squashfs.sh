#!/usr/bin/env bash
# ==============================================================================
# Akriti OS - Remastering Script 04: Compress RootFS to SquashFS (ZSTD)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config/base.env
source "${SCRIPT_DIR}/../config/base.env"

if [[ $EUID -ne 0 ]]; then
    echo -e "${CLR_RED}Error: This script must be run as root (sudo).${CLR_RESET}" >&2
    exit 1
fi

echo -e "${CLR_CYAN}${CLR_BOLD}=== Stage 4: RootFS SquashFS Compression (ZSTD) ===${CLR_RESET}"

CASPER_DIR="${ISO_EXTRACT_DIR}/casper"
mkdir -p "${CASPER_DIR}"

# 1. Generate filesystem.manifest and filesystem.size
echo -e "${CLR_CYAN}Generating package manifests and filesystem size metrics...${CLR_RESET}"
chroot "${ROOTFS_DIR}" dpkg-query -W --showformat='${Package} ${Version}\n' > "${CASPER_DIR}/filesystem.manifest"
cp "${CASPER_DIR}/filesystem.manifest" "${CASPER_DIR}/filesystem.manifest-remove"

# Calculate uncompressed size in bytes
du -sx --block-size=1 "${ROOTFS_DIR}" | cut -f1 > "${CASPER_DIR}/filesystem.size"

# 2. Determine ZSTD compression level
if [[ "${BUILD_MODE}" == "prod" ]]; then
    COMP_LEVEL="${SQUASHFS_LEVEL_PROD}"
    EXTRA_FLAGS="-b ${SQUASHFS_BLOCK_SIZE}"
    echo -e "${CLR_COPPER}Production Build: Using ZSTD level ${COMP_LEVEL} with ${SQUASHFS_BLOCK_SIZE} block size...${CLR_RESET}"
else
    COMP_LEVEL="${SQUASHFS_LEVEL_DEV}"
    EXTRA_FLAGS=""
    echo -e "${CLR_COPPER}Development Build: Using fast ZSTD level ${COMP_LEVEL}...${CLR_RESET}"
fi

# 3. Remove all old squashfs images in casper directory to avoid duplicate/stale layers
rm -f "${CASPER_DIR}"/*.squashfs

# 4. Pack Squashfs using ZSTD
echo -e "${CLR_CYAN}Compressing RootFS with mksquashfs (ZSTD)...${CLR_RESET}"
# shellcheck disable=SC2086
mksquashfs "${ROOTFS_DIR}" "${CASPER_DIR}/filesystem.squashfs" \
    -comp "${SQUASHFS_COMP}" \
    -Xcompression-level "${COMP_LEVEL}" \
    ${EXTRA_FLAGS} \
    -noappend \
    -wildcards \
    -e "var/cache/apt/archives/*" \
    -e "tmp/*" \
    -e "var/tmp/*"

# 5. Update md5sum / sha256 metrics for Casper integrity check
echo -e "${CLR_CYAN}Updating casper md5sum manifest...${CLR_RESET}"
(
    cd "${ISO_EXTRACT_DIR}"
    rm -f md5sum.txt
    find . -type f ! -name "md5sum.txt" ! -path "./boot/grub/*" ! -path "./isolinux/*" -exec md5sum {} + > md5sum.txt
)

echo -e "${CLR_GREEN}${CLR_BOLD}Stage 4 SquashFS Packaging Complete!${CLR_RESET}"
