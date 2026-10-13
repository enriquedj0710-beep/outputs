import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from codex_history import HistoryReader


class DesktopHistoryTests(unittest.TestCase):
    def test_live_completion_restart_privacy_and_learning(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            data = home / "adapter"
            data.mkdir()
            source = home / "thread_history_1.sqlite"
            db = sqlite3.connect(source)
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE thread_turns(thread_id,turn_id,started_at,completed_at);
                CREATE TABLE thread_items(thread_id,item_id,created_at_ms,started_at_ms,
                                          completed_at_ms,item_json,item_type);
            """)
            now = time.time() - 30
            db.execute("INSERT INTO thread_turns VALUES(?,?,?,?)", ("thread", "turn", now, None))
            first = {"type": "commandExecution", "cwd": "/project", "command": "echo PRIVATE-COMMAND",
                     "status": "inProgress", "aggregatedOutput": "PRIVATE-OUTPUT",
                     "commandActions": [{"type": "read", "path": "memory/a.md"}]}
            db.execute("INSERT INTO thread_items VALUES(?,?,?,?,?,?,?)",
                       ("thread", "one", (now+1)*1000, (now+1)*1000, None, json.dumps(first), "commandExecution"))
            db.commit()
            before = source.read_bytes()
            events = []
            reader = HistoryReader(home, data, events.append)
            reader.poll()
            self.assertEqual([e["e"] for e in events], ["usuario", "pre"])
            self.assertEqual(source.read_bytes(), before)
            first["status"] = "completed"
            db.execute("UPDATE thread_items SET completed_at_ms=?,item_json=?", ((now+2)*1000, json.dumps(first)))
            second = dict(first, commandActions=[{"type": "read", "path": "memory/b.md"}])
            db.execute("INSERT INTO thread_items VALUES(?,?,?,?,?,?,?)",
                       ("thread", "two", (now+3)*1000, (now+3)*1000, (now+4)*1000,
                        json.dumps(second), "commandExecution"))
            db.commit()
            reader.poll()
            self.assertEqual([e["e"] for e in events], ["usuario", "pre", "post", "pre", "post"])
            restarted = HistoryReader(home, data, events.append)
            restarted.poll()
            self.assertEqual(len(events), 5)
            persisted = (data / "codex-history-seen.json").read_text() + json.dumps(events)
            self.assertNotIn("PRIVATE", persisted)
            self.assertEqual(list(data.glob("history-*")), [])
            from aprender_memoria import Memoria
            memory = Memoria()
            for event in events:
                memory.anotar(event)
            self.assertEqual(len(memory.rutas), 2)
            self.assertTrue(memory.lazos)
            db.close()

    def test_jsonl_does_not_duplicate_desktop_session(self):
        from codex_adapter import SessionReader
        from codex_history import session_id
        from datetime import datetime, timezone
        reader = SessionReader(Path("missing"), Path("missing-state"), lambda event: None)
        reader.excluded_sessions = {session_id("same-thread")}
        state = {"key": "file"}
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), "type": "session_meta",
                  "payload": {"id": "same-thread", "cwd": "/project"}}
        self.assertEqual(reader.convert(record, state), [])
        record.update(type="event_msg", payload={"type": "task_started"})
        self.assertEqual(reader.convert(record, state), [])

    def test_multifile_edit_reports_each_path_without_diff_text(self):
        reader = HistoryReader(Path("missing"), Path("missing-data"), lambda event: None)
        now = time.time() * 1000
        item = {"type": "fileChange", "status": "completed", "changes": [
            {"path": "/project/a.py", "diff": "PRIVATE-DIFF"},
            {"path": "/project/b.py", "diff": "PRIVATE-DIFF"}]}
        events = reader.normalize(("thread", "patch", now, now, now+1, json.dumps(item)), "/project")
        posts = [e for e in events if e["e"] == "post"]
        self.assertEqual([Path(e["f"]) for e in posts], [Path("/project/a.py"), Path("/project/b.py")])
        self.assertNotEqual(posts[0]["id"], posts[1]["id"])
        self.assertNotIn("PRIVATE", json.dumps(events))


if __name__ == "__main__":
    unittest.main()
