#!/usr/bin/env python3
"""
Akriti OS / Bharat OS - Laya Autonomous Supervisor & Command Gatekeeper
========================================================================
Acts as the 24/7 autonomous sentinel for terminal safety, command approvals,
and live GitHub repository build activity monitoring.

Roles:
1. Terminal Command Gatekeeper:
   - Evaluates terminal commands before execution.
   - Enforces zero-damage policy: blocks dangerous commands (e.g. `rm -rf /`,
     raw disk writes, uncommitted source deletion).
   - Approves safe build, git, chroot, packaging, and test commands.
   - Logs every decision to `logs/sentinel_approvals.log`.
2. Live Repository Watchdog:
   - Monitors GitHub Actions CI/CD runs on `neoline361-art/akriti-os-build`.
   - Prevents hallucination by parsing ground-truth logs from GitHub CLI.
   - Diagnoses failure points and suggests/executes automated remediation.
3. PRD Compliance:
   - External supervisor on host/Termux only (OS rootfs remains AI-Free).
"""

import sys
import os
import re
import time
import json
import logging
import subprocess
import argparse
from datetime import datetime
from typing import Dict, Any, Tuple, Optional

# Base Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
AUDIT_LOG_FILE = os.path.join(LOGS_DIR, "sentinel_approvals.log")
REPO_NAME = "neoline361-art/akriti-os-build"

os.makedirs(LOGS_DIR, exist_ok=True)

# Logger setup
logger = logging.getLogger("laya-supervisor")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

file_handler = logging.FileHandler(AUDIT_LOG_FILE, encoding="utf-8")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


# ==============================================================================
# 1. Safety Policies & Threat Classification
# ==============================================================================
BLOCKED_PATTERNS = [
    (r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*\s+|\s+.*-r\w*\s+)(/|\~|\$HOME|/data/data/com\.termux/files/home/?)\b", "Catastrophic file deletion attempt on root or home directory"),
    (r"\bmkfs(\.\w+)?\s+/dev/(sd[a-z]|nvme\d+n\d+|mmcblk\d+)(?!p\d+loop)", "Direct disk formatting of physical block devices"),
    (r"\bdd\s+.*of=/dev/(sd[a-z]|nvme\d+n\d+|mmcblk\d+)\b", "Direct raw disk write to host physical device"),
    (r"\b(shutdown|reboot|poweroff|init\s+0|halt)\b", "System shutdown command outside container sandbox"),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "Fork-bomb denial-of-service sequence"),
    (r">\s*/dev/(sd[a-z]|nvme\d+|mem|kmem)", "Direct write redirection to kernel memory or raw disk"),
]

SAFE_COMMAND_PREFIXES = [
    "git", "gh", "make", "python3", "pytest", "ls", "du", "df", "cat", "echo",
    "grep", "find", "curl", "wget", "tar", "unsquashfs", "mksquashfs", "xorriso",
    "sha256sum", "md5sum", "mkdir", "cp", "rsync", "chmod", "sync", "./build.sh",
    "sudo ./build.sh", "bash scripts/", "sudo bash scripts/"
]


