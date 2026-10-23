# ==============================================================================
# Akriti OS (Chameleon) - Makefile
# Ergonomic targets for building, packaging, and testing Akriti OS ISO images
# ==============================================================================

SHELL := /usr/bin/env bash
include config/base.env

.PHONY: all help deps bootstrap chroot squashfs iso test-qemu test-qemu-uefi clean distclean

# Default target
all: deps bootstrap chroot squashfs iso
	@echo -e "$(CLR_GREEN)$(CLR_BOLD)🎉 Full build pipeline completed successfully!$(CLR_RESET)"
	@echo -e "$(CLR_WHITE)ISO Location: $(OUTPUT_DIR)/$(ISO_FILENAME)$(CLR_RESET)"

help:
	@echo -e "$(CLR_COPPER)$(CLR_BOLD)Akriti OS (Chameleon) Build System$(CLR_RESET)"
	@echo ""
	@echo "Available make targets:"
	@echo "  make deps          - Check and install required host build utilities"
	@echo "  make bootstrap     - Download base ISO and extract rootfs and boot files"
	@echo "  make chroot        - Apply overlay and run customization hooks in chroot"
	@echo "  make squashfs      - Compress rootfs using ZSTD into filesystem.squashfs"
	@echo "  make iso           - Build hybrid dual BIOS/UEFI bootable ISO with xorriso"
	@echo "  make test-qemu     - Run generated ISO in QEMU (BIOS mode, 2GB RAM)"
	@echo "  make test-qemu-uefi- Run generated ISO in QEMU (UEFI mode via OVMF)"
	@echo "  make clean         - Safely unmount filesystems and purge build directory"
	@echo "  make distclean     - Purge build directory and cached base ISO images"
	@echo ""
	@echo "Configuration flags:"
	@echo "  BUILD_MODE=prod make iso   # Build with maximum ZSTD-19 compression"

deps:
	@./build.sh deps

bootstrap:
	@sudo ./build.sh bootstrap

chroot:
	@sudo ./build.sh chroot

squashfs:
	@sudo ./build.sh squashfs

iso:
	@sudo ./build.sh iso

test-qemu:
	@ISO_PATH="$(OUTPUT_DIR)/$(ISO_FILENAME)"; \
	if [[ ! -f "$${ISO_PATH}" ]]; then \
		echo "❌ ISO not found at $${ISO_PATH}. Run 'make iso' first."; \
		exit 1; \
	fi; \
	KVM_FLAG=""; \
	if [ -e /dev/kvm ] && [ -r /dev/kvm ] && [ -w /dev/kvm ]; then \
		KVM_FLAG="-enable-kvm -cpu host"; \
	fi; \
	echo "🚀 Launching Akriti OS in QEMU (BIOS mode, 2GB RAM)..."; \
	qemu-system-x86_64 $${KVM_FLAG} \
		-m 2048 \
		-smp 2 \
		-vga virtio \
		-cdrom "$${ISO_PATH}" \
		-boot d

test-qemu-uefi:
	@ISO_PATH="$(OUTPUT_DIR)/$(ISO_FILENAME)"; \
	if [[ ! -f "$${ISO_PATH}" ]]; then \
		echo "❌ ISO not found at $${ISO_PATH}. Run 'make iso' first."; \
		exit 1; \
	fi; \
	OVMF_BIOS=""; \
	for p in /usr/share/OVMF/OVMF_CODE.fd /usr/share/ovmf/OVMF.fd /usr/share/qemu/OVMF.fd; do \
		if [[ -f "$$p" ]]; then OVMF_BIOS="$$p"; break; fi; \
	done; \
	if [[ -z "$${OVMF_BIOS}" ]]; then \
		echo "❌ OVMF UEFI firmware not found. Please install ovmf package."; \
		exit 1; \
	fi; \
	KVM_FLAG=""; \
	if [ -e /dev/kvm ] && [ -r /dev/kvm ] && [ -w /dev/kvm ]; then \
		KVM_FLAG="-enable-kvm -cpu host"; \
	fi; \
	echo "🚀 Launching Akriti OS in QEMU (UEFI mode via $${OVMF_BIOS})..."; \
	qemu-system-x86_64 $${KVM_FLAG} \
		-bios "$${OVMF_BIOS}" \
		-m 2048 \
		-smp 2 \
		-vga virtio \
		-cdrom "$${ISO_PATH}" \
		-boot d

clean:
	@sudo ./build.sh clean

distclean: clean
	@echo "Purging cached base ISOs..."
	@rm -rf cache
