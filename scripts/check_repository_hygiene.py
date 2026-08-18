#!/usr/bin/env python3
"""Reject tracked content that matches repository safety rules."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

GENERIC_RULES = (
    (
        "private-key",
        re.compile(r"-{5}BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-{5}"),
    ),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "local-user-path",
        re.compile(re.escape("/" + "Users" + "/") + r"[^/\s]+/"),
    ),
    (
        "windows-user-path",
        re.compile(r"[A-Za-z]:\\" + re.escape("Users") + r"\\[^\\\s]+\\", re.IGNORECASE),
    ),
    (
        "hosted-ticket-url",
        re.compile(r"https?://[A-Za-z0-9.-]+\.atlassian\.net(?:/|\b)", re.IGNORECASE),
    ),
)

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b", re.IGNORECASE)
ALLOWED_EMAIL_DOMAINS = {
    "example.com",
    "example.invalid",
    "example.net",
    "example.org",
    "users.noreply.github.com",
}
PRIVATE_DIRECTORY_SEQUENCES = {
    (".codex",),
    ("docs", "superpowers"),
    ("internal",),
    ("private",),
    ("_private",),
}
SENSITIVE_FILENAMES = {
    "credentials.json",
    "id_ed25519",
    "id_rsa",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
}
SENSITIVE_SUFFIXES = {".key", ".p12", ".pem", ".pfx"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Git repository root")
    parser.add_argument(
        "--denylist-file",
        type=Path,
        help="Untracked file containing one literal exclusion per line",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Scan the content staged in the Git index instead of the working tree",
    )
    return parser.parse_args()


def tracked_paths(root: Path) -> list[PurePosixPath]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(message or "unable to list tracked files")
    return [
        PurePosixPath(raw.decode("utf-8", errors="surrogateescape"))
        for raw in result.stdout.split(b"\0")
        if raw
    ]


def load_denylist(path: Path | None, root: Path) -> list[str]:
    denylist_path = path if path is not None else root / ".repository-local-denylist"
    if path is None and not denylist_path.exists():
        return []
    if not denylist_path.is_file():
        raise RuntimeError(f"local denylist not found: {denylist_path}")
    entries = []
    for line in denylist_path.read_text(encoding="utf-8").splitlines():
        entry = line.strip()
        if entry and not entry.startswith("#"):
            entries.append(entry.casefold())
    return entries


def path_has_private_directory(path: PurePosixPath) -> bool:
    parts = tuple(part.casefold() for part in path.parts[:-1])
    for sequence in PRIVATE_DIRECTORY_SEQUENCES:
        width = len(sequence)
        if any(parts[index : index + width] == sequence for index in range(len(parts) - width + 1)):
            return True
    return False


def path_has_sensitive_filename(path: PurePosixPath) -> bool:
    name = path.name.casefold()
    if name in SENSITIVE_FILENAMES or Path(name).suffix in SENSITIVE_SUFFIXES:
        return True
    allowed_environment_examples = {".env.example", ".env.sample"}
    return name == ".env" or (name.startswith(".env.") and name not in allowed_environment_examples)


def read_tracked_text(root: Path, relative: PurePosixPath, *, staged: bool) -> str | None:
    if staged:
        result = subprocess.run(
            ["git", "-C", str(root), "show", "--no-textconv", f":./{relative.as_posix()}"],
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            message = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"unable to read staged file {relative}: {message}")
        raw = result.stdout
    else:
        path = root.joinpath(*relative.parts)
        try:
            raw = os.readlink(path).encode("utf-8") if path.is_symlink() else path.read_bytes()
        except OSError as exc:
            raise RuntimeError(f"unable to read tracked file {relative}: {exc}") from exc
    if b"\0" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def safe_display_path(relative: PurePosixPath, denylist: list[str]) -> str:
    rendered = relative.as_posix()
    folded = rendered.casefold()
    if any(entry in folded for entry in denylist):
        return "<redacted-path>"
    return json.dumps(rendered, ensure_ascii=True)[1:-1]


def scan(root: Path, denylist: list[str], *, staged: bool = False) -> list[tuple[str, int, str]]:
    findings: list[tuple[str, int, str]] = []
    for relative in tracked_paths(root):
        display_path = safe_display_path(relative, denylist)
        folded_path = relative.as_posix().casefold()
        if path_has_private_directory(relative):
            findings.append((display_path, 0, "private-directory"))
        if path_has_sensitive_filename(relative):
            findings.append((display_path, 0, "sensitive-filename"))
        if any(entry in folded_path for entry in denylist):
            findings.append((display_path, 0, "local-denylist-filename"))

        text = read_tracked_text(root, relative, staged=staged)
        if text is None:
            findings.append((display_path, 0, "binary-file"))
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for rule_name, pattern in GENERIC_RULES:
                if pattern.search(line):
                    findings.append((display_path, line_number, rule_name))
            for match in EMAIL_PATTERN.finditer(line):
                if match.group(1).casefold() not in ALLOWED_EMAIL_DOMAINS:
                    findings.append((display_path, line_number, "non-example-email"))
            folded_line = line.casefold()
            if any(entry in folded_line for entry in denylist):
                findings.append((display_path, line_number, "local-denylist"))
    return sorted(set(findings))


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    try:
        denylist = load_denylist(args.denylist_file, root)
        findings = scan(root, denylist, staged=args.staged)
    except RuntimeError as exc:
        print(f"Repository hygiene scan could not run: {exc}", file=sys.stderr)
        return 2

    if findings:
        print("Repository hygiene scan failed:")
        for path, line_number, rule_name in findings:
            print(f"{path}:{line_number}: {rule_name}")
        return 1

    print("Repository hygiene scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
