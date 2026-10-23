#!/usr/bin/env bash
# ==============================================================================
# Akriti OS - Remastering Script 02: Enter Chroot & Execute Build Hooks
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config/base.env
source "${SCRIPT_DIR}/../config/base.env"

if [[ $EUID -ne 0 ]]; then
    echo -e "${CLR_RED}Error: This script must be run as root (sudo).${CLR_RESET}" >&2
    exit 1
fi

if [[ ! -d "${ROOTFS_DIR}" || ! -f "${ROOTFS_DIR}/bin/bash" ]]; then
    echo -e "${CLR_RED}Error: RootFS not found at ${ROOTFS_DIR}. Run stage 01 first.${CLR_RESET}" >&2
    exit 1
fi

echo -e "${CLR_CYAN}${CLR_BOLD}=== Stage 2: Chroot Environment Execution ===${CLR_RESET}"

# 1. Mount virtual kernel filesystems
echo -e "${CLR_CYAN}Mounting virtual filesystems in chroot...${CLR_RESET}"
mount --bind /dev "${ROOTFS_DIR}/dev"
mount --bind /dev/pts "${ROOTFS_DIR}/dev/pts"
mount -t proc proc "${ROOTFS_DIR}/proc"
mount -t sysfs sysfs "${ROOTFS_DIR}/sys"
mount --bind /run "${ROOTFS_DIR}/run"

cleanup_mounts() {
    echo -e "${CLR_YELLOW}Unmounting virtual filesystems from chroot...${CLR_RESET}"
    for m in "${ROOTFS_DIR}/run" "${ROOTFS_DIR}/sys" "${ROOTFS_DIR}/proc" "${ROOTFS_DIR}/dev/pts" "${ROOTFS_DIR}/dev"; do
        if mountpoint -q "${m}"; then
            umount -l "${m}" || true
        fi
    done
}
trap cleanup_mounts EXIT INT TERM

# 2. Ingest DNS and Host Resolution
cp -L /etc/resolv.conf "${ROOTFS_DIR}/etc/resolv.conf"

# 3. Stage Calamares configuration files inside chroot
mkdir -p "${ROOTFS_DIR}/opt/akriti-build/calamares"
cp -rf "${CALAMARES_CONFIG_DIR}/"* "${ROOTFS_DIR}/opt/akriti-build/calamares/"

# 4. Copy Overlay Tree into RootFS
if [[ -d "${OVERLAY_DIR}" ]]; then
    echo -e "${CLR_CYAN}Applying filesystem overlay tree to rootfs...${CLR_RESET}"
    cp -a "${OVERLAY_DIR}/." "${ROOTFS_DIR}/"
fi

# 5. Execute Chroot Customization Hooks in sequence
HOOK_SCRIPTS=(
    "01-strip-bloat.chroot"
    "02-install-core.chroot"
    "03-configure-xfce.chroot"
    "04-cleanup-rootfs.chroot"
)

mkdir -p "${ROOTFS_DIR}/tmp/hooks"
for hook in "${HOOK_SCRIPTS[@]}"; do
    hook_file="${HOOKS_DIR}/${hook}"
    if [[ -f "${hook_file}" ]]; then
        echo -e "${CLR_COPPER}Executing Hook: ${hook}...${CLR_RESET}"
        cp "${hook_file}" "${ROOTFS_DIR}/tmp/hooks/${hook}"
        chmod +x "${ROOTFS_DIR}/tmp/hooks/${hook}"
        chroot "${ROOTFS_DIR}" "/tmp/hooks/${hook}"
    else
        echo -e "${CLR_YELLOW}Warning: Hook ${hook_file} not found, skipping.${CLR_RESET}"
    fi
done

# Clean up hooks and staging directory inside rootfs
rm -rf "${ROOTFS_DIR}/tmp/hooks"
rm -rf "${ROOTFS_DIR}/opt/akriti-build"

echo -e "${CLR_GREEN}${CLR_BOLD}Stage 2 Chroot Customization Complete!${CLR_RESET}"
