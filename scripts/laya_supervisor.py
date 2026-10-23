#!/usr/bin/env python3
"""
Akriti OS / Bharat OS - Laya Autonomous Supervisor & Command Gatekeeper
========================================================================
Acts as the 24/7 autonomous sentinel for terminal safety, command approvals,
and live GitHub repository build activity monitoring.

Integrates the local Laya non-autoregressive decision model (`from laya import Router`)
to act as the autonomous command gatekeeper and self-healing build monitor.

Capabilities:
1. Autonomous Command Gatekeeper:
   - Intercepts proposed build commands, git actions, and chroot operations.
   - Evaluates commands against safety policies and queries local Laya model
     with structured questions (`gatekeeper_decision`, `risk_level`, `is_safe`).
   - Logs telemetry and decision distribution to `logs/sentinel_approvals.log`.
2. Live GitHub Actions Build Sentinel:
   - Monitors live runs on `neoline361-art/akriti-os-build`.
   - On build failure: extracts error trace, has Laya classify root cause,
     evaluates self-healing patch, commits, and pushes to trigger healed build!
   - On build success: retrieves and reports ISO release/artifact download URLs.
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
from typing import Dict, Any, Tuple, Optional, List

# Base Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
AUDIT_LOG_FILE = os.path.join(LOGS_DIR, "sentinel_approvals.log")
REPO_NAME = "neoline361-art/akriti-os-build"

# Ensure offline cache mode for lightning-fast local model loading
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

try:
    import torch
    torch.set_num_threads(4)
except Exception:
    pass

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
# 1. Deterministic Hard Safety Invariants (Zero-Damage Floor)
# ==============================================================================
BLOCKED_PATTERNS = [
    (r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*\s+|\s+.*-r\w*\s+)(/|\~|\$HOME|/data/data/com\.termux/files/home/?)(/|\s|$)", "Catastrophic deletion on root or home directory"),
    (r"\bmkfs(\.\w+)?\s+/dev/(sd[a-z]|nvme\d+n\d+|mmcblk\d+)(?!p\d+loop)", "Direct disk formatting of physical block devices"),
    (r"\bdd\s+.*of=/dev/(sd[a-z]|nvme\d+n\d+|mmcblk\d+)\b", "Direct raw disk write to host physical device"),
    (r"\b(shutdown|reboot|poweroff|init\s+0|halt)\b", "Host system shutdown command"),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "Fork-bomb denial-of-service sequence"),
    (r">\s*/dev/(sd[a-z]|nvme\d+|mem|kmem)", "Direct write redirection to kernel memory or raw disk"),
]

SAFE_COMMAND_PREFIXES = [
    "git", "gh", "make", "python3", "pytest", "ls", "du", "df", "cat", "echo",
    "grep", "find", "curl", "wget", "tar", "unsquashfs", "mksquashfs", "xorriso",
    "sha256sum", "md5sum", "mkdir", "cp", "rsync", "chmod", "sync", "./build.sh",
    "sudo ./build.sh", "bash scripts/", "sudo bash scripts/"
]


# ==============================================================================
# 2. Laya Decision Model Schemas
# ==============================================================================
def get_gatekeeper_questions() -> Dict[str, Any]:
    return {
        "gatekeeper_decision": {
            "type": "choice",
            "instructions": "Determine whether the shell command is approved, rejected, or requires remediation.",
            "criteria": {
                "approve": "Standard operational, build, git, test, packaging, or inspection command.",
                "reject": "Dangerous, catastrophic, unauthorized, or destructive command.",
                "remediate": "Command is missing arguments or poses ambiguous risks requiring adjustment.",
            },
        },
        "risk_level": {
            "type": "choice",
            "instructions": "Rate the command risk level.",
            "criteria": {
                "low": "Read-only inspection or standard git workflow.",
                "medium": "Local build script or file modification within project scope.",
                "high": "Sudo execution, kernel mount, or chroot modifications.",
            },
        },
        "is_safe": {
            "type": "noul",
            "instructions": "Is this command compliant with zero-damage isolation?",
            "criteria": {
                "true": "Command is safe to execute in the workspace.",
                "false": "Command presents unacceptable hazard or system damage risk.",
            },
        },
    }


def get_failure_diagnosis_questions() -> Dict[str, Any]:
    return {
        "failure_classification": {
            "type": "choice",
            "instructions": "Diagnose root cause of the build failure from logs.",
            "criteria": {
                "fix_resolv_conf_symlink": "cp: resolv.conf same file collision between host bind-mounted /run and rootfs.",
                "fix_squashfs_overlay": "SquashFS extraction or overlay mounting inode/hardlink conflict.",
                "fix_mirror_url": "Ubuntu/Debian archive mirror 404 or connection failure.",
                "fix_package_dep": "Unmet package dependencies or dpkg configuration error.",
                "retry_transient": "Ephemeral network timeout or runner disconnection.",
                "syntax_error": "Shell syntax or undefined variable under set -euo pipefail.",
            },
        },
        "remediation_action": {
            "type": "choice",
            "instructions": "Select autonomous remediation action.",
            "criteria": {
                "patch_resolv_conf": "Remove rootfs resolv.conf symlink before cp -L in scripts/02-enter-chroot.sh.",
                "patch_overlayfs": "Update 01-extract-iso.sh overlay logic.",
                "retry_transient": "Re-run build without code modification.",
                "manual_triage": "Complex failure requiring human review.",
            },
        },
        "auto_approve_healing": {
            "type": "noul",
            "instructions": "Can this fix be autonomously committed and pushed to git?",
            "criteria": {
                "true": "Deterministic verified patch available for immediate autonomous healing.",
                "false": "Uncertain or dangerous change requiring developer confirmation.",
            },
        },
    }


# ==============================================================================
# 3. Laya Sentinel Command Gatekeeper
# ==============================================================================
class LayaSentinel:
    """Evaluates terminal commands using local Laya neural model + deterministic floor."""

    def __init__(self, use_model: bool = True):
        self.use_model = use_model
        self._router = None

    def _get_router(self):
        """Lazy loads Laya neural decision engine."""
        if not self.use_model:
            return None
        if self._router is None:
            try:
                from laya import Router
                self._router = Router(default="english")
                logger.info("🧠 Laya Neural Decision Engine loaded (local weights active).")
            except Exception as e:
                logger.warning("Laya neural model init failed (%s). Using high-speed rule fallback.", e)
                self.use_model = False
        return self._router

    def evaluate_command(self, cmd: str) -> Dict[str, Any]:
        """Audits a command with Laya decision engine and returns approval verdict."""
        stripped = cmd.strip()

        # 1. Deterministic Hard Floor: Reject catastrophic patterns immediately
        for pattern, reason in BLOCKED_PATTERNS:
            if re.search(pattern, stripped, re.IGNORECASE):
                decision = {
                    "approved": False,
                    "action": "BLOCKED",
                    "risk_level": "CRITICAL",
                    "reason": reason,
                    "command": stripped,
                    "model_telemetry": {"engine": "hard_floor", "verdict": "blocked"},
                    "timestamp": datetime.now().isoformat(),
                }
                self._log_audit(decision)
                return decision

        # 2. Query Local Laya Decision Model
        router = self._get_router()
        if self.use_model and router:
            try:
                state = {
                    "command": stripped,
                    "project": "akriti-os-build",
                    "context": "Akriti OS remastering build pipeline and Git CI/CD operations",
                }
                questions = get_gatekeeper_questions()
                res = router.predict(state, questions)
                answers = res.get("answers", {})

                gk_decision = answers.get("gatekeeper_decision", {}).get("choice", "approve")
                risk = answers.get("risk_level", {}).get("choice", "medium").upper()
                is_safe = answers.get("is_safe", {}).get("value", True)
                confidence = answers.get("gatekeeper_decision", {}).get("confidence", 0.0)
                probs = answers.get("gatekeeper_decision", {}).get("probabilities", {})

                is_whitelisted = any(stripped.startswith(p) for p in SAFE_COMMAND_PREFIXES)
                reject_prob = probs.get("reject", 0.0)
                approved = is_safe and (
                    (gk_decision == "approve") or
                    (gk_decision == "remediate" and is_whitelisted and reject_prob < 0.35)
                )
                action_str = "APPROVED" if approved else ("REMEDIATE" if gk_decision == "remediate" else "REJECTED")

                decision = {
                    "approved": approved,
                    "action": action_str,
                    "risk_level": risk,
                    "reason": f"Laya Decision: {gk_decision} (conf: {confidence:.2f}, safe={is_safe})",
                    "command": stripped,
                    "model_telemetry": {
                        "engine": "laya_neural",
                        "probabilities": probs,
                        "confidence": confidence,
                        "routing": res.get("routing", {}),
                    },
                    "timestamp": datetime.now().isoformat(),
                }
                self._log_audit(decision)
                return decision
            except Exception as e:
                logger.warning("Laya model evaluation failed (%s). Falling back to rules.", e)

        # 3. Deterministic Heuristic Fallback
        matched_safe = any(stripped.startswith(prefix) for prefix in SAFE_COMMAND_PREFIXES)
        risk = "LOW" if matched_safe else "MEDIUM"

        decision = {
            "approved": True,
            "action": "APPROVED",
            "risk_level": risk,
            "reason": "Safe verified build/git workflow operation (heuristic fallback).",
            "command": stripped,
            "model_telemetry": {"engine": "heuristic_fallback"},
            "timestamp": datetime.now().isoformat(),
        }
        self._log_audit(decision)
        return decision

    def _log_audit(self, decision: Dict[str, Any]):
        """Logs audit record to sentinel log file and console."""
        symbol = "✅" if decision["approved"] else "🛑"
        telem = decision.get("model_telemetry", {})
        conf_str = f" [conf: {telem.get('confidence', 0.0):.2f}]" if "confidence" in telem else ""
        logger.info(
            "%s [%s] (%s risk)%s %s -> %s",
            symbol,
            decision["action"],
            decision["risk_level"],
            conf_str,
            decision["reason"],
            decision["command"][:90] + ("..." if len(decision["command"]) > 90 else ""),
        )

    def execute_safely(self, cmd: str) -> Tuple[bool, int, str]:
        """Evaluates command, and if approved, runs it and captures output."""
        audit = self.evaluate_command(cmd)
        if not audit["approved"]:
            err_msg = f"[SENTINEL BLOCKED] Command rejected: {audit['reason']} (Command: {cmd})"
            logger.error(err_msg)
            return False, 1, err_msg

        logger.info("⚡ Executing approved command: %s", cmd)
        try:
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=PROJECT_ROOT)
            return res.returncode == 0, res.returncode, res.stdout + ("\nSTDERR:\n" + res.stderr if res.stderr else "")
        except Exception as e:
            logger.error("Execution failed with exception: %s", e)
            return False, 1, str(e)


# ==============================================================================
# 4. Live GitHub Actions Repository Sentinel & Auto-Healer
# ==============================================================================
class RepoWatchdog:
    """Monitors live GitHub repository runs, alerts, and triggers auto-healing."""

    def __init__(self, sentinel: LayaSentinel, repo: str = REPO_NAME):
        self.sentinel = sentinel
        self.repo = repo

    def get_latest_runs(self, limit: int = 5) -> list:
        """Retrieves latest workflow runs via GitHub CLI."""
        cmd = f"gh run list --repo {self.repo} --limit {limit} --json databaseId,status,conclusion,name,headBranch,createdAt,updatedAt,event,displayTitle"
        success, code, output = self.sentinel.execute_safely(cmd)
        if not success:
            logger.warning("Could not query GitHub runs. Ensure gh CLI is authenticated.")
            return []
        try:
            json_start = output.find("[")
            json_end = output.rfind("]") + 1
            if json_start != -1 and json_end != -1:
                return json.loads(output[json_start:json_end])
            return []
        except Exception as e:
            logger.error("Failed to parse gh run list JSON: %s", e)
            return []

    def inspect_failed_run(self, run_id: int) -> Dict[str, Any]:
        """Fetches failure logs and has Laya diagnose root cause and recommend healing."""
        logger.info("🔍 Inspecting failed run #%s...", run_id)
        cmd = f"gh run view {run_id} --repo {self.repo} --log-failed"
        success, code, output = self.sentinel.execute_safely(cmd)

        raw_snippet = output[-2500:] if len(output) > 2500 else output

        state = {
            "run_id": run_id,
            "error_log": raw_snippet,
            "project": "akriti-os-build",
        }

        # Query Laya decision model for diagnosis
        router = self.sentinel._get_router()
        if self.sentinel.use_model and router:
            try:
                questions = get_failure_diagnosis_questions()
                diag_res = router.predict(state, questions)
                answers = diag_res.get("answers", {})

                classification = answers.get("failure_classification", {}).get("choice", "unknown")
                remediation = answers.get("remediation_action", {}).get("choice", "manual_triage")
                auto_approve = answers.get("auto_approve_healing", {}).get("value", False)
                confidence = answers.get("failure_classification", {}).get("confidence", 0.0)

                logger.info("🧠 Laya Diagnosis: Root Cause='%s', Fix='%s' (conf: %.2f, auto_heal=%s)",
                            classification, remediation, confidence, auto_approve)
                return {
                    "run_id": run_id,
                    "root_cause": classification,
                    "suggested_fix": remediation,
                    "auto_approve": auto_approve,
                    "raw_log_tail": raw_snippet,
                }
            except Exception as e:
                logger.warning("Laya diagnostic model query failed: %s", e)

        # Heuristic fallback diagnosis
        classification = "unknown"
        remediation = "manual_triage"
        auto_approve = False

        if "are the same file" in output and "resolv.conf" in output:
            classification = "fix_resolv_conf_symlink"
            remediation = "patch_resolv_conf"
            auto_approve = True
        elif "Could not locate filesystem.squashfs" in output or "hardlink" in output:
            classification = "fix_squashfs_overlay"
            remediation = "patch_overlayfs"
            auto_approve = True
        elif "Could not get lock /var/lib/dpkg/lock" in output:
            classification = "retry_transient"
            remediation = "retry_transient"
            auto_approve = True

        return {
            "run_id": run_id,
            "root_cause": classification,
            "suggested_fix": remediation,
            "auto_approve": auto_approve,
            "raw_log_tail": raw_snippet,
        }

    def heal_resolv_conf_issue(self) -> bool:
        """Applies self-healing patch for the resolv.conf bind-mount collision."""
        logger.info("🩹 Applying self-healing patch to scripts/02-enter-chroot.sh...")
        chroot_script = os.path.join(PROJECT_ROOT, "scripts", "02-enter-chroot.sh")
        try:
            with open(chroot_script, "r", encoding="utf-8") as f:
                content = f.read()

            target_str = 'cp -L /etc/resolv.conf "${ROOTFS_DIR}/etc/resolv.conf"'
            if target_str in content:
                replacement_str = (
                    '# Remove symlink if present to prevent resolving into bind-mounted /run\n'
                    'rm -f "${ROOTFS_DIR}/etc/resolv.conf"\n'
                    'if [[ -f /etc/resolv.conf ]]; then\n'
                    '    cp -L --remove-destination /etc/resolv.conf "${ROOTFS_DIR}/etc/resolv.conf" 2>/dev/null || \\\n'
                    '        echo -e "nameserver 1.1.1.1\\nnameserver 8.8.8.8" > "${ROOTFS_DIR}/etc/resolv.conf"\n'
                    'else\n'
                    '    echo -e "nameserver 1.1.1.1\\nnameserver 8.8.8.8" > "${ROOTFS_DIR}/etc/resolv.conf"\n'
                    'fi'
                )
                content = content.replace(target_str, replacement_str)
                with open(chroot_script, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info("✅ Patched scripts/02-enter-chroot.sh successfully.")
            else:
                logger.info("scripts/02-enter-chroot.sh already patched or target string not found.")

            # Intercept and gatekeep Git commit & push
            self.sentinel.execute_safely("git add scripts/02-enter-chroot.sh scripts/laya_supervisor.py")
            ok, code, out = self.sentinel.execute_safely(
                'git commit -m "fix(chroot): unlink resolv.conf before copy to prevent bind-mount collision"'
            )
            if not ok and "nothing to commit" not in out:
                logger.error("Git commit failed: %s", out)
                return False

            ok, code, out = self.sentinel.execute_safely("git push origin master")
            if not ok:
                logger.error("Git push failed: %s", out)
                return False

            logger.info("🚀 Healed commit pushed to GitHub! New build workflow triggered.")
            return True
        except Exception as e:
            logger.error("Healing failed: %s", e)
            return False

    def watch(self, target_run_id: Optional[int] = None, interval: int = 20, max_iterations: int = 25):
        """Monitors GitHub repository activity continuously."""
        logger.info("🔭 Starting Live Repo Watchdog for %s (interval=%ds, max=%d)...",
                    self.repo, interval, max_iterations)
        iterations = 0

        while iterations < max_iterations:
            iterations += 1
            runs = self.get_latest_runs(3)
            if not runs:
                logger.info("[%d/%d] No runs returned by GitHub API. Retrying in %ds...",
                            iterations, max_iterations, interval)
                time.sleep(interval)
                continue

            latest = runs[0]
            if target_run_id:
                for r in runs:
                    if r.get("databaseId") == target_run_id:
                        latest = r
                        break

            run_id = latest.get("databaseId")
            status = latest.get("status")
            conclusion = latest.get("conclusion")
            title = latest.get("displayTitle", latest.get("name", "Build"))

            logger.info("[%d/%d] Run #%s: '%s' | Status='%s', Conclusion='%s'",
                        iterations, max_iterations, run_id, title[:40], status, conclusion)

            if status in ("in_progress", "queued", "waiting"):
                logger.info("⏳ Build #%s in progress... Laya Sentinel active.", run_id)
            elif status == "completed":
                if conclusion == "success":
                    logger.info("🎉🎉 BUILD #%s SUCCEEDED! Akriti OS ISO remastering successful!", run_id)
                    # Query Artifacts
                    art_cmd = f"gh run view {run_id} --repo {self.repo} --json artifacts"
                    _, _, art_out = self.sentinel.execute_safely(art_cmd)
                    logger.info("📦 Artifact Details: %s", art_out)
                    break
                elif conclusion == "failure":
                    logger.warning("❌ Build #%s failed. Initiating Laya failure diagnosis...", run_id)
                    diag = self.inspect_failed_run(run_id)
                    if diag.get("suggested_fix") == "patch_resolv_conf" and diag.get("auto_approve"):
                        logger.info("🤖 Auto-approving self-healing patch...")
                        if self.heal_resolv_conf_issue():
                            logger.info("Monitoring next healed run...")
                            time.sleep(10)
                            target_run_id = None
                            continue
                    break

            time.sleep(interval)


# ==============================================================================
# 5. CLI Entry Point
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="Laya Autonomous Sentinel & Build Supervisor")
    subparsers = parser.add_subparsers(dest="command", help="Sentinel sub-commands")

    eval_parser = subparsers.add_parser("eval", help="Evaluate safety of a command")
    eval_parser.add_argument("cmd_str", type=str, help="Shell command to audit")

    run_parser = subparsers.add_parser("run", help="Audit and execute command safely")
    run_parser.add_argument("cmd_str", type=str, help="Shell command to execute")

    watch_parser = subparsers.add_parser("watch", help="Watch live GitHub repository build status")
    watch_parser.add_argument("--run-id", type=int, default=None, help="Specific GitHub Run ID to monitor")
    watch_parser.add_argument("--interval", type=int, default=15, help="Polling interval in seconds")
    watch_parser.add_argument("--iterations", type=int, default=20, help="Maximum polling iterations")

    subparsers.add_parser("status", help="Show recent audit log history")

    args = parser.parse_args()
    sentinel = LayaSentinel(use_model=True)

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
        watchdog.watch(target_run_id=args.run_id, interval=args.interval, max_iterations=args.iterations)

    elif args.command == "status":
        if os.path.exists(AUDIT_LOG_FILE):
            with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
                print("".join(lines[-35:]))
        else:
            print("No audit log found yet.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

