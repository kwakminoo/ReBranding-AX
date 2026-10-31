"""Allowlist and content checks for Git's index, not ignored working files."""
from pathlib import Path, PurePosixPath
import hashlib
import io
import json
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {"README.md", "AGENTS.md", ".gitignore", "data/README.md", "data/seed.json", "data/seed.zip"}
PREFIXES = ("scripts/", "skills/", "tests/", "docs/", ".github/workflows/")
PATTERNS = (
    rb"(?i)(?:sk-proj-|ghp_|github_pat_)[a-z0-9_-]{16,}",
    rb"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----",
    rb"(?i)[a-z]:[/\\]users[/\\](?!PUBLIC|EXAMPLE|USER[ /\\])[^/\\\s]+[/\\]",
)

def violations(name, content):
    errors = []
    if name == "data/seed.zip":
        from build_seed import SECRET_PATTERNS
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                manifest = json.loads(z.read("AX-BUNDLE.json"))
                if set(manifest["files"]) != set(z.namelist()) - {"AX-BUNDLE.json"}:
                    errors.append("seed manifest mismatch")
                if sum(i.file_size for i in z.infolist()) > 250_000_000:
                    return ["seed exceeds expected size"]
                for member, expected in manifest["files"].items():
                    parts = PurePosixPath(member).parts
                    if not parts or parts[0] not in ("knowledge", "archive", "clients", "config.json") or ".." in parts or "\\" in member or ":" in member:
                        errors.append("unexpected seed path")
                    raw = z.read(member)
                    if hashlib.sha256(raw).hexdigest() != expected:
                        errors.append("seed content checksum mismatch")
                    if any(re.search(p, raw.decode("utf-8"), re.S) for p in SECRET_PATTERNS):
                        errors.append(f"credential pattern in seed member: {member}")
        except (ValueError, KeyError, zipfile.BadZipFile):
            errors.append("invalid seed archive")
        return errors
    if name not in ROOT_FILES and not name.startswith(PREFIXES):
        errors.append("path not in public allowlist")
    if PurePosixPath(name).suffix.lower() not in (".md", ".py", ".ps1", ".yml", ".yaml", "") and name not in (".gitignore", "data/seed.json"):
        errors.append("unexpected file type")
    if len(content) > 150_000:
        errors.append("unexpectedly large public file")
    if any(re.search(pattern, content) for pattern in PATTERNS):
        errors.append("possible credential or personal absolute path")
    return errors

def main():
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    errors = []
    seed_hash = None
    metadata_hash = None
    for name in filter(None, names):
        content = subprocess.check_output(["git", "show", f":{name}"], cwd=ROOT)
        errors.extend(f"{name}: {error}" for error in violations(name, content))
        if name == "data/seed.zip": seed_hash = hashlib.sha256(content).hexdigest()
        if name == "data/seed.json": metadata_hash = json.loads(content)["sha256"]
    if seed_hash != metadata_hash:
        errors.append("seed.zip and seed.json must be staged together with matching hashes")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        raise SystemExit(1)
    print(f"Public index check passed: {len(list(filter(None, names)))} files. Manual review still required.")

if __name__ == "__main__":
    main()
