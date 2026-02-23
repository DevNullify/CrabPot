"""Network egress policy engine — domain allowlist, blocklist, and secret scanner.

The policy file uses a simple line-based format:
  - One domain per line (e.g., api.openai.com)
  - Wildcards: *.example.com matches sub.example.com
  - Lines starting with # are comments
  - Lines starting with ! are explicitly blocked
  - Empty lines are ignored

The secret scanner is obfuscation-aware: it decodes base64, hex, URL-encoding,
and reversed strings before scanning, to catch attempts to hide credentials.
"""

import base64
import fnmatch
import logging
import math
import re
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

logger = logging.getLogger(__name__)


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    PENDING = "pending"


# ── Secret patterns (compiled for performance) ───────────────────────────────

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # OpenAI
    re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),  # Anthropic
    re.compile(r"(?:AKIA|ABIA|ACCA|ASIA)[A-Z0-9]{16}"),  # AWS access key
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{30,}"),  # Bearer tokens
    re.compile(r"ghp_[A-Za-z0-9]{36}"),  # GitHub PAT
    re.compile(r"glpat-[A-Za-z0-9_-]{20,}"),  # GitLab PAT
    re.compile(r"xox[bpsa]-[A-Za-z0-9-]{10,}"),  # Slack tokens
    re.compile(
        r"(?i)(?:api[_-]?key|api[_-]?secret|access[_-]?token|private[_-]?key)"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9+/=_-]{20,}['\"]?"
    ),
]

# ── Sensitive data patterns (PII / system info) ──────────────────────────────

SENSITIVE_DATA_PATTERNS = [
    # Private IPv4 ranges (attacker wants to map internal network)
    re.compile(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3})\b"),
    re.compile(r"\b(?:172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"),
    re.compile(r"\b(?:192\.168\.\d{1,3}\.\d{1,3})\b"),
    # SSH private key markers
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    # /etc/passwd or /etc/shadow content
    re.compile(r"root:[x*]:0:0:"),
    # Hostname/username in exfiltration context
    re.compile(r"(?i)(?:hostname|username|whoami|uname)\s*[:=]\s*\S+"),
]

# ── Known malicious/exfiltration domains ─────────────────────────────────────

DEFAULT_BLOCKLIST = [
    "*.ngrok.io",
    "*.ngrok-free.app",
    "*.requestbin.com",
    "*.pipedream.net",
    "webhook.site",
    "*.burpcollaborator.net",
    "*.oastify.com",
    "*.interact.sh",
    "*.canarytokens.com",
    "pastebin.com",
    "hastebin.com",
    "*.requestcatcher.com",
    "*.hookbin.com",
]

# ── Entropy threshold for high-entropy string detection ──────────────────────
# Strings with Shannon entropy above this (bits/char) are suspicious.
# English text ≈ 3.5-4.0, random/encoded data ≈ 4.5-6.0, base64 ≈ 5.5-6.0.
ENTROPY_THRESHOLD = 4.8
MIN_ENTROPY_LENGTH = 30  # Only check strings of this length or longer


def _shannon_entropy(s: str) -> float:
    """Calculate Shannon entropy of a string in bits per character."""
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    length = len(s)
    return float(-sum((c / length) * math.log2(c / length) for c in freq.values()))


def _try_decode_base64(s: str) -> str:
    """Attempt to base64-decode a string. Returns decoded text or empty string."""
    # Remove whitespace and common wrappers
    cleaned = re.sub(r"\s+", "", s)
    # Must be valid base64 characters and reasonable length
    if not re.match(r"^[A-Za-z0-9+/=_-]{20,}$", cleaned):
        return ""
    try:
        # Try standard base64
        decoded = base64.b64decode(cleaned, validate=True).decode("utf-8", errors="strict")
        if decoded.isprintable() and len(decoded) > 10:
            return decoded
    except Exception:
        pass
    try:
        # Try URL-safe base64
        decoded = base64.urlsafe_b64decode(cleaned).decode("utf-8", errors="strict")
        if decoded.isprintable() and len(decoded) > 10:
            return decoded
    except Exception:
        pass
    return ""


