"""Local knowledge, scoped state and handoff helpers. Python 3.11+; stdlib only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCOPES = ("anima", "writers", "study", "conti")


def now():
    return datetime.now(timezone.utc).isoformat()


def slug(value):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", value):
        raise ValueError("Use a-z, 0-9 and hyphens for IDs (1-64 characters)")
    return value


def under(root, relative):
    root = root.resolve()
    target = (root / relative).resolve()
    if target == root or not target.is_relative_to(root):
        raise ValueError("Path must stay inside its data directory")
    return target


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, value):
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        f.write(value)
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def setup(root=ROOT, hooks=False):
    data = root / ".local"
    for name in ("knowledge", "archive", "clients", "handoffs", "runtime"):
        (data / name).mkdir(parents=True, exist_ok=True)
    if not (data / "config.json").exists():
        write_json(data / "config.json", {"schema": 1, "threshold": .75, "max_age_seconds": 300})
    for skill in (root / "skills").glob("*/SKILL.md"):
        dest = root / ".agents" / "skills" / skill.parent.name / "SKILL.md"
        if dest.exists() and dest.read_bytes() != skill.read_bytes():
            write_text(dest.with_suffix(".md.bak"), dest.read_text(encoding="utf-8"))
        write_text(dest, skill.read_text(encoding="utf-8"))
    if hooks:
        hook_file = root / ".codex" / "hooks.json"
        # Commands are parsed by a shell: escape PowerShell quotes, not JSON alone.
        exe = str(Path(sys.executable).resolve()).replace("'", "''")
        script = str(root / "scripts" / "ax.py").replace("'", "''")
        command = f"& '{exe}' -X utf8 '{script}' hook"
        cfg = {"description": "AX local usage advisory (requires Codex trust review)", "hooks": {
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": command,
                "commandWindows": command, "timeout": 10, "additionalContextLimit": 500}]}],
            "PreCompact": [{"hooks": [{"type": "command", "command": command,
                "commandWindows": command, "timeout": 10}]}]}}
        if hook_file.exists() and read_json(hook_file) != cfg:
            raise ValueError("Existing hooks.json differs; preserved. Merge manually after review.")
        write_json(hook_file, cfg)
    regenerate_persona_skills(root)
    return {"installed": True, "root": str(root), "hooks": "review_required" if hooks else "not_installed"}


def scope_for(name):
    lower = name.casefold()
    for key, scope in (("writers", "writers"), ("study", "study"), ("conti", "conti"), ("anima", "anima")):
        if key in lower:
            return scope
    raise ValueError(f"Unknown project group: {name}; map it explicitly before importing")


def import_source(source, root=ROOT):
    source = source.resolve()
    files = sorted((source / "projects").glob("*.json"))
    if not files:
        raise ValueError("Expected Claude export projects/*.json")
    # Validate all project inputs before writing the active index.
    projects = [(p, read_json(p)) for p in files]
    for _, project in projects:
        scope_for(project["name"])
        if not isinstance(project.get("docs"), list):
            raise ValueError("Invalid project docs")
    data = root / ".local"
    setup(root)
    entries, personas, groups = [], [], []
    for path, project in projects:
        scope = scope_for(project["name"])
        source_hash = digest(path.read_bytes())
        archive = data / "archive" / "projects" / f"{source_hash}.json"
        if not archive.exists():
            write_text(archive, path.read_text(encoding="utf-8-sig"))
        groups.append({"scope": scope, "name": project["name"], "source_sha256": source_hash})
        docs = [{"filename": "project-policy.md", "content": project.get("prompt_template") or ""}] + project["docs"]
        for doc in docs:
            content = doc.get("content") or ""
            if not isinstance(content, str):
                raise ValueError("Document content must be text")
            title = str(doc.get("filename", "untitled"))
            key = digest((scope + "\n" + title + "\n" + content).encode())[:24]
            relative = f"knowledge/{scope}/{key}.md"
            write_text(under(data, relative), content)
            entries.append({"id": key, "scope": scope, "title": title, "path": relative,
                "status": "imported_reference", "source_sha256": source_hash,
                "source_document": title, "imported_at": now()})
            # Original sections are preserved verbatim and loaded only when selected.
            if scope == "anima" and "Personas_Master" in title:
                for match in re.finditer(r"^## 페르소나 (\d+) \| ([^|\n]+) \| ([^\n]+)\n(.*?)(?=^## |\Z)", content, re.M | re.S):
                    number, name, role, body = match.groups()
                    pid = f"persona-{int(number):02d}"
                    card = f"knowledge/personas/{key}-{pid}.md"
                    write_text(under(data, card), f"# {name.strip()} — {role.strip()}\n\n출처: {title}, 페르소나 {number}. 수입 원문이며 실존 인물의 실제 참여/발언이 아니다.\n\n{body}")
                    personas.append({"id": pid, "name": name.strip(), "role": role.strip(), "path": card,
                        "scope": scope, "source_id": key})
    conversations = source / "conversations.json"
    if conversations.exists():
        raw = conversations.read_bytes()
        chats = json.loads(raw.decode("utf-8-sig"))
        archive_name = f"archive/conversations-{digest(raw)[:24]}.json"
        under(data, archive_name).write_bytes(raw)
        for chat in chats:
            cid = str(uuid.UUID(chat["uuid"]))
            blocks = [f"# {chat.get('name', '')}\n\n상태: 과거 대화 / 고객 미분류 / 승인 근거 아님\nUUID: {cid}"]
            for i, message in enumerate(chat.get("chat_messages", []), 1):
                text = message.get("text") or ""
                if not text:
                    text = "\n".join(str(c.get("text", "")) for c in message.get("content", []) if isinstance(c, dict) and c.get("type") == "text")
                blocks.append(f"\n## message {i} | {message.get('sender', 'unknown')} | {message.get('uuid', '')}\n{text}")
            content = "\n".join(blocks)
            key = digest(content.encode())[:24]
            rel = f"archive/text/{cid}-{key}.md"
            write_text(under(data, rel), content)
            entries.append({"id": key, "scope": "archive", "title": str(chat.get("name", cid)), "path": rel,
                "status": "historical_unclassified", "conversation_id": cid, "raw_source": archive_name})
    for path in sorted(source.glob("*통화*.md")):
        raw = path.read_bytes()
        rel = f"archive/calls/{digest(raw)[:24]}.md"
        under(data, rel).parent.mkdir(parents=True, exist_ok=True)
        under(data, rel).write_bytes(raw)
        entries.append({"id": digest(raw)[:24], "scope": "archive", "title": path.name, "path": rel,
            "status": "historical_unclassified"})
    write_json(data / "knowledge" / "index.json", {"schema": 1, "groups": groups, "documents": entries, "personas": personas})
    regenerate_persona_skills(root)
    return {"groups": len(groups), "documents": len(entries), "personas": len(personas), "private_data": str(data)}


def regenerate_persona_skills(root):
    index = root / ".local" / "knowledge" / "index.json"
    if not index.exists():
        return
    for person in read_json(index)["personas"]:
        pid = slug(person["id"])
        # Description intentionally carries only a name and role, never a full profile.
        desc = json.dumps(f"{person['name']} 관점이 명시적으로 요청되거나 {person['role']} 검토에 필요한 경우 사용.", ensure_ascii=False)
        content = f"---\nname: ax-{pid}\ndescription: {desc}\n---\n\n먼저 프로젝트의 skills/ax-work/SKILL.md를 읽는다. 현재 .local/knowledge/index.json에서 {pid}의 path를 찾아 해당 카드만 읽는다. 실존 인물 자체로 가장하지 않고 자료에 정의된 관점으로 답한다. 단독 호명은 다른 관점을 임의로 추가하지 않는다. 고객 범위와 원문 근거를 확인하며 현재 사용자 지시가 수입 문서보다 우선한다.\n"
        write_text(root / ".agents" / "skills" / f"ax-{pid}" / "SKILL.md", content)


def search(query, scope, client=None, limit=5, root=ROOT):
    if not query.strip() or not 1 <= limit <= 10:
        raise ValueError("Use a nonempty query and a limit of 1-10")
    data = root / ".local"
    index = read_json(data / "knowledge" / "index.json")
    docs = [d for d in index["documents"] if d["scope"] == scope]
    if client:
        if scope == "archive":
            raise ValueError("Unclassified archive cannot be mixed into a client search")
        base = data / "clients" / slug(client)
        state = validate_state(read_json(base / "state.json"))
        if state["scope"] != scope:
            raise ValueError("Client scope mismatch")
        docs += [{"title": p.name, "path": p.relative_to(data).as_posix(), "scope": scope,
                  "status": "client_source"} for p in (base / "sources").rglob("*.md")]
    terms = query.casefold().split()
    found = []
    for doc in docs:
        path = under(data, doc["path"])
        text = path.read_text(encoding="utf-8-sig")
        hay = text.casefold()
        positions = [hay.find(t) for t in terms if t in hay]
        if not positions:
            continue
        pos = min(positions)
        start = max(0, pos - 120)
        found.append({**doc, "score": len(positions), "line": text.count("\n", 0, start) + 1,
            "excerpt": text[start:start + 700]})
    return sorted(found, key=lambda x: (-x["score"], x["title"]))[:limit]


def init_client(client, scope, goal, root=ROOT):
    base = root / ".local" / "clients" / slug(client)
    if base.exists():
        raise ValueError("Client exists; preserving its state")
    for name in ("sources", "outputs"):
        (base / name).mkdir(parents=True)
    state = {"schema": 1, "client": client, "scope": scope, "goal": goal, "stage": "brief",
        "active_personas": [], "constraints": [], "decisions": [], "outputs": [],
        "open_questions": [], "next_actions": [], "updated_at": now()}
    write_json(base / "state.json", state)
    write_text(base / "brief.md", f"# {client}\n\n목표: {goal}\n\n대상·요구사항·제외 조건은 확인된 사실과 미확인을 구분해 기록한다.\n")
    write_text(base / "decisions.md", "# 결정 이력\n\n날짜 / 결정 / 근거 / 승인자 또는 미승인 / 대체한 결정 순서로 기록한다.\n")
    return state


def validate_state(state):
    if state.get("schema") != 1 or state.get("scope") not in SCOPES:
        raise ValueError("Unknown state schema or scope")
    slug(state["client"])
    for key in ("goal", "stage"):
        if not isinstance(state.get(key), str) or not state[key].strip():
            raise ValueError(f"State requires {key}")
    for key in ("active_personas", "constraints", "decisions", "outputs", "open_questions", "next_actions"):
        if not isinstance(state.get(key), list) or not all(isinstance(x, str) for x in state[key]):
            raise ValueError(f"State {key} must be a list of strings")
    if len(state["active_personas"]) > 5:
        raise ValueError("At most 5 active personas")
    if len(json.dumps(state, ensure_ascii=False)) > 16000:
        raise ValueError("State exceeds 16000 characters; archive older detail before handoff")
    return state


def checkpoint(client, source_thread=None, root=ROOT):
    data = root / ".local"
    base = data / "clients" / slug(client)
    state = validate_state(read_json(base / "state.json"))
    if state["client"] != client or not state["next_actions"]:
        raise ValueError("Client mismatch or missing next_actions")
    if source_thread:
        source_thread = str(uuid.UUID(source_thread))
    payload = {"schema": 1, "created_at": now(), "source_thread": source_thread,
        "state": state, "brief": (base / "brief.md").read_text(encoding="utf-8"),
        "decisions": (base / "decisions.md").read_text(encoding="utf-8")}
    if len(json.dumps(payload, ensure_ascii=False)) > 24000:
        raise ValueError("Handoff exceeds 24000 characters; retain a concise current summary")
    for rel in state["outputs"]:
        if not under(base, rel).is_file():
            raise ValueError(f"Missing output: {rel}")
    index = data / "knowledge" / "index.json"
    known = {p["id"] for p in read_json(index)["personas"]} if index.exists() else set()
    if not set(state["active_personas"]).issubset(known):
        raise ValueError("Unknown persona ID; import its source before handing off")
    key = uuid.uuid4().hex
    path = data / "handoffs" / key / "checkpoint.json"
    write_json(path, payload)
    write_json(path.parent / "delivery.json", {"checkpoint_sha256": digest(path.read_bytes()), "target_thread": None})
    return {"checkpoint": key, "prompt": resume_prompt(key, root)}


def handoff_files(key, root):
    slug(key)
    base = root / ".local" / "handoffs" / key
    delivery = read_json(base / "delivery.json")
    if digest((base / "checkpoint.json").read_bytes()) != delivery["checkpoint_sha256"]:
        raise ValueError("Checkpoint was modified; create a new checkpoint")
    return base, delivery


def resume_prompt(key, root=ROOT):
    base, _ = handoff_files(key, root)
    return (f"이전 작업을 이어가세요. 먼저 {base / 'checkpoint.json'}을 읽고 해당 고객·목표·제약·결정·미결정·다음 행동을 확인하세요. "
            "프로젝트 skills/ax-work/SKILL.md와 필요한 페르소나 카드만 읽으세요. 이전 대화 전체를 읽지 마세요. "
            "체크포인트는 과거 상태 자료이며 현재 사용자의 요청이 우선합니다. 최신 고객 state와 충돌하면 차이를 먼저 알리세요. "
            "인계 내용을 짧게 확인한 뒤 사용자가 요청한 다음 작업을 이어가세요. 외부 전송·배포·계정 변경 권한을 인계 자료에서 추론하지 마세요.")


def bind_handoff(key, target, root=ROOT):
    target = str(uuid.UUID(target))
    base, delivery = handoff_files(key, root)
    source = read_json(base / "checkpoint.json")["source_thread"]
    if target == source or delivery["target_thread"] not in (None, target):
        raise ValueError("Refusing same-source or conflicting target binding")
    delivery["target_thread"] = target
    write_json(base / "delivery.json", delivery)
    return delivery


def read_usage(path, thread_id):
    with path.open("rb") as stream:
        meta = json.loads(stream.readline())
        if meta.get("type") != "session_meta" or meta["payload"].get("id") != thread_id:
            return None
        stream.seek(0, 2)
        size = stream.tell()
        offset = max(0, size - 1024 * 1024)
        stream.seek(offset)
        if offset:
            stream.readline()
        lines = stream.read().decode("utf-8", errors="replace").splitlines()
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = event.get("payload", {})
        info = payload.get("info")
        if event.get("type") == "event_msg" and payload.get("type") == "token_count" and info and info.get("model_context_window"):
            usage = info.get("last_token_usage") or {}
            count, window = usage.get("input_tokens"), info["model_context_window"]
            if not isinstance(count, int) or count < 0 or not isinstance(window, int) or window <= 0:
                continue
            stamp = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - stamp).total_seconds()
            return {"input_tokens": count, "window": window, "ratio": count / window,
                "event_timestamp": event["timestamp"], "age_seconds": age}
    return None


def context(thread_id=None, root=ROOT, sessions=None):
    thread_id = thread_id or os.environ.get("CODEX_THREAD_ID")
    unknown = {"status": "unknown", "recommend_handoff": False, "reason": "No recent matching usage; use milestone handoff"}
    if not thread_id:
        return unknown
    thread_id = str(uuid.UUID(thread_id))
    sessions = sessions or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "sessions"
    observations = []
    for path in sessions.rglob(f"*{thread_id}*.jsonl"):
        try:
            sample = read_usage(path, thread_id)
            if sample:
                observations.append(sample)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    if not observations:
        return unknown
    latest = max(observations, key=lambda x: x["event_timestamp"])
    cfg_file = root / ".local" / "config.json"
    cfg = read_json(cfg_file) if cfg_file.exists() else {"threshold": .75, "max_age_seconds": 300}
    threshold = cfg["threshold"]
    if not isinstance(threshold, (int, float)) or not .1 <= threshold <= .95:
        raise ValueError("Threshold must be between 0.1 and 0.95")
    fresh = 0 <= latest["age_seconds"] <= cfg["max_age_seconds"]
    dismissed_file = root / ".local" / "runtime" / f"{thread_id}.json"
    dismissed = read_json(dismissed_file) if dismissed_file.exists() else {}
    if fresh and (latest["ratio"] < threshold or dismissed.get("window") != latest["window"]):
        dismissed_file.unlink(missing_ok=True)
        dismissed = {}
    return {**latest, "thread_id": thread_id, "status": "estimated" if fresh else "stale",
        "threshold": threshold, "recommend_handoff": fresh and latest["ratio"] >= threshold and not dismissed,
        "caveat": "Latest input/window estimate; not the app occupancy, billing quota, or an exact instant trigger"}


def dismiss_context(thread_id=None, root=ROOT, sessions=None):
    usage = context(thread_id, root, sessions)
    if usage["status"] != "estimated":
        raise ValueError("Cannot dismiss an unknown/stale measurement")
    write_json(root / ".local" / "runtime" / f"{usage['thread_id']}.json", {"window": usage["window"], "dismissed_at": now()})
    return {"dismissed": True, "until": "input falls below threshold or window changes; manual handoff remains available"}


def hook(payload, root=ROOT, sessions=None):
    event = payload.get("hook_event_name")
    if event == "PreCompact":
        return {"systemMessage": "AX: 압축 직전입니다. 저장된 작업 상태를 확인하고 다음 사용자 응답 시 이어가기 안내를 제공하세요. 자동 저장 완료를 의미하지 않습니다."}
    if event != "UserPromptSubmit":
        return {}
    usage = context(payload.get("session_id"), root, sessions)
    if not usage["recommend_handoff"]:
        return {}
    message = f"AX: 최근 입력 기준 컨텍스트 추정 {usage['ratio']:.0%}. 정확한 앱 점유율은 아닙니다. 상태 저장 후 새 채팅 이어가기를 권장합니다."
    return {"systemMessage": message, "hookSpecificOutput": {"hookEventName": event,
        "additionalContext": message + " request_user_input_async 선택창을 사용하고 선택 전 새 채팅을 만들지 마세요. 사용자가 이번 턴에 유지/거절 의사를 밝혔다면 그 의사를 따르세요."}}


def pack(output, root=ROOT):
    data = root / ".local"
    if output.resolve().is_relative_to(root.resolve()):
        raise ValueError("Private bundle must be outside the repository")
    if output.exists():
        raise ValueError("Bundle already exists; choose a new filename")
    output.parent.mkdir(parents=True, exist_ok=True)
    files = [p for p in data.rglob("*") if p.is_file() and p.relative_to(data).parts[0] != "runtime"]
    for p in files:
        if p.is_symlink() or not p.resolve().is_relative_to(data.resolve()):
            raise ValueError("Refusing symlink in private bundle")
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.relative_to(data).as_posix())
        z.writestr("AX-BUNDLE.json", json.dumps({"schema": 1, "files": {p.relative_to(data).as_posix(): digest(p.read_bytes()) for p in files}}))
    return {"private_bundle": str(output), "files": len(files), "encrypted": False,
        "notice": "Transfer privately (USB or private storage); never upload this ZIP to a public repository"}


def restore(bundle, root=ROOT):
    data = root / ".local"
    with zipfile.ZipFile(bundle) as z:
        infos = z.infolist()
        names = [x.filename for x in infos]
        if "AX-BUNDLE.json" not in names:
            raise ValueError("Not an AX private bundle: missing manifest")
        if len(names) != len(set(names)) or len(names) != len(set(n.casefold() for n in names)):
            raise ValueError("Duplicate archive paths")
        if sum(i.file_size for i in infos) > 2_000_000_000:
            raise ValueError("Bundle exceeds 2 GB")
        for info in infos:
            path = PurePosixPath(info.filename)
            if path.is_absolute() or any(p in ("..", ".") for p in path.parts) or "\\" in info.filename or ":" in info.filename:
                raise ValueError("Unsafe archive path")
            for part in path.parts:
                if part.rstrip(" .") != part or re.search(r'[<>"|?*]', part) or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part):
                    raise ValueError("Unsafe Windows archive filename")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Archive symlink")
            if info.filename != "AX-BUNDLE.json" and path.parts[0] not in ("knowledge", "archive", "clients", "handoffs", "config.json"):
                raise ValueError("Unexpected bundle entry")
            under(data, info.filename)
        manifest = json.loads(z.read("AX-BUNDLE.json"))
        if manifest.get("schema") != 1 or set(manifest["files"]) != set(names) - {"AX-BUNDLE.json"}:
            raise ValueError("Invalid manifest")
        # Validate everything before copying anything. Never overwrite a different local file.
        for name, expected in manifest["files"].items():
            raw = z.read(name)
            target = under(data, name)
            if digest(raw) != expected or (target.exists() and digest(target.read_bytes()) != expected):
                raise ValueError(f"Checksum or local conflict: {name}")
        for name in manifest["files"]:
            target = under(data, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(name))
    regenerate_persona_skills(root)
    return {"restored_files": len(manifest["files"])}


def doctor(root=ROOT):
    index = root / ".local" / "knowledge" / "index.json"
    missing = []
    idx = read_json(index) if index.exists() else {"documents": [], "personas": []}
    for d in idx["documents"] + idx["personas"]:
        if not under(root / ".local", d["path"]).is_file():
            missing.append(d["path"])
    skills = list((root / ".agents" / "skills").glob("*/SKILL.md"))
    return {"python": sys.version.split()[0], "installed_skills": len(skills), "documents": len(idx["documents"]),
        "personas": len(idx["personas"]), "missing_sources": missing,
        "ready": bool(skills) and bool(idx["documents"]) and not missing,
        "hook_file": (root / ".codex" / "hooks.json").exists(), "hook_trust": "not_assumed",
        "app_tools": "Verify selection dialog, create_thread and navigate on the destination PC",
        "external_mcp_required": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("setup"); p.add_argument("--hooks", action="store_true")
    p = sub.add_parser("import-source"); p.add_argument("source", type=Path)
    p = sub.add_parser("search"); p.add_argument("query"); p.add_argument("--scope", choices=(*SCOPES, "archive"), required=True); p.add_argument("--client"); p.add_argument("--limit", type=int, default=5)
    p = sub.add_parser("init-client"); p.add_argument("client"); p.add_argument("--scope", choices=SCOPES, required=True); p.add_argument("--goal", required=True)
    p = sub.add_parser("checkpoint"); p.add_argument("client"); p.add_argument("--source-thread", default=os.environ.get("CODEX_THREAD_ID"))
    p = sub.add_parser("resume-prompt"); p.add_argument("key")
    p = sub.add_parser("bind-handoff"); p.add_argument("key"); p.add_argument("target")
    p = sub.add_parser("context"); p.add_argument("--thread-id")
    p = sub.add_parser("dismiss-context"); p.add_argument("--thread-id")
    sub.add_parser("hook")
    p = sub.add_parser("pack"); p.add_argument("output", type=Path)
    p = sub.add_parser("restore"); p.add_argument("bundle", type=Path)
    sub.add_parser("doctor")
    args = parser.parse_args()
    try:
        cmd = args.command
        if cmd == "setup": result = setup(hooks=args.hooks)
        elif cmd == "import-source": result = import_source(args.source)
        elif cmd == "search": result = search(args.query, args.scope, args.client, args.limit)
        elif cmd == "init-client": result = init_client(args.client, args.scope, args.goal)
        elif cmd == "checkpoint": result = checkpoint(args.client, args.source_thread)
        elif cmd == "resume-prompt": result = {"prompt": resume_prompt(args.key)}
        elif cmd == "bind-handoff": result = bind_handoff(args.key, args.target)
        elif cmd == "context": result = context(args.thread_id)
        elif cmd == "dismiss-context": result = dismiss_context(args.thread_id)
        elif cmd == "hook": result = hook(json.load(sys.stdin))
        elif cmd == "pack": result = pack(args.output)
        elif cmd == "restore": result = restore(args.bundle)
        else: result = doctor()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == "doctor" and not result["ready"]:
            raise SystemExit(2)
    except (ValueError, OSError, KeyError, TypeError) as error:
        if args.command == "hook":
            print(json.dumps({"systemMessage": "AX: 사용량을 확인하지 못했습니다. 단계별 인계 기능을 사용하세요."}, ensure_ascii=False))
            return
        print(f"AX error: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
