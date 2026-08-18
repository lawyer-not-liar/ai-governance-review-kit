from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "check_repository_hygiene.py"


def initialize_repository(path: Path, tracked_files: dict[str, str | bytes]) -> None:
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "symbolic-ref", "HEAD", "refs/heads/main"],
        check=True,
        capture_output=True,
    )
    for relative_name, content in tracked_files.items():
        target = path / relative_name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True, capture_output=True)


def run_scanner(
    path: Path, denylist_file: Path | None = None, *, staged: bool = False
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT), "--root", str(path)]
    if denylist_file is not None:
        command.extend(["--denylist-file", str(denylist_file)])
    if staged:
        command.append("--staged")
    return subprocess.run(command, text=True, capture_output=True, check=False)


def test_clean_tracked_content_passes(tmp_path: Path) -> None:
    initialize_repository(
        tmp_path,
        {"README.md": "A fictional public example owned by alex@example.invalid.\n"},
    )

    result = run_scanner(tmp_path)

    assert result.returncode == 0
    assert result.stdout == "Repository hygiene scan passed.\n"


def test_generic_local_user_path_is_rejected_without_echoing_content(tmp_path: Path) -> None:
    risky_content = "source=" + "/Us" + "ers/alice/private-notes.md\n"
    initialize_repository(tmp_path, {"notes.md": risky_content})

    result = run_scanner(tmp_path)

    assert result.returncode == 1
    assert "notes.md:1: local-user-path" in result.stdout
    assert risky_content.strip() not in result.stdout


def test_local_denylist_match_in_content_is_rejected_and_redacted(tmp_path: Path) -> None:
    initialize_repository(tmp_path, {"notes.md": "Derived from project-saffron.\n"})
    denylist_file = tmp_path / ".repository-local-denylist"
    denylist_file.write_text("project-saffron\n", encoding="utf-8")

    result = run_scanner(tmp_path, denylist_file)

    assert result.returncode == 1
    assert "notes.md:1: local-denylist" in result.stdout
    assert "project-saffron" not in result.stdout


def test_local_denylist_match_in_filename_is_rejected(tmp_path: Path) -> None:
    initialize_repository(tmp_path, {"project-saffron-notes.md": "Public-looking text.\n"})
    denylist_file = tmp_path / ".repository-local-denylist"
    denylist_file.write_text("project-saffron\n", encoding="utf-8")

    result = run_scanner(tmp_path, denylist_file)

    assert result.returncode == 1
    assert "local-denylist-filename" in result.stdout
    assert "project-saffron" not in result.stdout


def test_blank_and_comment_denylist_lines_are_ignored(tmp_path: Path) -> None:
    initialize_repository(tmp_path, {"README.md": "A clean public example.\n"})
    denylist_file = tmp_path / ".repository-local-denylist"
    denylist_file.write_text("# local exclusions\n\n   # another comment\n", encoding="utf-8")

    result = run_scanner(tmp_path, denylist_file)

    assert result.returncode == 0


def test_default_local_denylist_is_loaded(tmp_path: Path) -> None:
    initialize_repository(tmp_path, {"notes.md": "Do not publish project-saffron.\n"})
    (tmp_path / ".repository-local-denylist").write_text("project-saffron\n", encoding="utf-8")

    result = run_scanner(tmp_path)

    assert result.returncode == 1
    assert "notes.md:1: local-denylist" in result.stdout
    assert "project-saffron" not in result.stdout


def test_binary_file_is_rejected_but_untracked_file_is_ignored(tmp_path: Path) -> None:
    binary_content = b"\x00" + ("/Us" + "ers/alice/secret").encode()
    initialize_repository(tmp_path, {"asset.bin": binary_content, "README.md": "Clean.\n"})
    (tmp_path / "untracked.txt").write_text("/Us" + "ers/alice/secret\n", encoding="utf-8")

    result = run_scanner(tmp_path)

    assert result.returncode == 1
    assert "asset.bin:0: binary-file" in result.stdout


def test_sensitive_filename_is_rejected(tmp_path: Path) -> None:
    initialize_repository(tmp_path, {"credentials.json": "{}\n"})

    result = run_scanner(tmp_path)

    assert result.returncode == 1
    assert "credentials.json:0: sensitive-filename" in result.stdout


def test_staged_scan_reads_index_instead_of_clean_worktree(tmp_path: Path) -> None:
    risky_content = "source=" + "/Us" + "ers/alice/private-notes.md\n"
    initialize_repository(tmp_path, {"notes.md": risky_content})
    (tmp_path / "notes.md").write_text("Clean working-tree replacement.\n", encoding="utf-8")

    result = run_scanner(tmp_path, staged=True)

    assert result.returncode == 1
    assert "notes.md:1: local-user-path" in result.stdout