def _try_decode_hex(s: str) -> str:
    """Attempt to hex-decode a string. Returns decoded text or empty string."""
    cleaned = re.sub(r"[\s:-]", "", s)
    if not re.match(r"^[0-9a-fA-F]{20,}$", cleaned):
        return ""
    if len(cleaned) % 2 != 0:
        return ""
    try:
        decoded = bytes.fromhex(cleaned).decode("utf-8", errors="strict")
        if decoded.isprintable() and len(decoded) > 10:
            return decoded
    except (ValueError, UnicodeDecodeError):
        pass
    return ""


def _try_url_decode(s: str) -> str:
    """URL-decode a string if it contains percent-encoding."""
    if "%" not in s:
        return ""
    try:
        decoded = unquote(s)
        if decoded != s:
            return decoded
    except Exception:
        pass
    return ""


def _deobfuscate_layers(content: str) -> list[str]:
    """Generate deobfuscated variants of content for deep secret scanning.

    Handles: base64, hex, URL-encoding, reversed strings, dot-separated chars.
    Returns a list of decoded strings to scan alongside the original.
    """
    variants = []

    # Find potential base64 blobs (exclude = except as padding at end)
    for match in re.finditer(r"[A-Za-z0-9+/_-]{28,}={0,2}", content):
        decoded = _try_decode_base64(match.group())
        if decoded:
            variants.append(decoded)

    # Find potential hex blobs
    for match in re.finditer(r"(?:[0-9a-fA-F]{2}[\s:-]?){15,}", content):
        decoded = _try_decode_hex(match.group())
        if decoded:
            variants.append(decoded)

    # URL-decode the whole content
    url_decoded = _try_url_decode(content)
    if url_decoded:
        variants.append(url_decoded)

    # Detect dot/dash/space separated chars (e.g., "s.k.-.a.n.t.-.x.y.z")
    separated = re.sub(r"(?<=\S)[.\s,]+(?=\S)", "", content)
    if separated != content and len(separated) > 20:
        variants.append(separated)

    # Check reversed content for reversed secrets
    if len(content) < 2000:  # Don't reverse huge strings
        reversed_content = content[::-1]
        variants.append(reversed_content)

    return variants


