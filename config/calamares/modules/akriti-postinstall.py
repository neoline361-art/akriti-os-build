#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
# Akriti OS (Chameleon) - Calamares Post-Install Hook
# Dynamically configures target user workspaces, Pothi, Jugaad, and permissions
# ==============================================================================

import os
import sys
import pwd
import grp
import shutil
import subprocess

try:
    import libcalamares
except ImportError:
    libcalamares = None


def resolve_user_ids(root_mount, username):
    """
    Parse /etc/passwd inside the target root filesystem to get exact UID and GID.
    """
    passwd_path = os.path.join(root_mount, "etc", "passwd")
    if not os.path.exists(passwd_path):
        return 1000, 1000  # Safe standard fallback

    with open(passwd_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(":")
            if parts and parts[0] == username:
                return int(parts[2]), int(parts[3])
    return 1000, 1000


def recursive_chown(path, uid, gid):
    """
    Recursively apply ownership to path and all descendants.
    """
    for root, dirs, files in os.walk(path):
        try:
            os.chown(root, uid, gid)
        except OSError:
            pass
        for item in files:
            try:
                os.chown(os.path.join(root, item), uid, gid)
            except OSError:
                pass


def setup_pothi_workspaces(home_dir, uid, gid):
    """
    Initializes Pothi digital notebook structure for learning and coursework.
    """
    pothi_root = os.path.join(home_dir, "Pothi")
    subdirs = [
        "Vidya/Mathematics",
        "Vidya/Science",
        "Vidya/General",
        "Nirman/Python",
        "Nirman/C_Projects",
        "Nirman/Web",
        "Kosh/Reference_Papers",
        "Kosh/Datasets",
        ".archive"
    ]

    for sd in subdirs:
        os.makedirs(os.path.join(pothi_root, sd), exist_ok=True)

    manifest_path = os.path.join(pothi_root, "pothi.yaml")
    if not os.path.exists(manifest_path):
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write("""# Akriti OS - Pothi Workspace Manifest
version: "1.0"
edition: "Bharat Cyberdeck"
description: "Structured digital notebook and coursework manager"
active_subjects:
  - id: math
    name: "गणित (Mathematics)"
    path: "Vidya/Mathematics"
  - id: science
    name: "विज्ञान (Science)"
    path: "Vidya/Science"
  - id: engineering
    name: "अभियांत्रिकी (Engineering & Coding)"
    path: "Nirman"
archive_dir: ".archive"
""")

    readme_path = os.path.join(pothi_root, "README.md")
    if not os.path.exists(readme_path):
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write("""# 📖 पोथी (Pothi) Workspaces — Akriti OS

Welcome to your structured knowledge workspace!

## Workspace Sutras:
- **Vidya (विद्या):** Coursework, notes, calculations, and reading materials.
- **Nirman (निर्माण):** Software projects, hardware blueprints, robotics, and build scripts.
- **Kosh (कोश):** Archives, offline references, research papers, and shared datasets.

Use the `pothi` CLI or desktop launcher to create, manage, and archive your projects:
```bash
pothi list
pothi create math linear-algebra --template=math
pothi archive math linear-algebra
```
""")

    recursive_chown(pothi_root, uid, gid)


def setup_jugaad_sandbox(home_dir, uid, gid):
    """
    Initializes Jugaad Bench safe scratchpad and Bubblewrap sandbox folders.
    """
    jugaad_root = os.path.join(home_dir, "Jugaad")
    subdirs = [
        "scratch",
        "templates/python",
        "templates/c",
        "templates/web",
        "templates/bash",
        ".snapshots"
    ]

    for sd in subdirs:
        os.makedirs(os.path.join(jugaad_root, sd), exist_ok=True)

    # Starter Python boilerplate in scratch
    py_starter = os.path.join(jugaad_root, "scratch", "main.py")
    if not os.path.exists(py_starter):
        with open(py_starter, "w", encoding="utf-8") as f:
            f.write("""#!/usr/bin/env python3
# Akriti OS Jugaad Bench - Quick Scratchpad
import sys

def main():
    print("✨ Namaste from Akriti OS Jugaad Bench!")
    print(f"🐍 Python {sys.version.split()[0]} running inside safe sandbox.")

if __name__ == "__main__":
    main()
""")

    readme_path = os.path.join(jugaad_root, "README.md")
    if not os.path.exists(readme_path):
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write("""# 🛠️ जुगाड़ (Jugaad) Bench — Safe Sandbox

Jugaad Bench is your zero-risk scratchpad. You can test code, compile software,
and experiment freely without worrying about breaking your system or losing credentials.

- Sensitive directories (`~/.ssh`, `~/.gnupg`, `~/Pothi`) are masked during execution.
- Automatically takes differential snapshots before major sandbox resets.

Commands:
```bash
jugaad launch python    # Launch safe Python scratch session
jugaad launch web       # Launch safe static web preview session
jugaad reset            # Snapshot current work and reset scratch folder
```
""")

    recursive_chown(jugaad_root, uid, gid)


def setup_user_configs(home_dir, uid, gid):
    """
    Initializes theme default and user config state.
    """
    cfg_dir = os.path.join(home_dir, ".config", "akriti")
    os.makedirs(cfg_dir, exist_ok=True)

    theme_file = os.path.join(cfg_dir, "active-theme")
    if not os.path.exists(theme_file):
        with open(theme_file, "w", encoding="utf-8") as f:
            f.write("retro-cyberdeck\n")

    recursive_chown(os.path.join(home_dir, ".config"), uid, gid)


def run():
    """
    Calamares module entry point.
    """
    if libcalamares:
        root_mount = libcalamares.globalstorage.get("rootMountPoint")
        username = libcalamares.globalstorage.get("username")
    else:
        root_mount = os.environ.get("TARGET_ROOT", "/")
        username = os.environ.get("TARGET_USER", "akriti")

    if not root_mount or not os.path.isdir(root_mount):
        return ("Root mount point invalid", f"Path does not exist: {root_mount}")

    if not username:
        username = "akriti"

    home_dir = os.path.join(root_mount, "home", username)
    if not os.path.isdir(home_dir):
        os.makedirs(home_dir, exist_ok=True)

    uid, gid = resolve_user_ids(root_mount, username)

    # 1. Setup Pothi Workspaces
    setup_pothi_workspaces(home_dir, uid, gid)

    # 2. Setup Jugaad Sandbox
    setup_jugaad_sandbox(home_dir, uid, gid)

    # 3. Setup User Configs
    setup_user_configs(home_dir, uid, gid)

    # 4. Ensure correct base permissions on home directory
    try:
        os.chown(home_dir, uid, gid)
        os.chmod(home_dir, 0o750)
    except OSError:
        pass

    return None


if __name__ == "__main__":
    status = run()
    if status is not None:
        print(f"Post-install failed: {status}")
        sys.exit(1)
    print("Akriti OS post-install hook finished successfully.")
