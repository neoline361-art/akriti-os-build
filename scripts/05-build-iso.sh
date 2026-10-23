#!/usr/bin/env bash
# ==============================================================================
# Akriti OS - Remastering Script 05: Build Hybrid Dual BIOS/UEFI ISO with Xorriso
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config/base.env
source "${SCRIPT_DIR}/../config/base.env"

if [[ $EUID -ne 0 ]]; then
    echo -e "${CLR_RED}Error: This script must be run as root (sudo).${CLR_RESET}" >&2
    exit 1
fi

echo -e "${CLR_CYAN}${CLR_BOLD}=== Stage 5: Hybrid Dual BIOS / UEFI ISO Generation ===${CLR_RESET}"

mkdir -p "${OUTPUT_DIR}"
OUTPUT_ISO="${OUTPUT_DIR}/${ISO_FILENAME}"

# 1. Ingest ISO Overlays (GRUB config, bootsplash, etc.)
if [[ -d "${ISO_OVERLAY_DIR}" ]]; then
    echo -e "${CLR_CYAN}Applying ISO overlay (GRUB bootloader configurations)...${CLR_RESET}"
    cp -a "${ISO_OVERLAY_DIR}/." "${ISO_EXTRACT_DIR}/"
fi

# 2. Check EFI Boot Image
EFI_IMG_PATH=""
if [[ -f "${ISO_EXTRACT_DIR}/boot/grub/efi.img" ]]; then
    EFI_IMG_PATH="${ISO_EXTRACT_DIR}/boot/grub/efi.img"
elif [[ -f "${ISO_EXTRACT_DIR}/EFI/BOOT/bootx64.efi" || -f "${ISO_EXTRACT_DIR}/EFI/boot/bootx64.efi" ]]; then
    echo -e "${CLR_YELLOW}Generating missing FAT efi.img from EFI directory...${CLR_RESET}"
    EFI_IMG_PATH="${ISO_EXTRACT_DIR}/boot/grub/efi.img"
    mkdir -p "$(dirname "${EFI_IMG_PATH}")"
    truncate -s 4M "${EFI_IMG_PATH}"
    mkfs.vfat "${EFI_IMG_PATH}"
    mcopy -s -i "${EFI_IMG_PATH}" "${ISO_EXTRACT_DIR}/EFI" ::/
elif [[ -f "${ISO_EXTRACT_DIR}/efi.img" ]]; then
    EFI_IMG_PATH="${ISO_EXTRACT_DIR}/efi.img"
fi

# 3. Detect BIOS El Torito Bootloader (Isolinux or GRUB i386-pc)
BIOS_ARGS=()
if [[ -f "${ISO_EXTRACT_DIR}/isolinux/isolinux.bin" ]]; then
    echo -e "${CLR_CYAN}Detected Isolinux BIOS bootloader.${CLR_RESET}"
    BIOS_ARGS=(
        -b isolinux/isolinux.bin
        -c isolinux/boot.cat
        -no-emul-boot
        -boot-load-size 4
        -boot-info-table
    )
elif [[ -f "${ISO_EXTRACT_DIR}/boot/grub/i386-pc/eltorito.img" ]]; then
    echo -e "${CLR_CYAN}Detected GRUB i386-pc BIOS bootloader.${CLR_RESET}"
    BIOS_ARGS=(
        -b boot/grub/i386-pc/eltorito.img
        -no-emul-boot
        -boot-load-size 4
        -boot-info-table
    )
fi

# 4. Construct UEFI Boot Arguments
UEFI_ARGS=()
if [[ -n "${EFI_IMG_PATH}" && -f "${EFI_IMG_PATH}" ]]; then
    REL_EFI_PATH="${EFI_IMG_PATH#$ISO_EXTRACT_DIR/}"
    echo -e "${CLR_CYAN}Configuring UEFI El Torito and GPT partition 2 (efi.img: ${REL_EFI_PATH})...${CLR_RESET}"
    UEFI_ARGS=(
        -eltorito-alt-boot
        -e "${REL_EFI_PATH}"
        -no-emul-boot
        -isohybrid-gpt-basdat
        -append_partition 2 0xef "${EFI_IMG_PATH}"
    )
fi

# 5. Execute Xorriso to build Hybrid ISO
echo -e "${CLR_COPPER}Executing Xorriso to generate: ${OUTPUT_ISO}...${CLR_RESET}"
rm -f "${OUTPUT_ISO}"

xorriso -as mkisofs \
    -r \
    -V "${ISO_VOLID}" \
    -o "${OUTPUT_ISO}" \
    -J -l \
    "${BIOS_ARGS[@]}" \
    "${UEFI_ARGS[@]}" \
    "${ISO_EXTRACT_DIR}"

# 6. Generate SHA256 Checksum
echo -e "${CLR_CYAN}Computing SHA256 Checksum...${CLR_RESET}"
(
    cd "${OUTPUT_DIR}"
    sha256sum "${ISO_FILENAME}" > "${ISO_FILENAME}.sha256"
)

echo -e "${CLR_GREEN}${CLR_BOLD}======================================================${CLR_RESET}"
echo -e "${CLR_GREEN}${CLR_BOLD}✨ Akriti OS ISO Generated Successfully!${CLR_RESET}"
echo -e "${CLR_WHITE}ISO Image: ${OUTPUT_ISO}${CLR_RESET}"
echo -e "${CLR_WHITE}Checksum:  ${OUTPUT_ISO}.sha256${CLR_RESET}"
echo -e "${CLR_GREEN}${CLR_BOLD}======================================================${CLR_RESET}"
