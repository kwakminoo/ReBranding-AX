"""Allowlist and content checks for Git's index, not ignored working files."""
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {"README.md", "AGENTS.md", ".gitignore"}
PREFIXES = ("scripts/", "skills/", "tests/", "docs/", ".github/workflows/")
PATTERNS = (
    rb"(?i)(?:sk-proj-|ghp_|github_pat_)[a-z0-9_-]{16,}",
    rb"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----",
    rb"(?i)[a-z]:[/\\]users[/\\](?!PUBLIC|EXAMPLE|USER[ /\\])[^/\\\s]+[/\\]",
)

def violations(name, content):
    errors = []
    if name not in ROOT_FILES and not name.startswith(PREFIXES):
        errors.append("path not in public allowlist")
    if PurePosixPath(name).suffix.lower() not in (".md", ".py", ".ps1", ".yml", ".yaml", "") and name != ".gitignore":
        errors.append("unexpected file type")
    if len(content) > 150_000:
        errors.append("unexpectedly large public file")
    if any(re.search(pattern, content) for pattern in PATTERNS):
        errors.append("possible credential or personal absolute path")
    return errors

def main():
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    errors = []
    for name in filter(None, names):
        content = subprocess.check_output(["git", "show", f":{name}"], cwd=ROOT)
        errors.extend(f"{name}: {error}" for error in violations(name, content))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        raise SystemExit(1)
    print(f"Public index check passed: {len(list(filter(None, names)))} files. Manual review still required.")

if __name__ == "__main__":
    main()
