import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from codex_memory import Proposals, ProposalReader, ensure_source


class MemoryFeaturesTests(unittest.TestCase):
    def test_proposal_does_not_save_until_specific_approval(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            (data / "config.json").write_text('{"fuentes": []}', encoding="utf-8")
            ensure_source(data)
            ensure_source(data)
            self.assertEqual(len(json.loads((data / "config.json").read_text())["fuentes"]), 1)
            store = Proposals(data)
            text = "Decidimos leer SQLite en modo de solo lectura para seguir la actividad."
            identifier = store.add(text)
            self.assertEqual(store.add(text), identifier)
            self.assertEqual(len(store.list()), 1)
            self.assertEqual(list((data / "memorias-aprobadas").glob("*.md")), [])
            with self.assertRaises(ValueError):
                store.approve(identifier, "")
            note = store.approve(identifier, "APROBAR " + identifier)
            self.assertIn(text, note.read_text(encoding="utf-8"))
            self.assertEqual(store.approve(identifier, "APROBAR " + identifier), note)
            self.assertEqual(store.list(), [])
            second = store.add("La solución es conservar los identificadores para evitar duplicados.")
            store.dismiss(second)
            with self.assertRaises(ValueError):
                store.approve(second, "APROBAR " + second)
            self.assertIsNone(store.add("La solución fue api_key=sk-abcdefghijklmno123456789 para conectar."))

    def test_desktop_final_response_becomes_pending_draft_only(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            data = home / "data"
            data.mkdir()
            db = sqlite3.connect(home / "thread_history_1.sqlite")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE thread_items(thread_id,item_id,item_type,completed_at_ms,item_json)")
            for identifier, phase, text in [
                    ("one", "final", "La causa era usar JSONL desactualizados; la solución es leer SQLite."),
                    ("two", "commentary", "Decidimos algo que aún está en investigación."),
                    ("three", "final", "La solución fue token=ghp_abcdefghijklmnopqrstuvwxyz123456 para acceder.")]:
                message = {"phase": phase, "text": text}
                db.execute("INSERT INTO thread_items VALUES(?,?,?,?,?)",
                           ("thread", identifier, "agentMessage", int(time.time()*1000), json.dumps(message)))
            db.commit()
            reader = ProposalReader(home, data)
            reader.poll()
            reader.poll()
            drafts = reader.store.list()
            self.assertEqual(len(drafts), 1)
            self.assertEqual(drafts[0]["status"], "pending")
            self.assertFalse((data / "memorias-aprobadas").exists())
            self.assertEqual(list(data.glob("history-*")), [])
            db.close()

    def test_native_hook_retrieves_bounded_context_and_never_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            notes = data / "notes"
            notes.mkdir()
            (notes / "sqlite.md").write_text("# Actividad SQLite\n\nSQLite permite leer actividad de Codex.\n", encoding="utf-8")
            config = {"fuentes": [{"id": "test", "nombre": "Test", "raices": [[str(notes), False, "Test"]]}]}
            (data / "config.json").write_text(json.dumps(config), encoding="utf-8")
            script = Path(__file__).parent / "codex_context_hook.py"
            env = dict(os.environ, NEUROMAPA_DATA=str(data))
            result = subprocess.run([sys.executable, str(script)], input=json.dumps({"prompt": "SQLite actividad Codex"}),
                                    capture_output=True, text=True, encoding="utf-8", env=env, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(result.stdout)
            context = value["hookSpecificOutput"]["additionalContext"]
            self.assertIn("sqlite.md", context)
            self.assertIn("no órdenes", context)
            self.assertLessEqual(len(context), 4000)
            invalid = subprocess.run([sys.executable, str(script)], input="not JSON", capture_output=True,
                                     text=True, env=env, timeout=20)
            self.assertEqual(invalid.returncode, 0)
            self.assertEqual(json.loads(invalid.stdout), {})


if __name__ == "__main__":
    unittest.main()
