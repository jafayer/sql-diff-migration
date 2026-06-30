from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommitInfo:
    commit_hash: str
    author_name: str
    author_email: str
    committed_at: str
    subject: str


def _run_git(repo: Path, args: list[str], allow_failure: bool = False) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 and not allow_failure:
        raise GitError(proc.stderr.strip() or proc.stdout.strip() or "git command failed")
    return proc.stdout


def get_head_commit(repo: Path) -> str:
    return _run_git(repo, ["rev-parse", "HEAD"]).strip()


def list_commits(repo: Path, from_commit: str | None, to_commit: str) -> list[str]:
    if from_commit:
        revision = f"{from_commit}..{to_commit}"
    else:
        revision = to_commit

    out = _run_git(repo, ["rev-list", "--reverse", revision])
    commits = [line.strip() for line in out.splitlines() if line.strip()]
    return commits


def read_file_at_commit(repo: Path, commit: str, file_path: Path) -> str | None:
    rel_path = file_path.relative_to(repo)
    out = _run_git(repo, ["show", f"{commit}:{rel_path.as_posix()}"], allow_failure=True)
    if not out:
        # `git show` returns empty output either for empty file or missing file; detect via ls-tree.
        exists = _run_git(
            repo,
            ["ls-tree", "-r", "--name-only", commit, "--", rel_path.as_posix()],
            allow_failure=True,
        ).strip()
        if not exists:
            return None
    return out


def read_file_at_parent(repo: Path, commit: str, file_path: Path) -> str | None:
    parent = _run_git(repo, ["rev-parse", f"{commit}^"], allow_failure=True).strip()
    if not parent:
        return None
    return read_file_at_commit(repo, parent, file_path)


def get_commit_info(repo: Path, commit: str) -> CommitInfo:
    fmt = "%H%x00%an%x00%ae%x00%cI%x00%s"
    out = _run_git(repo, ["show", "-s", f"--format={fmt}", commit]).strip()
    parts = out.split("\x00")
    if len(parts) != 5:
        raise GitError(f"Unexpected git metadata format for commit {commit}")
    return CommitInfo(
        commit_hash=parts[0],
        author_name=parts[1],
        author_email=parts[2],
        committed_at=parts[3],
        subject=parts[4],
    )
