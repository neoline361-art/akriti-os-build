# 🦎 Akriti OS (Bharat Cyberdeck) — ISO Remastering Build System

> **Product Name:** Akriti OS (Chameleon Edition)  
> **Foundation:** Ubuntu 24.04 LTS (Noble Numbat) / Linux Lite 7.0 Base  
> **Desktop Environment:** XFCE 4.18 with Sutra Workspaces & Chameleon Theme Engine  
> **Target Devices:** Netbooks (1024x600 TN screens), Desktop PCs, Laptops, DIY Cyberdecks

---

## 📖 Overview

The **Akriti OS Build System** is an automated, reproducible chroot + SquashFS remastering pipeline that transforms an Ubuntu / Linux Lite foundation into **Akriti OS**—an offline-first, multilingual educational operating system engineered for students, makers, and teachers across India.

### Key Architectural Pillars
- **Anti-Cascade APT Stripping:** Uses an explicit `apt-mark manual` desktop stack protection list to purge bloat without breaking XFCE, LightDM, or NetworkManager.
- **2GB RAM Performance Optimization:** Integrated 150% ZRAM memory compression (`ALGO=zstd`) with aggressive swappiness tuning (`vm.swappiness=180`) preventing OOM freezes on low-cost netbooks.
- **Unprivileged Sandboxing:** Syctl tuning unblocks Ubuntu 24.04 AppArmor restrictions, allowing Bubblewrap (`bwrap`) to provide zero-risk scratchpads.
- **Lightweight Multilingual Typing:** Standardized on Fcitx5 IME (`fcitx5-m17n`), saving ~24MB RAM compared to IBus while providing native InScript and Phonetic keyboards.
- **Hybrid Dual BIOS / UEFI Booting:** Generates universal hybrid ISOs using `xorriso` with EFI partition 2 appending and support for Live, Persistent, and Toram boot modes.
- **Netbook-Hardened Calamares:** Constrained to 780x500px window geometry to eliminate button clipping on 1024x600 displays.

---

## 📁 Repository Directory Structure

```text
akriti-os-build/
├── build.sh                       # Master build orchestrator with stages and root checks
├── Makefile                       # Ergonomic targets (make deps, chroot, squashfs, iso, test-qemu)
├── config/
│   ├── base.env                   # Distro variables, compression levels, and paths
│   ├── packages.list              # Curated core package manifest
│   ├── packages.strip             # Downstream bloat packages purged from base
│   └── calamares/                 # Calamares installer configurations
│       ├── settings.conf          # Module execution sequence
│       ├── modules/
│       │   ├── unpackfs.conf      # Casper squashfs unpack config
│       │   └── akriti-postinstall.py # Dynamic rootMountPoint user workspace config
│       └── branding/akriti/
│           └── branding.desc      # 780x500px window geometry & Cyberdeck palette
├── hooks/
│   ├── 01-strip-bloat.chroot      # Desktop protection & bloat purge
│   ├── 02-install-core.chroot     # Installs Calamares, Fcitx5, Indic fonts, Python GTK4
│   ├── 03-configure-xfce.chroot   # Injects Sutra workspaces, panel layout & /etc/skel
│   └── 04-cleanup-rootfs.chroot   # Purges APT archives, truncates logs, zeroes machine-id
├── overlay/                       # Filesystem tree injected into target rootfs
│   ├── etc/
│   │   ├── akriti/design-tokens.json
│   │   ├── default/zramswap       # 150% ZRAM configuration
│   │   └── sysctl.d/
│   │       ├── 60-akriti-bwrap.conf # Bubblewrap userns unblock
│   │       └── 99-akriti-zram.conf  # Swappiness and memory tuning
│   └── usr/
│       ├── local/bin/             # Signature CLI suite (pothi, jugaad, akriti-doctor, akriti-pack)
│       └── share/akriti/          # Wallpapers & Bharat Study Packs catalog
├── iso-overlay/
│   └── boot/grub/grub.cfg         # Dual BIOS/UEFI GRUB menu (Live, Persistent, Toram)
├── scripts/                       # Modular stage execution scripts
│   ├── 01-extract-iso.sh
│   ├── 02-enter-chroot.sh
│   ├── 04-pack-squashfs.sh
│   └── 05-build-iso.sh
└── .github/workflows/
    └── build-iso.yml              # Cloud CI/CD workflow building bootable ISO
```

---

## 🚀 Quick Start & Build Instructions

### 1. Prerequisites
The build system runs on an Ubuntu / Debian host (or inside Docker/VM) with `sudo` access:

```bash
# Check and install host tools
make deps
```

### 2. Building the ISO
Execute the full automated pipeline:

```bash
# Full build in development mode (ZSTD level 15 - fast build)
sudo ./build.sh all

# Or build using make
sudo make all

# Build production release (maximum ZSTD level 19 compression)
sudo BUILD_MODE=prod make iso
```

### 3. Step-by-Step Stage Execution
You can execute stages individually during development:

```bash
make bootstrap     # 1. Download base ISO and extract rootfs
make chroot        # 2. Enter chroot, apply overlays, and run hooks
make squashfs      # 3. Compress rootfs with ZSTD
make iso           # 4. Generate hybrid dual BIOS/UEFI bootable ISO
```

### 4. Testing in QEMU
Test the output ISO immediately with hardware acceleration (if available):

```bash
# Test Legacy BIOS boot
make test-qemu

# Test UEFI boot (requires OVMF)
make test-qemu-uefi
```

---

## 🎛️ Signature System Software Suite

The userland tools are pre-staged in `/usr/local/bin`:

| Command | Description |
| :--- | :--- |
| `pothi` | **Pothi Workspaces Manager:** Organizes student projects into Vidya, Nirman, and Kosh with archiving. |
| `jugaad` | **Jugaad Bench:** Safe Bubblewrap sandbox that masks sensitive user credentials (`~/.ssh`, `~/.gnupg`, `~/Pothi`). |
| `akriti-doctor` | **Self-Healing Diagnostics:** Real-time health probes and automated repairs for disk space, broken APT locks, Indic IME, and audio. |
| `akriti-pack` | **Bharat Study Packs:** Offline package manager for curated learning, electronics, and coding bundles. |
| `akriti-theme-switch` | **Atomic Theme Switcher:** Live switching between Retro Cyberdeck, Calm Study, High Contrast, and Terminal Forward. |

---

## 🌐 Automated GitHub Actions CI/CD
The repository includes `.github/workflows/build-iso.yml` which:
1. Runs on an `ubuntu-24.04` runner.
2. Cleans up runner storage to free 30+ GB of disk space.
3. Installs build toolchains (`xorriso`, `squashfs-tools`, `mtools`, `zstd`, `qemu-utils`).
4. Executes `./build.sh all`.
5. Computes SHA256 checksums.
6. Uploads the bootable ISO artifact with 14-day retention.
7. Automatically attaches the ISO to GitHub Releases when a version tag (`v*`) is pushed.
