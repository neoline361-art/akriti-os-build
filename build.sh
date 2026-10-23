#!/usr/bin/env bash
# ==============================================================================
# Akriti OS (Codename: Chameleon) - Master Remastering & Build Pipeline
# Architecture: XFCE 4.18 + Linux Lite / Ubuntu 24.04 LTS Base
# Target: x86_64 Dual BIOS/UEFI Hybrid Live/Installer ISO
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config/base.env
source "${SCRIPT_DIR}/config/base.env"

# Trap errors and unexpected termination to unmount any leaked virtual filesystems
cleanup() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        echo -e "\n${CLR_RED}❌ Build process interrupted or failed with exit code ${exit_code}.${CLR_RESET}" >&2
    fi
    if [[ -d "${ROOTFS_DIR}" ]]; then
        for m in "${ROOTFS_DIR}/run" "${ROOTFS_DIR}/sys" "${ROOTFS_DIR}/proc" "${ROOTFS_DIR}/dev/pts" "${ROOTFS_DIR}/dev"; do
            if mountpoint -q "${m}" 2>/dev/null; then
                echo -e "${CLR_YELLOW}Unmounting active mount: ${m}...${CLR_RESET}"
                umount -l "${m}" 2>/dev/null || true
            fi
        done
    fi
}
trap cleanup EXIT INT TERM

# Ensure root privileges for chroot, mount, and mksquashfs operations
check_root() {
    if [[ $EUID -ne 0 ]]; then
        echo -e "${CLR_RED}❌ Error: build.sh requires root privileges for mount, chroot, and packaging.${CLR_RESET}" >&2
        echo -e "${CLR_YELLOW}Please execute using: sudo ./build.sh [STAGE]${CLR_RESET}" >&2
        exit 1
    fi
}

show_banner() {
    echo -e "${CLR_COPPER}====================================================================${CLR_RESET}"
    echo -e "${CLR_COPPER}  🦎 AKRITI OS (CHAMELEON) — ISO REMASTERING BUILD PIPELINE${CLR_RESET}"
    echo -e "${CLR_COPPER}  Bharat Cyberdeck Edition • Ubuntu 24.04 LTS Noble Base • XFCE 4.18${CLR_RESET}"
    echo -e "${CLR_COPPER}====================================================================${CLR_RESET}"
}

show_help() {
    show_banner
    cat << EOF
Usage:
  sudo ./build.sh [STAGE]

Available Stages:
  all           Execute full pipeline: bootstrap -> chroot -> squashfs -> iso (Default)
  deps          Verify and install build dependencies on host
  bootstrap     Download base ISO and extract rootfs & boot structures
  chroot        Ingest overlays and execute customization hooks in chroot
  squashfs      Compress rootfs into ZSTD squashfs filesystem
  iso           Assemble hybrid dual BIOS/UEFI bootable ISO with xorriso
  clean         Safely unmount filesystems and clean build artifacts
  help          Display this help message

Environment Variables:
  BUILD_MODE    'dev' (fast ZSTD-15, default) or 'prod' (maximum ZSTD-19, 1MB block)
EOF
}

stage_deps() {
    echo -e "${CLR_CYAN}${CLR_BOLD}Checking host build tool dependencies...${CLR_RESET}"
    local MISSING_DEPS=()
    local REQUIRED_BINS=(xorriso mksquashfs unsquashfs rsync curl zstd mcopy mkfs.vfat)

    for bin in "${REQUIRED_BINS[@]}"; do
        if ! command -v "${bin}" >/dev/null 2>&1; then
            MISSING_DEPS+=("${bin}")
        fi
    done

    if [[ ${#MISSING_DEPS[@]} -gt 0 ]]; then
        echo -e "${CLR_YELLOW}Missing build binaries: ${MISSING_DEPS[*]}${CLR_RESET}"
        if command -v apt-get >/dev/null 2>&1; then
            echo -e "${CLR_CYAN}Installing missing tools via apt-get...${CLR_RESET}"
            check_root
            apt-get update -y
            apt-get install -y --no-install-recommends \
                xorriso \
                squashfs-tools \
                rsync \
                curl \
                zstd \
                mtools \
                dosfstools \
                qemu-system-x86
        else
            echo -e "${CLR_RED}Please install missing tools using your system package manager: ${MISSING_DEPS[*]}${CLR_RESET}" >&2
            exit 1
        fi
    else
        echo -e "${CLR_GREEN}✅ All required host build tools are available.${CLR_RESET}"
    fi
}

stage_bootstrap() {
    check_root
    "${SCRIPTS_DIR}/01-extract-iso.sh"
}

stage_chroot() {
    check_root
    "${SCRIPTS_DIR}/02-enter-chroot.sh"
}

stage_squashfs() {
    check_root
    "${SCRIPTS_DIR}/04-pack-squashfs.sh"
}

stage_iso() {
    check_root
    "${SCRIPTS_DIR}/05-build-iso.sh"
}

stage_clean() {
    check_root
    echo -e "${CLR_YELLOW}Cleaning build directories and mountpoints...${CLR_RESET}"
    if [[ -d "${ROOTFS_DIR}" ]]; then
        for m in "${ROOTFS_DIR}/run" "${ROOTFS_DIR}/sys" "${ROOTFS_DIR}/proc" "${ROOTFS_DIR}/dev/pts" "${ROOTFS_DIR}/dev"; do
            if mountpoint -q "${m}" 2>/dev/null; then
                umount -l "${m}" 2>/dev/null || true
            fi
        done
    fi
    rm -rf "${BUILD_DIR}"
    echo -e "${CLR_GREEN}Build directory cleaned.${CLR_RESET}"
}

# Main Dispatcher
STAGE="${1:-all}"

case "${STAGE}" in
    all)
        show_banner
        stage_deps
        stage_bootstrap
        stage_chroot
        stage_squashfs
        stage_iso
        ;;
    deps)
        stage_deps
        ;;
    bootstrap)
        stage_bootstrap
        ;;
    chroot)
        stage_chroot
        ;;
    squashfs)
        stage_squashfs
        ;;
    iso)
        stage_iso
        ;;
    clean)
        stage_clean
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${CLR_RED}Unknown stage: ${STAGE}${CLR_RESET}"
        show_help
        exit 1
        ;;
esac
