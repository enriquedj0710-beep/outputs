"""Read the desktop's projected history without writing to Codex databases."""
import hashlib
import json
import shutil
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


def fingerprint(path):
    return tuple((p.stat().st_size, p.stat().st_mtime_ns) if p.exists() else None
                 for p in (path, Path(str(path) + "-wal")))


@contextmanager
def snapshot(path, scratch):
    # WAL copies are accepted only if neither source changes while copying.
    # Opening these private copies also avoids SQLite writing the source SHM.
    with tempfile.TemporaryDirectory(prefix="history-", dir=scratch) as directory:
        target = Path(directory) / path.name
        for attempt in range(3):
            before = fingerprint(path)
            shutil.copyfile(path, target)
            wal = Path(str(path) + "-wal")
            copied = Path(str(target) + "-wal")
            if wal.exists():
                shutil.copyfile(wal, copied)
            elif copied.exists():
                copied.unlink()
            if before == fingerprint(path):
                break
        else:
            raise OSError("Codex está actualizando su historial; reintento en el próximo ciclo")
        connection = sqlite3.connect(target.as_uri() + "?mode=ro", uri=True)
        try:
            yield connection
        finally:
            connection.close()


def session_id(identifier):
    return hashlib.sha256(str(identifier).encode()).hexdigest()[:8]


class HistoryReader:
    def __init__(self, home, data, emit, history_seconds=3600):
        self.home, self.data, self.emit = Path(home), Path(data), emit
        self.since = time.time() - history_seconds
        self.state_file = self.data / "codex-history-seen.json"
        try:
            self.seen = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.seen = {}
        self.sessions = set()
        self.source_signature = None
        self.last_events = 0
        self.error = ""

    def normalize(self, row, cwd):
        thread, item_id, created, started, completed, raw = row
        item = json.loads(raw)
        kind = item.get("type")
        if kind not in ("commandExecution", "fileChange", "mcpToolCall", "collabAgentToolCall"):
            return []
        event = {"s": session_id(thread), "c": cwd, "provider": "codex",
                 "source": "desktop-history", "h": kind,
                 "id": hashlib.sha256(str(item_id).encode()).hexdigest()[:10]}
        event["k"] = {"commandExecution": "ejecutar", "fileChange": "editar",
                      "mcpToolCall": "otro", "collabAgentToolCall": "agente"}[kind]
        if kind == "commandExecution":
            import hook_evento
            event["c"] = str(item.get("cwd") or cwd)
            hook_evento.sumar_comando(event, {"command": item.get("command", "")}, event["c"])
            paths = []
            for action in item.get("commandActions") or []:
                if action.get("type") == "read" and isinstance(action.get("path"), str):
                    paths.append(str(Path(event["c"]) / action["path"]))
            if paths:
                event.update(k="leer", fs=paths[:5])
        elif kind == "fileChange":
            paths = [change.get("path") for change in item.get("changes", [])]
            paths = [str(Path(cwd) / p) for p in paths if isinstance(p, str)]
            if paths:
                event["f"] = paths[0]
                event["fs"] = paths[:5]
        elif kind == "mcpToolCall":
            event["h"] = (str(item.get("server", "")) + ":" + str(item.get("tool", "")))[:120]
            if "neuromapa" in str(item.get("server", "")):
                tool = str(item.get("tool", ""))
                if tool in ("sobre", "buscar"):
                    event.update(k="consulta", p=tool)
                elif tool == "leer_nota":
                    args = item.get("arguments") or {}
                    if isinstance(args, dict) and isinstance(args.get("ruta"), str):
                        event.update(k="leer", f=args["ruta"])
        import hook_evento
        for field in ("f", "c"):
            if field in event:
                safe = hook_evento.ruta_guardable(event[field])
                if safe:
                    event[field] = safe
                else:
                    event.pop(field)
        if "fs" in event:
            event["fs"] = [safe for path in event["fs"] if (safe := hook_evento.ruta_guardable(path))]
        variants = [event]
        if kind == "fileChange" and len(event.get("fs", [])) > 1:
            for index, path in enumerate(event["fs"][1:], 1):
                variants.append(dict(event, f=path, part=index,
                                     id=hashlib.sha256(f"{item_id}:{index}".encode()).hexdigest()[:10]))
        events = []
        for variant in variants:
            events.append(dict(variant, t=(started or created) / 1000, e="pre"))
            if completed:
                events.append(dict(variant, t=completed / 1000,
                                   e="falla" if item.get("status") in ("failed", "declined") else "post"))
        return events

    def poll(self):
        database = self.home / "thread_history_1.sqlite"
        if not database.exists():
            return
        signature = fingerprint(database)
        if signature == self.source_signature:
            return
        cutoff = max(self.since, time.time() - 3600)
        cwds = {}
        state = self.home / "state_5.sqlite"
        if state.exists():
            with snapshot(state, self.data) as connection:
                cwds = dict(connection.execute("SELECT id,cwd FROM threads"))
        pending = []
        with snapshot(database, self.data) as connection:
            self.sessions = {session_id(row[0]) for row in connection.execute("SELECT DISTINCT thread_id FROM thread_turns")}
            for thread, turn, started, completed in connection.execute(
                    "SELECT thread_id,turn_id,started_at,completed_at FROM thread_turns WHERE started_at>=?", (cutoff,)):
                base = {"s": session_id(thread), "c": cwds.get(thread, ""), "provider": "codex",
                        "source": "desktop-history", "h": ""}
                for phase, t in (("usuario", started), ("fin", completed)):
                    if t:
                        pending.append((f"{thread}:{turn}:{phase}", dict(base, e=phase, k=phase, t=t)))
            for row in connection.execute(
                    "SELECT thread_id,item_id,created_at_ms,started_at_ms,completed_at_ms,item_json "
                    "FROM thread_items WHERE created_at_ms>=? AND item_type IN "
                    "('commandExecution','fileChange','mcpToolCall','collabAgentToolCall') "
                    "ORDER BY created_at_ms LIMIT 5000", (int(cutoff * 1000),)):
                try:
                    for event in self.normalize(row, cwds.get(row[0], "")):
                        suffix = f":file{event['part']}" if "part" in event else ""
                        pending.append((f"{row[0]}:{row[1]}:{event['e']}{suffix}", event))
                except (ValueError, TypeError, AttributeError):
                    continue
        emitted = 0
        for key, event in sorted(pending, key=lambda pair: pair[1]["t"]):
            if key not in self.seen:
                self.emit(event)
                self.seen[key] = event["t"]
                emitted += 1
        from archivos import escribir_atomico
        self.seen = {key: value for key, value in self.seen.items() if value >= time.time() - 86400}
        escribir_atomico(self.state_file, json.dumps(self.seen))
        self.source_signature = signature
        self.last_events = emitted
        self.error = ""


