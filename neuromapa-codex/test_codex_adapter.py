import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from codex_adapter import SessionReader, make_config


class CodexAdapterTests(unittest.TestCase):
    def test_complete_records_restart_and_private_text(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            sessions = home / "sessions"
            sessions.mkdir()
            file = sessions / "session.jsonl"
            now = datetime.now(timezone.utc).isoformat()
            rows = [
                {"type": "session_meta", "payload": {"id": "thread-123", "cwd": str(home)}},
                {"type": "event_msg", "payload": {"type": "task_started", "prompt": "PRIVATE-PROMPT"}},
                {"type": "response_item", "payload": {"type": "function_call", "name": "read_file",
                 "call_id": "call-123", "arguments": json.dumps({"path": "memory.md"})}},
                {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-123",
                 "output": "PRIVATE-OUTPUT"}},
            ]
            encoded = [json.dumps(dict(row, timestamp=now)).encode() + b"\n" for row in rows]
            file.write_bytes(b"".join(encoded[:-1]) + encoded[-1][:-1])
            events = []
            state_file = home / "offsets.json"
            reader = SessionReader(home, state_file, events.append)
            reader.poll()
            self.assertEqual([e["e"] for e in events], ["inicio", "usuario", "pre"])
            with file.open("ab") as stream:
                stream.write(b"\n")
            reader.poll()
            self.assertEqual(events[-1]["e"], "post")
            self.assertEqual(events[2]["id"], events[3]["id"])
            self.assertEqual(events[2]["f"], str(home / "memory.md"))
            restarted = SessionReader(home, state_file, events.append)
            restarted.poll()
            self.assertEqual(len(events), 4)
            persisted = state_file.read_text() + json.dumps(events)
            self.assertNotIn("PRIVATE", persisted)
            # Truncation is a new file stream, not a stale offset.
            file.write_bytes(encoded[0])
            restarted.poll()
            self.assertEqual(events[-1]["e"], "inicio")
            self.assertEqual(len(events), 5)

    def test_old_metadata_and_unknown_records(self):
        reader = SessionReader(Path("missing"), Path("missing-offsets"), lambda ev: None)
        state = {"key": "session"}
        self.assertEqual(reader.convert({"type": "session_meta", "timestamp": "2000-01-01T00:00:00Z",
                                       "payload": {"id": "old", "cwd": "/project"}}, state), [])
        self.assertEqual(state["cwd"], "/project")
        self.assertEqual(reader.convert({"payload": []}, state), [])
        self.assertEqual(reader.convert({"timestamp": "invalid", "payload": {}}, state), [])

    def test_sources_are_markdown_not_credentials(self):
        config = make_config(Path("/codex"), ["/project"])
        self.assertEqual(config["fuentes"][0]["raices"][0][0], str(Path("/codex/memories")))
        self.assertEqual(config["fuentes"][1]["patron"], "AGENTS.md")
        self.assertEqual(config["fuentes"][2]["patron"], "AGENTS.md")
        self.assertNotIn("auth.json", json.dumps(config))


if __name__ == "__main__":
    unittest.main()