class EgressPolicy:
    """Evaluates network egress requests against an allowlist.

    Domains in the allowlist are auto-allowed. Known-bad domains are auto-denied.
    Everything else is classified as PENDING for human review (or auto-denied
    depending on configuration).

    The secret scanner is multi-layered:
      1. Direct pattern matching on plaintext
      2. Deobfuscation (base64/hex/URL/reverse) then pattern matching
      3. Shannon entropy analysis for high-entropy strings (likely encoded secrets)
      4. Sensitive data patterns (private IPs, SSH keys, system info)
    """

    def __init__(
        self,
        policy_path: Optional[Path] = None,
        unknown_action: str = "pending",
    ):
        self._lock = threading.Lock()
        self._allowed: list[str] = []
        self._blocked: list[str] = list(DEFAULT_BLOCKLIST)
        self.unknown_action = unknown_action
        self._session_approved: set[str] = set()
        self._session_denied: set[str] = set()
        self._audit_log: list[dict] = []

        if policy_path and policy_path.exists():
            self._load(policy_path)
        self._policy_path = policy_path

    def _load(self, path: Path) -> None:
        """Load the allowlist/blocklist from a line-based policy file."""
        try:
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("!"):
                    self._blocked.append(line[1:].strip())
                else:
                    self._allowed.append(line)
        except OSError as e:
            logger.warning("Failed to load egress policy from %s: %s", path, e)

    def check_domain(self, domain: str) -> Decision:
        """Evaluate a domain against the policy.

        Returns:
            Decision.ALLOW  — domain is in the allowlist or session-approved
            Decision.DENY   — domain is blocklisted or session-denied
            Decision.PENDING — domain is unknown and needs human review
        """
        domain = domain.lower().strip()

        with self._lock:
            for pattern in self._blocked:
                if self._match(domain, pattern.lower()):
                    return Decision.DENY

            if domain in self._session_denied:
                return Decision.DENY

            for pattern in self._allowed:
                if self._match(domain, pattern.lower()):
                    return Decision.ALLOW

            if domain in self._session_approved:
                return Decision.ALLOW

        if self.unknown_action == "deny":
            return Decision.DENY
        return Decision.PENDING

    def session_approve(self, domain: str) -> None:
        """Approve a domain for this session."""
        with self._lock:
            self._session_approved.add(domain.lower())
            self._session_denied.discard(domain.lower())

    def session_deny(self, domain: str) -> None:
        """Deny a domain for this session."""
        with self._lock:
            self._session_denied.add(domain.lower())
            self._session_approved.discard(domain.lower())

    def add_permanent(self, domain: str) -> None:
        """Add a domain to the permanent allowlist and save."""
        domain = domain.lower().strip()
        with self._lock:
            if domain not in self._allowed:
                self._allowed.append(domain)
        self._save()

    def remove_permanent(self, domain: str) -> None:
        """Remove a domain from the permanent allowlist and save."""
        domain = domain.lower().strip()
        with self._lock:
            self._allowed = [d for d in self._allowed if d != domain]
        self._save()

    def get_allowlist(self) -> list[str]:
        """Return a copy of the current allowlist."""
        with self._lock:
            return list(self._allowed)

    def get_session_approved(self) -> set[str]:
        """Return session-approved domains."""
        with self._lock:
            return set(self._session_approved)

    def log_attempt(self, domain: str, port: int, method: str, decision: str) -> None:
        """Log an egress attempt to the audit trail."""
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "domain": domain,
            "port": port,
            "method": method,
            "decision": decision,
        }
        with self._lock:
            self._audit_log.append(entry)
            if len(self._audit_log) > 5000:
                self._audit_log = self._audit_log[-2500:]

    def get_audit_log(self, last: int = 50) -> list[dict]:
        """Return recent audit log entries."""
        with self._lock:
            return list(self._audit_log[-last:])

    def scan_for_secrets(self, content: str) -> list[str]:
        """Multi-layered secret and sensitive data scanning.

        Layer 1: Direct pattern matching on plaintext.
        Layer 2: Deobfuscation (base64/hex/URL/reverse) + pattern matching.
        Layer 3: Shannon entropy analysis for high-entropy blobs.
        Layer 4: Sensitive data patterns (private IPs, SSH keys, etc.).

        Returns a list of finding descriptions (never exposes the actual secrets).
        """
        findings = []

        # Layer 1: Direct pattern match
        for pattern in SECRET_PATTERNS:
            if pattern.search(content):
                findings.append(f"secret_pattern:{pattern.pattern[:40]}")

        # Layer 2: Deobfuscated variants
        for variant in _deobfuscate_layers(content):
            for pattern in SECRET_PATTERNS:
                if pattern.search(variant):
                    findings.append(f"obfuscated_secret:{pattern.pattern[:40]}")

        # Layer 3: Entropy analysis — flag high-entropy strings
        for match in re.finditer(r"[A-Za-z0-9+/=_-]{30,}", content):
            token = match.group()
            if len(token) >= MIN_ENTROPY_LENGTH:
                entropy = _shannon_entropy(token)
                if entropy >= ENTROPY_THRESHOLD:
                    findings.append(f"high_entropy:{entropy:.1f}bpc_len{len(token)}")

        # Layer 4: Sensitive data patterns
        for pattern in SENSITIVE_DATA_PATTERNS:
            if pattern.search(content):
                findings.append(f"sensitive_data:{pattern.pattern[:40]}")

        return findings

    def _save(self) -> None:
        """Persist the current allowlist back to the policy file."""
        if not self._policy_path:
            return
        try:
            lines = ["# CrabPot Egress Allowlist", "# Managed by crabpot policy commands", ""]
            with self._lock:
                for domain in self._allowed:
                    lines.append(domain)
                lines.append("")
                for pattern in self._blocked:
                    if pattern not in DEFAULT_BLOCKLIST:
                        lines.append(f"!{pattern}")
            self._policy_path.write_text("\n".join(lines) + "\n")
        except OSError as e:
            logger.warning("Failed to save egress policy: %s", e)

    @staticmethod
    def _match(domain: str, pattern: str) -> bool:
        """Match a domain against a pattern (supports *.example.com wildcards)."""
        if pattern == domain:
            return True
        if pattern.startswith("*."):
            suffix = pattern[1:]  # .example.com
            return domain.endswith(suffix) or domain == pattern[2:]
        return fnmatch.fnmatch(domain, pattern)