class ActivityReader:
    def __init__(self, home, data, emit):
        from codex_adapter import SessionReader
        self.history = HistoryReader(home, data, emit)
        self.jsonl = SessionReader(home, Path(data) / "codex-offsets.json", emit)
        self.status_file = Path(data) / "codex-status.json"
        from codex_memory import ProposalReader
        self.proposals = ProposalReader(home, data)

    def poll(self):
        try:
            self.history.poll()
        except (OSError, sqlite3.Error) as error:
            self.history.error = str(error)
        self.jsonl.excluded_sessions = self.history.sessions
        self.jsonl.poll()
        proposal_error = ""
        try:
            self.proposals.poll()
        except (OSError, sqlite3.Error, ValueError) as error:
            proposal_error = str(error)
        from archivos import escribir_atomico
        escribir_atomico(self.status_file, json.dumps({"checked_at": time.time(),
            "desktop_sessions": len(self.history.sessions), "desktop_events": len(self.history.seen),
            "jsonl_files": len(self.jsonl.state), "error": self.history.error,
            "pending_memories": len(self.proposals.store.list()), "proposal_error": proposal_error}))

    def watch(self, stop):
        while not stop.is_set():
            try:
                self.poll()
            except (OSError, sqlite3.Error) as error:
                import sys
                print(f"Observador Codex: {type(error).__name__}: {error}", file=sys.stderr)
            stop.wait(2)
