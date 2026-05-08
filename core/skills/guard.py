from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Skill Security Scanner — regex + structure-based threat detection."""

import logging
import re
from pathlib import Path

from core.skills.models import (
    _SEVERITY_RANKS,
    ScanFinding,
    ScanResult,
    SkillScanVerdict,
    SkillTrustLevel,
    ThreatPattern,
)

logger = logging.getLogger(__name__)

# ── Version ────────────────────────────────────────────────

SCANNER_VERSION = "1.0.0"

# ── Size Limits ────────────────────────────────────────────

MAX_SKILL_FILE_SIZE = 512 * 1024  # 512KB per file
MAX_SKILL_DIR_SIZE = 5 * 1024 * 1024  # 5MB total
MAX_FILES_PER_SKILL = 50

# ── Binary Extensions (skip scanning) ─────────────────────

_BINARY_EXTENSIONS: set[str] = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".bmp",
    ".svg",
    ".mp3",
    ".mp4",
    ".wav",
    ".ogg",
    ".flac",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".pptx",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".eot",
    ".pyc",
    ".pyo",
    ".so",
    ".dll",
    ".dylib",
    ".exe",
    ".bin",
    ".dat",
    ".db",
    ".sqlite",
    ".glb",
    ".gltf",
    ".fbx",
    ".obj",
    ".vrm",
}

# ── Invisible Characters ───────────────────────────────────

INVISIBLE_CHARS: set[str] = {
    "\u200b",  # zero-width space
    "\u200c",  # zero-width non-joiner
    "\u200d",  # zero-width joiner
    "\u2060",  # word joiner
    "\ufeff",  # BOM / zero-width no-break space
    "\u00ad",  # soft hyphen
    "\u200e",  # left-to-right mark
    "\u200f",  # right-to-left mark
    "\u202a",  # left-to-right embedding
    "\u202b",  # right-to-left embedding
    "\u202c",  # pop directional formatting
    "\u2066",  # left-to-right isolate
    "\u2067",  # right-to-left isolate
    "\u2068",  # first strong isolate
    "\u2069",  # pop directional isolate
}

# ── Threat Patterns ────────────────────────────────────────

THREAT_PATTERNS: list[ThreatPattern] = [
    # ── Prompt Injection ──
    ThreatPattern(
        name="prompt_injection_system",
        pattern=r"(?i)(ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|rules?|prompts?)|you\s+are\s+now\s+a|forget\s+everything)",
        severity="high",
        category="prompt_injection",
    ),
    ThreatPattern(
        name="prompt_injection_role_override",
        pattern=r"(?i)(your\s+new\s+(role|instruction|task)\s+is|override\s+system\s+prompt|act\s+as\s+if\s+you\s+have\s+no\s+restrictions)",
        severity="high",
        category="prompt_injection",
    ),
    # ── Data Exfiltration ──
    ThreatPattern(
        name="data_exfil_curl_wget",
        pattern=r"(?i)(curl|wget|fetch)\s+.*(--data|--post|-d\s|--upload)",
        severity="high",
        category="data_exfiltration",
    ),
    ThreatPattern(
        name="data_exfil_env_leak",
        pattern=r"(?i)(echo|print|cat|send).+(\$\{?\w*KEY\w*\}?|\$\{?\w*SECRET\w*\}?|\$\{?\w*TOKEN\w*\}?|\$\{?\w*PASSWORD\w*\}?)",
        severity="critical",
        category="data_exfiltration",
    ),
    # ── Destructive Commands ──
    ThreatPattern(
        name="destructive_rm_rf",
        pattern=r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+|--force\s+).*(/|~|\$HOME|\$\{HOME\}|\.\.|/etc|/usr|/var)",
        severity="critical",
        category="destructive",
    ),
    ThreatPattern(
        name="destructive_format_dd",
        pattern=r"(?i)(mkfs|dd\s+if=|format\s+[a-z]:)",
        severity="critical",
        category="destructive",
    ),
    # ── Credential Harvesting ──
    ThreatPattern(
        name="credential_read",
        pattern=r"(?i)(cat|read|type|get-content)\s+.*(\.env|credentials|\.aws|\.ssh|id_rsa|\.gnupg|keychain|\.netrc)",
        severity="critical",
        category="credential_harvesting",
    ),
    # ── Network Callbacks ──
    ThreatPattern(
        name="network_reverse_shell",
        pattern=r"(?i)(nc\s+-[a-z]*l|ncat|socat|bash\s+-i\s+>&\s*/dev/tcp|reverse.shell)",
        severity="critical",
        category="network_callback",
    ),
    # ── AnimaWorks Fixed: Protected File Modification ──
    ThreatPattern(
        name="animaworks_identity_modify",
        pattern=r"(?i)(write|overwrite|replace|modify|edit|update).+(identity\.md|permissions\.(md|json)|bootstrap\.md)",
        severity="high",
        category="protected_file_modification",
    ),
    ThreatPattern(
        name="animaworks_activity_log_tamper",
        pattern=r"(?i)(delete|rm|truncate|clear|purge).+activity_log",
        severity="high",
        category="protected_file_modification",
    ),
    # ── Supply Chain ──
    ThreatPattern(
        name="supply_chain_pip_install",
        pattern=r"(?i)(pip|pip3|npm|yarn|cargo)\s+install\s+(?!-r\s+requirements)",
        severity="medium",
        category="supply_chain",
    ),
    # ── Shell Pipe Dangers ──
    ThreatPattern(
        name="shell_pipe_eval",
        pattern=r"(?i)(curl|wget)\s+.*\|\s*(bash|sh|eval|python|node)",
        severity="critical",
        category="shell_pipe",
    ),
    # ── Privilege Escalation ──
    ThreatPattern(
        name="privilege_escalation",
        pattern=r"(?i)(sudo\s+|chmod\s+[0-7]*7[0-7]*\s+|chown\s+root|setuid|capabilities)",
        severity="medium",
        category="privilege_escalation",
    ),
]

# ── Install Policy Matrix ──────────────────────────────────

_INSTALL_POLICY: dict[str, dict[str, str]] = {
    "builtin": {"safe": "allow", "caution": "allow", "warn": "allow", "dangerous": "block"},
    "official": {"safe": "allow", "caution": "allow", "warn": "allow", "dangerous": "block"},
    "trusted": {"safe": "allow", "caution": "allow", "warn": "ask", "dangerous": "block"},
    "community": {"safe": "allow", "caution": "ask", "warn": "block", "dangerous": "block"},
    "untrusted": {"safe": "ask", "caution": "block", "warn": "block", "dangerous": "block"},
}

# ── Helpers ────────────────────────────────────────────────


def _determine_verdict(findings: list[ScanFinding]) -> SkillScanVerdict:
    """Determine overall verdict from the highest severity finding."""
    if not findings:
        return SkillScanVerdict.safe
    max_rank = max(f.severity_rank for f in findings)
    if max_rank >= _SEVERITY_RANKS["critical"]:
        return SkillScanVerdict.dangerous
    if max_rank >= _SEVERITY_RANKS["high"]:
        return SkillScanVerdict.warn
    if max_rank >= _SEVERITY_RANKS["medium"]:
        return SkillScanVerdict.caution
    return SkillScanVerdict.safe


def _is_binary(path: Path) -> bool:
    """Check if a file is binary based on extension."""
    return path.suffix.lower() in _BINARY_EXTENSIONS


# ── SkillScanner ───────────────────────────────────────────


class SkillScanner:
    """Regex + structure-based security scanner for skill files."""

    def __init__(self, patterns: list[ThreatPattern] | None = None) -> None:
        self._patterns = patterns or THREAT_PATTERNS
        self._compiled: list[tuple[ThreatPattern, re.Pattern[str]]] = [
            (tp, re.compile(tp.pattern)) for tp in self._patterns
        ]

    def scan_file(self, path: Path, *, source: str = "community") -> list[ScanFinding]:
        """Scan a single file for threat patterns and invisible characters.

        Args:
            path: Path to the file to scan.
            source: Provenance label (unused in scan logic, for logging).

        Returns:
            List of findings detected in the file.
        """
        findings: list[ScanFinding] = []

        if not path.exists() or not path.is_file():
            return findings

        if _is_binary(path):
            return findings

        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return findings

        rel_path = str(path.name)

        # Check invisible characters
        for line_num, line in enumerate(content.splitlines(), start=1):
            for char in INVISIBLE_CHARS:
                if char in line:
                    findings.append(
                        ScanFinding(
                            pattern_name="invisible_character",
                            category="obfuscation",
                            severity="high",
                            line_number=line_num,
                            file_path=rel_path,
                            matched_text=f"U+{ord(char):04X}",
                        )
                    )
                    break  # one finding per line for invisible chars

        # Check threat patterns
        for tp, compiled in self._compiled:
            for line_num, line in enumerate(content.splitlines(), start=1):
                m = compiled.search(line)
                if m:
                    findings.append(
                        ScanFinding(
                            pattern_name=tp.name,
                            category=tp.category,
                            severity=tp.severity,
                            line_number=line_num,
                            file_path=rel_path,
                            matched_text=m.group()[:100],
                        )
                    )

        return findings

    def scan_skill(self, skill_dir: Path, *, source: str = "community") -> ScanResult:
        """Scan an entire skill directory for threats.

        Args:
            skill_dir: Path to the skill directory (containing SKILL.md).
            source: Provenance label for logging.

        Returns:
            ScanResult with verdict, findings, and metadata.
        """
        findings: list[ScanFinding] = []
        files_scanned = 0
        files_skipped = 0
        size_violations: list[str] = []

        if not skill_dir.exists():
            return ScanResult(verdict=SkillScanVerdict.safe)

        # Handle single file (not a directory)
        if skill_dir.is_file():
            file_findings = self.scan_file(skill_dir, source=source)
            return ScanResult(
                verdict=_determine_verdict(file_findings),
                findings=file_findings,
                files_scanned=1,
            )

        # Collect all files
        all_files: list[Path] = []
        total_size = 0

        for f in skill_dir.rglob("*"):
            if not f.is_file():
                continue
            all_files.append(f)

        # Check file count limit
        if len(all_files) > MAX_FILES_PER_SKILL:
            size_violations.append(f"File count ({len(all_files)}) exceeds limit ({MAX_FILES_PER_SKILL})")

        # Scan files
        for f in all_files:
            file_size = f.stat().st_size
            total_size += file_size

            if file_size > MAX_SKILL_FILE_SIZE:
                size_violations.append(f"{f.name}: {file_size} bytes exceeds limit ({MAX_SKILL_FILE_SIZE})")
                files_skipped += 1
                continue

            if _is_binary(f):
                files_skipped += 1
                continue

            file_findings = self.scan_file(f, source=source)
            findings.extend(file_findings)
            files_scanned += 1

        # Check total size
        if total_size > MAX_SKILL_DIR_SIZE:
            size_violations.append(f"Total size ({total_size}) exceeds limit ({MAX_SKILL_DIR_SIZE})")

        verdict = _determine_verdict(findings)

        return ScanResult(
            verdict=verdict,
            findings=findings,
            files_scanned=files_scanned,
            files_skipped=files_skipped,
            size_violations=size_violations,
        )

    def should_allow(
        self,
        result: ScanResult,
        trust_level: SkillTrustLevel,
        *,
        force: bool = False,
    ) -> tuple[bool | None, str]:
        """Determine if a skill should be allowed based on scan result and trust.

        Args:
            result: Scan result from ``scan_skill``.
            trust_level: Trust tier of the skill source.
            force: Whether ``--force`` was specified (cannot override ``dangerous``).

        Returns:
            Tuple of (decision, reason):
            - ``(True, reason)``: allow
            - ``(False, reason)``: block
            - ``(None, reason)``: human approval required
        """
        verdict = result.verdict.value
        trust = trust_level.value

        # dangerous is always blocked regardless of force
        if verdict == "dangerous":
            category_summary = ", ".join(sorted({f.category for f in result.findings}))
            return (
                False,
                f"Blocked: dangerous verdict (categories: {category_summary}). Cannot be overridden with --force.",
            )

        # Size violations block regardless
        if result.size_violations:
            return (False, f"Blocked: size violations: {'; '.join(result.size_violations)}")

        # Look up policy
        policy_row = _INSTALL_POLICY.get(trust)
        if policy_row is None:
            # quarantine and blocked trust levels always block
            return (False, f"Blocked: trust level '{trust}' not in install policy")

        decision = policy_row.get(verdict, "block")

        if decision == "allow":
            return (True, f"Allowed: trust={trust}, verdict={verdict}")

        if decision == "ask":
            if force:
                return (True, f"Forced allow: trust={trust}, verdict={verdict} (--force)")
            finding_summary = f"{len(result.findings)} finding(s)"
            return (
                None,
                f"Human approval required: trust={trust}, verdict={verdict}, {finding_summary}",
            )

        # "block"
        if force and verdict != "dangerous":
            return (True, f"Forced allow: trust={trust}, verdict={verdict} (--force)")
        return (False, f"Blocked: trust={trust}, verdict={verdict}")