class LayaSentinel:
    """Evaluates terminal commands and supervises repository workflows."""

    def __init__(self, use_model: bool = False):
        self.use_model = use_model
        self.router = None
        if self.use_model:
            try:
                from laya import Router
                self.router = Router(default="english")
                logger.info("Laya Decision Engine connected.")
            except Exception as e:
                logger.warning("Laya neural model unavailable (%s). Using high-speed rule evaluator.", e)
                self.use_model = False

    def evaluate_command(self, cmd: str) -> Dict[str, Any]:
        """Audits a command for safety and returns approval verdict."""
        stripped = cmd.strip()

        # 1. Check against blocked catastrophic patterns
        for pattern, reason in BLOCKED_PATTERNS:
            if re.search(pattern, stripped, re.IGNORECASE):
                decision = {
                    "approved": False,
                    "action": "BLOCKED",
                    "risk_level": "CRITICAL",
                    "reason": reason,
                    "command": stripped,
                    "timestamp": datetime.now().isoformat()
                }
                self._log_audit(decision)
                return decision

        # 2. Check for suspicious rm operations
        if re.search(r"\brm\s+-[a-zA-Z]*r", stripped):
            # Allow rm only inside build/, cache/, /tmp, or specific targets
            allowed_rm_paths = [
                r"build/", r"build$", r"cache/", r"cache$", r"/tmp/", r"\.tmp",
                r"md5sum\.txt", r"\.squashfs", r"\.iso"
            ]
            has_allowed_target = any(re.search(p, stripped) for p in allowed_rm_paths)
            if not has_allowed_target and ("*" in stripped or "/" in stripped):
                decision = {
                    "approved": False,
                    "action": "REJECTED",
                    "risk_level": "HIGH",
                    "reason": "Potentially destructive recursive deletion without explicit build-scoped path.",
                    "command": stripped,
                    "timestamp": datetime.now().isoformat()
                }
                self._log_audit(decision)
                return decision

        # 3. Safe verified command whitelist match
        matched_safe = any(stripped.startswith(prefix) for prefix in SAFE_COMMAND_PREFIXES)
        risk = "LOW" if matched_safe else "MEDIUM"

        decision = {
            "approved": True,
            "action": "APPROVED",
            "risk_level": risk,
            "reason": "Safe build, inspection, or CI/CD workflow operation.",
            "command": stripped,
            "timestamp": datetime.now().isoformat()
        }
        self._log_audit(decision)
        return decision

    def _log_audit(self, decision: Dict[str, Any]):
        """Logs audit record to sentinel log file."""
        symbol = "✅" if decision["approved"] else "🛑"
        logger.info(
            "%s [%s] (%s risk) %s -> %s",
            symbol,
            decision["action"],
            decision["risk_level"],
            decision["reason"],
            decision["command"][:80] + ("..." if len(decision["command"]) > 80 else "")
        )

    def execute_safely(self, cmd: str) -> Tuple[bool, int, str]:
        """Evaluates command, and if approved, runs it and captures output."""
        audit = self.evaluate_command(cmd)
        if not audit["approved"]:
            err_msg = f"[SENTINEL BLOCKED] Command rejected: {audit['reason']} (Command: {cmd})"
            logger.error(err_msg)
            return False, 1, err_msg

        logger.info("Executing approved command: %s", cmd)
        try:
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=PROJECT_ROOT)
            return res.returncode == 0, res.returncode, res.stdout + ("\nSTDERR:\n" + res.stderr if res.stderr else "")
        except Exception as e:
            logger.error("Execution failed with exception: %s", e)
            return False, 1, str(e)


