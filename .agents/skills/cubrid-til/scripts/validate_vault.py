#!/usr/bin/env python3
"""Validate CUBRID TIL metadata, links, and publish safety."""

from __future__ import annotations

import argparse
import ipaddress
import re
import sys
from pathlib import Path

LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
IPV4_RE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"(?:gh[opurs]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "credential assignment": re.compile(
        r"(?im)^\s*(?:password|passwd|api[_-]?key|secret|token)\s*[:=]\s*[^<\s][^\s]*\s*$"
    ),
    "internal hostname": re.compile(r"\b[a-z0-9][a-z0-9.-]*\.(?:internal|corp|local)\b", re.I),
}
REQUIRED_STATE_SECTIONS = {
    "현재 세션",
    "BFS Frontier",
    "후속 주제 큐",
    "완료 주제",
    "이전 추천 결과",
    "보류 및 미해결 질문",
}


def frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    result: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip().strip('"\'')
    return result


def visible_markdown(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("*.md"):
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if relative.parts[0] == "Templates" or relative.name == "AGENTS.md":
            continue
        files.append(path)
    return sorted(files)


def text_files(root: Path) -> list[Path]:
    extensions = {".md", ".py", ".json", ".toml", ".txt", ".yaml", ".yml"}
    files = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink() or path.suffix.lower() not in extensions:
            continue
        relative = path.relative_to(root)
        if ".git" in relative.parts or ".obsidian" in relative.parts or "__pycache__" in relative.parts:
            continue
        files.append(path)
    return sorted(files)


def is_sensitive_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    documentation_ranges = (
        ipaddress.ip_network("192.0.2.0/24"),
        ipaddress.ip_network("198.51.100.0/24"),
        ipaddress.ip_network("203.0.113.0/24"),
    )
    if address.is_loopback or address.is_unspecified or any(address in network for network in documentation_ranges):
        return False
    return address.is_private or not address.is_global


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--public", action="store_true", help="require every note to be public-ready")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    files = visible_markdown(root)
    errors: list[str] = []
    warnings: list[str] = []
    by_stem: dict[str, list[Path]] = {}
    texts: dict[Path, str] = {}

    for path in files:
        text = path.read_text(encoding="utf-8")
        texts[path] = text
        by_stem.setdefault(path.stem.casefold(), []).append(path)
        metadata = frontmatter(text)
        relative = path.relative_to(root)

        if not metadata.get("visibility"):
            errors.append(f"{relative}: missing visibility frontmatter")
        elif metadata["visibility"] == "restricted":
            errors.append(f"{relative}: restricted content blocks automatic push")
        elif args.public and metadata["visibility"] != "public":
            errors.append(f"{relative}: visibility is not public")


    for path in text_files(root):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(root)
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"{relative}: possible {name}")
        for match in IPV4_RE.finditer(text):
            if is_sensitive_ip(match.group(0)):
                errors.append(f"{relative}: possible real infrastructure IP {match.group(0)}")

    for stem, paths in by_stem.items():
        if len(paths) > 1:
            joined = ", ".join(str(path.relative_to(root)) for path in paths)
            errors.append(f"duplicate note title {stem!r}: {joined}")

    known = set(by_stem)
    for path, text in texts.items():
        relative = path.relative_to(root)
        for target in LINK_RE.findall(text):
            normalized = Path(target.strip()).name.casefold()
            if normalized not in known:
                errors.append(f"{relative}: unresolved wikilink [[{target}]]")

    state = root / "Learning State.md"
    if not state.exists():
        errors.append("Learning State.md: missing")
    else:
        headings = set(re.findall(r"^##\s+(.+?)\s*$", texts.get(state, state.read_text(encoding="utf-8")), re.M))
        for section in sorted(REQUIRED_STATE_SECTIONS - headings):
            errors.append(f"Learning State.md: missing section {section!r}")

    if not args.public:
        internal_count = sum(
            frontmatter(text).get("visibility") == "internal" for text in texts.values()
        )
        if internal_count:
            warnings.append(f"{internal_count} internal note(s) require review before making the repository public")

    for warning in warnings:
        print(f"WARN: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    print(f"Validated {len(files)} note(s): {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
