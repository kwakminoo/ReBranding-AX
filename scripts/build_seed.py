"""Build the explicitly authorized public seed; exclude credentials and machine history."""
import argparse
import io
import json
from pathlib import Path
import re
import zipfile

import ax

SECRET_PATTERNS = (
    r"(?i)(?:sk-proj-|sk-|ghp_|github_pat_)[a-z0-9_-]{24,}",
    r"AIza[0-9A-Za-z_-]{35}",
    r"(?:AKIA|ASIA)[0-9A-Z]{16}",
    r"xox[baprs]-[0-9A-Za-z-]{20,}",
    r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----.*?-----END (?:RSA |OPENSSH |EC )?PRIVATE KEY-----",
    r"(?i)Bearer\s+[a-z0-9_.-]{32,}",
)
DROP_KEYS = {"account", "creator", "access_token", "refresh_token", "api_key", "password", "authorization", "cookie", "client_secret"}


def clean_text(text, counts):
    for pattern in SECRET_PATTERNS:
        text, count = re.subn(pattern, "[REDACTED_CREDENTIAL]", text, flags=re.S)
        counts["credential_matches"] += count
    text, count = re.subn(r"(?i)([a-z]:[/\\]+Users[/\\]+)[^/\\\s]+", lambda m: m[1] + "USER", text)
    counts["machine_paths"] += count
    return text


def clean_json(value, counts):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key.casefold() in DROP_KEYS:
                counts["metadata_fields"] += 1
            else:
                result[key] = clean_json(item, counts)
        return result
    if isinstance(value, list):
        return [clean_json(v, counts) for v in value]
    return clean_text(value, counts) if isinstance(value, str) else value


def build(root=ax.ROOT):
    data = root / ".local"
    counts = {"credential_matches": 0, "machine_paths": 0, "metadata_fields": 0}
    contents = {}
    for path in sorted(data.rglob("*")):
        rel = path.relative_to(data)
        if not path.is_file() or rel.parts[0] not in ("knowledge", "archive", "clients", "config.json"):
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(data.resolve()):
            raise ValueError("Refusing symlink/outside path")
        if path.suffix not in (".md", ".json"):
            raise ValueError(f"Review non-text file before publishing: {rel}")
        text = path.read_text(encoding="utf-8-sig")
        if path.suffix == ".json":
            text = json.dumps(clean_json(json.loads(text), counts), ensure_ascii=False, indent=2) + "\n"
        else:
            text = clean_text(text, counts)
        contents[rel.as_posix()] = text.encode("utf-8")
    if "knowledge/index.json" not in contents:
        raise ValueError("Import knowledge before creating a seed")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for name, raw in contents.items():
            z.writestr(name, raw)
        z.writestr("AX-BUNDLE.json", json.dumps({"schema": 1, "files": {name: ax.digest(raw) for name, raw in contents.items()}}))
    target = root / "data" / "seed.zip"
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(output.getvalue())
    index = json.loads(contents["knowledge/index.json"])
    metadata = {"schema": 1, "sha256": ax.digest(target.read_bytes()), "files": len(contents),
        "groups": len(index["groups"]), "documents": len(index["documents"]), "personas": len(index["personas"]),
        "redactions": counts, "published_with_user_authorization": True,
        "note": "Original source hashes describe the pre-publication originals. Bundle hashes verify the sanitized release."}
    ax.write_json(root / "data" / "seed.json", metadata)
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-publish-data", action="store_true", required=True)
    parser.parse_args()
    print(json.dumps(build(), ensure_ascii=False, indent=2))