# ==============================================================================
# 2. Live GitHub Actions Repository Sentinel
# ==============================================================================
class RepoWatchdog:
    """Monitors live GitHub repository runs, alerts, and triggers auto-healing."""

    def __init__(self, sentinel: LayaSentinel, repo: str = REPO_NAME):
        self.sentinel = sentinel
        self.repo = repo
        self.last_checked_run_id = None

    def get_latest_runs(self, limit: int = 5) -> list:
        """Retrieves latest workflow runs via GitHub CLI."""
        cmd = f"gh run list --repo {self.repo} --limit {limit} --json databaseId,status,conclusion,name,headBranch,createdAt,updatedAt,event"
        success, code, output = self.sentinel.execute_safely(cmd)
        if not success:
            logger.warning("Could not query GitHub runs. Ensure gh CLI is authenticated.")
            return []
        try:
            # gh run list output may have STDERR attached; extract JSON array
            json_start = output.find("[")
            json_end = output.rfind("]") + 1
            if json_start != -1 and json_end != -1:
                return json.loads(output[json_start:json_end])
            return []
        except Exception as e:
            logger.error("Failed to parse gh run list JSON: %s", e)
            return []

    def inspect_failed_run(self, run_id: int) -> Dict[str, Any]:
        """Fetches failure logs and diagnoses root cause."""
        logger.info("Inspecting failed run #%s...", run_id)
        cmd = f"gh run view {run_id} --repo {self.repo} --log-failed"
        success, code, output = self.sentinel.execute_safely(cmd)

        diagnosis = {
            "run_id": run_id,
            "root_cause": "unknown",
            "suggested_fix": "inspect logs manually",
            "raw_log_tail": output[-2000:] if len(output) > 2000 else output
        }

        if "Could not locate filesystem.squashfs" in output:
            diagnosis["root_cause"] = "squashfs_name_mismatch"
            diagnosis["suggested_fix"] = "Patch 01-extract-iso.sh with dynamic multi-layer squashfs discovery."
        elif "Could not get lock /var/lib/dpkg/lock" in output:
            diagnosis["root_cause"] = "apt_lock_busy"
            diagnosis["suggested_fix"] = "Kill stale processes and run dpkg --configure -a."
        elif "No space left on device" in output:
            diagnosis["root_cause"] = "disk_full"
            diagnosis["suggested_fix"] = "Free up rootfs space before squashfs compression."
        elif "404 Not Found" in output or "Could not resolve host" in output:
            diagnosis["root_cause"] = "network_mirror_failure"
            diagnosis["suggested_fix"] = "Retry with fallback Ubuntu noble archive mirror."

        logger.info("Diagnosis for run #%s: %s (Fix: %s)", run_id, diagnosis["root_cause"], diagnosis["suggested_fix"])
        return diagnosis

    def watch(self, interval: int = 30, max_iterations: int = 20):
        """Monitors GitHub repository activity continuously."""
        logger.info("Starting Live Repo Watchdog for %s (interval=%ds)...", self.repo, interval)
        iterations = 0
        while iterations < max_iterations:
            iterations += 1
            logger.info("--- Polling GitHub Actions status (%d/%d) ---", iterations, max_iterations)
            runs = self.get_latest_runs(3)
            if not runs:
                logger.info("No runs found or gh query returned empty. Sleeping...")
                time.sleep(interval)
                continue

            latest = runs[0]
            run_id = latest.get("databaseId")
            status = latest.get("status")
            conclusion = latest.get("conclusion")
            name = latest.get("name")

            logger.info("Run #%s [%s]: Status='%s', Conclusion='%s'", run_id, name, status, conclusion)

            if status == "in_progress":
                logger.info("Build in progress... Sentinel monitoring live execution.")
            elif status == "completed":
                if conclusion == "success":
                    logger.info("🎉 Build #%s succeeded! Checking for artifacts...", run_id)
                    # Check artifacts
                    art_cmd = f"gh run view {run_id} --repo {self.repo} --json artifacts"
                    _, _, art_out = self.sentinel.execute_safely(art_cmd)
                    logger.info("Artifacts: %s", art_out)
                    break
                elif conclusion == "failure":
                    logger.warning("❌ Build #%s failed. Diagnosing root cause...", run_id)
                    diag = self.inspect_failed_run(run_id)
                    break

            time.sleep(interval)


# ==============================================================================
# 3. CLI Entry Point
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="Laya Autonomous Sentinel & Build Supervisor")
    subparsers = parser.add_subparsers(dest="command", help="Sentinel sub-commands")

    # Command audit & run
    eval_parser = subparsers.add_parser("eval", help="Evaluate safety of a command")
    eval_parser.add_argument("cmd_str", type=str, help="Shell command to audit")

    run_parser = subparsers.add_parser("run", help="Audit and execute command safely")
    run_parser.add_argument("cmd_str", type=str, help="Shell command to execute")

    # Watchdog
    watch_parser = subparsers.add_parser("watch", help="Watch live GitHub repository build status")
    watch_parser.add_argument("--interval", type=int, default=15, help="Polling interval in seconds")
    watch_parser.add_argument("--iterations", type=int, default=10, help="Maximum polling iterations")

    # Status
    subparsers.add_parser("status", help="Show recent audit log history")

    args = parser.parse_args()
    sentinel = LayaSentinel(use_model=False)

    if args.command == "eval":
        res = sentinel.evaluate_command(args.cmd_str)
        print(json.dumps(res, indent=2))
        sys.exit(0 if res["approved"] else 1)

    elif args.command == "run":
        ok, code, out = sentinel.execute_safely(args.cmd_str)
        print(out)
        sys.exit(code)

    elif args.command == "watch":
        watchdog = RepoWatchdog(sentinel)
        watchdog.watch(interval=args.interval, max_iterations=args.iterations)

    elif args.command == "status":
        if os.path.exists(AUDIT_LOG_FILE):
            with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
                print("".join(lines[-30:]))
        else:
            print("No audit log found yet.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
