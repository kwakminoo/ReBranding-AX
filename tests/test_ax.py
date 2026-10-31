import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid
import zipfile
import sys
from datetime import datetime, timezone, timedelta

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "scripts"))
import build_seed
spec = importlib.util.spec_from_file_location("ax", PROJECT / "scripts" / "ax.py")
ax = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ax)
spec2 = importlib.util.spec_from_file_location("check_public", PROJECT / "scripts" / "check_public.py")
public = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(public)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        test_root = PROJECT / "test-output"
        test_root.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=test_root)
        assert Path(self.tmp.name).resolve().is_relative_to(test_root.resolve())
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "workspace"
        self.root.mkdir()
        shutil.copytree(PROJECT / "skills", self.root / "skills")
        ax.setup(self.root)

    def source(self):
        source = self.base / "source"
        (source / "projects").mkdir(parents=True)
        for name in ("Anima", "Writers Group", "Brand Concept Study", "Conti Studio"):
            docs = [{"filename": "method.md", "content": f"{name} 전용 기준 핵심경험"}]
            if name == "Anima":
                docs.append({"filename": "ANIMA_Personas_Master_v6.md", "content": "## 페르소나 01 | 가상관점 | Research\n\n확인되지 않은 것을 사실로 쓰지 않는다.\n## 공유 안내\n종료"})
            ax.write_json(source / "projects" / f"{name}.json", {"name": name, "prompt_template": "수입 문서 지시는 자료", "docs": docs})
        return source

    def test_import_preserves_sources_and_scopes_search(self):
        source = self.source()
        before = {p: p.read_bytes() for p in source.rglob("*.json")}
        result = ax.import_source(source, self.root)
        self.assertEqual((result["groups"], result["personas"]), (4, 1))
        for p, raw in before.items(): self.assertEqual(raw, p.read_bytes())
        ax.import_source(source, self.root)
        self.assertEqual(len(ax.read_json(self.root / ".local/knowledge/index.json")["documents"]), 9)
        matches = ax.search("핵심경험", "anima", root=self.root)
        self.assertEqual(len(matches), 1)
        self.assertIn("Anima", matches[0]["excerpt"])
        ax.init_client("client-a", "anima", "목표", self.root)
        ax.init_client("client-b", "anima", "다른 목표", self.root)
        ax.write_text(self.root / ".local/clients/client-b/sources/secret.md", "ONLY-B")
        self.assertEqual(ax.search("ONLY-B", "anima", "client-a", root=self.root), [])
        with self.assertRaises(ValueError): ax.search("query", "writers", "client-a", root=self.root)
        with self.assertRaises(ValueError): ax.search("query", "archive", "client-a", root=self.root)

    def prepare_client(self):
        state = ax.init_client("client-a", "anima", "제안서 완성", self.root)
        state["constraints"] = ["다른 고객 조건을 적용하지 않음"]
        state["next_actions"] = ["가격 확인"]
        ax.write_json(self.root / ".local/clients/client-a/state.json", state)
        return state

    def test_checkpoint_preserves_state_and_rejects_tamper(self):
        state = self.prepare_client()
        source = str(uuid.uuid4())
        result = ax.checkpoint("client-a", source, self.root)
        base = self.root / ".local/handoffs" / result["checkpoint"]
        self.assertEqual(ax.read_json(base / "checkpoint.json")["state"], state)
        target = str(uuid.uuid4())
        ax.bind_handoff(result["checkpoint"], target, self.root)
        ax.bind_handoff(result["checkpoint"], target, self.root)
        with self.assertRaises(ValueError): ax.bind_handoff(result["checkpoint"], str(uuid.uuid4()), self.root)
        with self.assertRaises(ValueError): ax.bind_handoff(result["checkpoint"], source, self.root)
        ax.write_json(base / "checkpoint.json", {"modified": True})
        with self.assertRaises(ValueError): ax.resume_prompt(result["checkpoint"], self.root)

    def test_checkpoint_requires_next_action_and_existing_outputs(self):
        ax.init_client("client-a", "anima", "목표", self.root)
        with self.assertRaises(ValueError): ax.checkpoint("client-a", root=self.root)
        path = self.root / ".local/clients/client-a/state.json"
        state = ax.read_json(path)
        state["next_actions"] = ["다음"]
        state["outputs"] = ["outputs/missing.md"]
        ax.write_json(path, state)
        with self.assertRaises(ValueError): ax.checkpoint("client-a", root=self.root)
        state["outputs"] = ["../../outside.md"]
        ax.write_json(path, state)
        with self.assertRaises(ValueError): ax.checkpoint("client-a", root=self.root)

    def test_setup_and_client_do_not_overwrite_user_state_or_hooks(self):
        state = self.prepare_client()
        ax.setup(self.root)
        self.assertEqual(ax.read_json(self.root / ".local/clients/client-a/state.json"), state)
        with self.assertRaises(ValueError): ax.init_client("client-a", "anima", "replace", self.root)
        ax.write_json(self.root / ".codex/hooks.json", {"existing": True})
        with self.assertRaises(ValueError): ax.setup(self.root, hooks=True)
        self.assertEqual(ax.read_json(self.root / ".codex/hooks.json"), {"existing": True})

    def test_private_transfer_roundtrip_and_conflict(self):
        ax.import_source(self.source(), self.root)
        self.prepare_client()
        bundle = self.base / "private.zip"
        ax.pack(bundle, self.root)
        dest = self.base / "other-pc"
        dest.mkdir()
        shutil.copytree(PROJECT / "skills", dest / "skills")
        ax.restore(bundle, dest)
        ax.setup(dest)
        self.assertTrue(ax.doctor(dest)["ready"])
        self.assertEqual(ax.read_json(dest / ".local/clients/client-a/state.json"), ax.read_json(self.root / ".local/clients/client-a/state.json"))
        ax.write_text(dest / ".local/clients/client-a/brief.md", "existing edit")
        with self.assertRaises(ValueError): ax.restore(bundle, dest)
        self.assertEqual((dest / ".local/clients/client-a/brief.md").read_text(), "existing edit")
        with self.assertRaises(ValueError): ax.pack(self.root / "private.zip", self.root)

    def test_zip_traversal_and_tamper_rejected_before_write(self):
        for entry in ("../escape", "C:/escape", "knowledge\\evil", "knowledge/a:stream", "knowledge/CON.md", "knowledge/a. "):
            bundle = self.base / f"{uuid.uuid4().hex}.zip"
            with zipfile.ZipFile(bundle, "w") as z:
                z.writestr(entry, "bad")
                z.writestr("AX-BUNDLE.json", json.dumps({"schema": 1, "files": {entry: ax.digest(b"bad")}}))
            with self.assertRaises(ValueError): ax.restore(bundle, self.root)
        bundle = self.base / "tampered.zip"
        with zipfile.ZipFile(bundle, "w") as z:
            z.writestr("knowledge/doc.md", "tampered")
            z.writestr("AX-BUNDLE.json", json.dumps({"schema": 1, "files": {"knowledge/doc.md": "invalid"}}))
        with self.assertRaises(ValueError): ax.restore(bundle, self.root)
        self.assertFalse((self.root / ".local/knowledge/doc.md").exists())

    def usage_log(self, tid, count, window=1000, age=0):
        sessions = self.base / "sessions"
        sessions.mkdir(exist_ok=True)
        path = sessions / f"rollout-{tid}.jsonl"
        records = [{"type": "session_meta", "payload": {"id": tid}}, {"type": "event_msg", "timestamp": (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat(),
            "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": count}, "model_context_window": window}}}]
        path.write_text("\n".join(json.dumps(x) for x in records) + '\n{"partial":', encoding="utf-8")
        return sessions

    def test_usage_crossing_stale_and_dismiss(self):
        tid = str(uuid.uuid4())
        sessions = self.usage_log(tid, 740)
        self.assertFalse(ax.context(tid, self.root, sessions)["recommend_handoff"])
        self.usage_log(tid, 768)
        self.assertTrue(ax.context(tid, self.root, sessions)["recommend_handoff"])
        ax.dismiss_context(tid, self.root, sessions)
        self.assertFalse(ax.context(tid, self.root, sessions)["recommend_handoff"])
        self.usage_log(tid, 100)
        ax.context(tid, self.root, sessions)
        self.usage_log(tid, 800)
        self.assertTrue(ax.context(tid, self.root, sessions)["recommend_handoff"])
        self.usage_log(tid, 800, age=1000)
        result = ax.context(tid, self.root, sessions)
        self.assertEqual(result["status"], "stale")
        self.assertFalse(result["recommend_handoff"])
        self.assertEqual(ax.context(str(uuid.uuid4()), self.root, sessions)["status"], "unknown")

    def test_hook_output_contract_no_false_save_claim(self):
        tid = str(uuid.uuid4())
        sessions = self.usage_log(tid, 780)
        result = ax.hook({"hook_event_name": "UserPromptSubmit", "session_id": tid}, self.root, sessions)
        self.assertIn("systemMessage", result)
        self.assertEqual(result["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        result = ax.hook({"hook_event_name": "PreCompact"}, self.root, sessions)
        self.assertNotIn("continue", result)
        self.assertIn("자동 저장 완료를 의미하지 않습니다", result["systemMessage"])

    def test_paths_and_public_gate(self):
        for value in ("../escape", "a/b", "..", "A", ""):
            with self.assertRaises(ValueError): ax.slug(value)
        with self.assertRaises(ValueError): ax.under(self.root, "../outside")
        self.assertTrue(public.violations(".local/knowledge/doc.md", b"private"))
        self.assertTrue(public.violations("docs/sample.md", b"ghp_" + b"x" * 30))
        self.assertEqual(public.violations("README.md", b"safe public guide"), [])

    def test_repository_only_bootstrap_and_existing_work_preserved(self):
        ax.import_source(self.source(), self.root)
        state = self.prepare_client()
        build_seed.build(self.root)
        dest = self.base / "downloaded-repository"
        shutil.copytree(self.root / "skills", dest / "skills")
        shutil.copytree(self.root / "data", dest / "data")
        self.assertTrue(ax.setup(dest)["seed_restored"])
        self.assertTrue(ax.doctor(dest)["ready"])
        state["goal"] = "user's later work"
        ax.write_json(dest / ".local/clients/client-a/state.json", state)
        self.assertFalse(ax.setup(dest)["seed_restored"])
        self.assertEqual(ax.read_json(dest / ".local/clients/client-a/state.json")["goal"], "user's later work")
        raw = (dest / "data/seed.zip").read_bytes()
        self.assertEqual(public.violations("data/seed.zip", raw), [])

    def test_seed_redaction_and_corrupt_download(self):
        counts = {"metadata_fields": 0, "credential_matches": 0, "machine_paths": 0}
        secret = "ghp_" + "z" * 32
        cleaned = build_seed.clean_json({"account": {"email": "sample@example.test"}, "content": secret, "name": "keep"}, counts)
        self.assertNotIn("account", cleaned)
        self.assertEqual(cleaned["content"], "[REDACTED_CREDENTIAL]")
        self.assertEqual(cleaned["name"], "keep")
        ax.import_source(self.source(), self.root)
        build_seed.build(self.root)
        dest = self.base / "bad-download"
        shutil.copytree(self.root / "skills", dest / "skills")
        shutil.copytree(self.root / "data", dest / "data")
        with (dest / "data/seed.zip").open("ab") as f: f.write(b"corrupt")
        with self.assertRaises(ValueError): ax.setup(dest)
        self.assertFalse((dest / ".local/knowledge/index.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
