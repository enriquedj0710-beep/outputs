"""Read-only Codex session adapter. No Claude hooks or credentials required."""
import hashlib
import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path


def codex_home():
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).resolve()


def make_config(home, projects=()):
    sources = [
        {"id": "codex-memory", "nombre": "Memoria de Codex", "color": "#E64980",
         "raices": [[str(home / "memories"), True, "Codex"]]},
        {"id": "codex-instructions", "nombre": "Instrucciones de Codex", "color": "#F59F00",
         "patron": "AGENTS.md", "raices": [[str(home), False, "usuario"]]},
    ]
    if projects:
        sources.append({"id": "project-instructions", "nombre": "AGENTS.md de proyectos",
                        "color": "#12B886", "patron": "AGENTS.md",
                        "raices": [[str(Path(p).resolve()), True, Path(p).name] for p in projects]})
    return {"fuentes": sources, "proyectos": [{"raiz": str(Path(p).resolve())} for p in projects]}


def timestamp(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError, OverflowError):
        return None


class SessionReader:
    """Tail complete records only; persist offsets and metadata without transcript text."""
    def __init__(self, home, state_file, emit, history_seconds=600):
        self.home, self.state_file, self.emit = Path(home), Path(state_file), emit
        self.since = time.time() - history_seconds
        try:
            self.state = json.loads(self.state_file.read_text(encoding="utf-8"))
            if not isinstance(self.state, dict):
                self.state = {}
        except (OSError, ValueError):
            self.state = {}

    def convert(self, record, state):
        payload = record.get("payload")
        if not isinstance(payload, dict):
            return []
        kind, subtype = record.get("type"), payload.get("type")
        if kind == "session_meta":
            identifier = str(payload.get("id") or payload.get("session_id") or state["key"])
            state["session"] = hashlib.sha256(identifier.encode()).hexdigest()[:8]
            state["cwd"] = str(payload.get("cwd") or "")
        elif kind == "turn_context":
            state["cwd"] = str(payload.get("cwd") or state.get("cwd", ""))
        if state.get("session") in getattr(self, "excluded_sessions", set()):
            return []
        t = timestamp(record.get("timestamp"))
        if t is None or t < self.since:
            return []
        event = {"t": round(t, 3), "s": state.get("session", ""),
                 "c": state.get("cwd", ""), "h": "", "provider": "codex"}
        if kind == "session_meta":
            return [dict(event, e="inicio", k="inicio")]
        if kind == "event_msg":
            phases = {"task_started": "usuario", "task_complete": "fin",
                      "turn_aborted": "fin", "context_compacted": "compacta"}
            phase = phases.get(subtype)
            return [dict(event, e=phase, k=phase)] if phase else []
        if kind != "response_item":
            return []
        if subtype in ("function_call", "custom_tool_call"):
            name = str(payload.get("name") or "")
            # Names and paths only: never copy prompts, outputs, commands or patch bodies.
            tool_kind = ("agente" if name.endswith(("spawn_agent", "followup_task")) else
                         "editar" if name.endswith("apply_patch") else
                         "leer" if name.endswith("read_file") else
                         "buscar" if "search" in name else
                         "ejecutar" if name in ("exec", "exec_command", "shell", "shell_command") else "otro")
            call_id = str(payload.get("call_id") or "")
            event.update(e="pre", h=name[:120], k=tool_kind,
                         id=hashlib.sha256(call_id.encode()).hexdigest()[:10])
            raw = payload.get("arguments", payload.get("input", ""))
            try:
                args = raw if isinstance(raw, dict) else json.loads(raw)
            except (ValueError, TypeError):
                args = {}
            if isinstance(args, dict):
                path = args.get("file_path") or args.get("path")
                if isinstance(path, str) and path and "://" not in path:
                    event["f"] = str(Path(state.get("cwd", "")) / path)[:300]
                if tool_kind == "ejecutar" and name != "exec":
                    import hook_evento
                    hook_evento.sumar_comando(event, {"command": args.get("cmd") or args.get("command", "")},
                                              state.get("cwd", ""))
            # Bound metadata when an interrupted session never returns tool outputs.
            state.setdefault("calls", {})[call_id] = {k: v for k, v in event.items()
                                                     if k in ("h", "k", "f", "fs", "b", "p")}
            while len(state["calls"]) > 256:
                state["calls"].pop(next(iter(state["calls"])))
            return [event]
        if subtype in ("function_call_output", "custom_tool_call_output"):
            call_id = str(payload.get("call_id") or "")
            call = state.get("calls", {}).pop(call_id, None)
            if call:
                return [dict(event, e="post", id=hashlib.sha256(call_id.encode()).hexdigest()[:10], **call)]
        return []

    def poll(self):
        changed = False
        for file in (self.home / "sessions").rglob("*.jsonl"):
            try:
                stat = file.stat()
                if stat.st_mtime < self.since:
                    continue
                key = str(file.resolve())
                state = self.state.setdefault(key, {"offset": 0, "key": key})
                if stat.st_size < state.get("offset", 0):
                    state.clear()
                    state.update(offset=0, key=key)
                if stat.st_size == state.get("offset", 0):
                    continue
                with file.open("rb") as stream:
                    stream.seek(state.get("offset", 0))
                    # Bound one poll; catch up over subsequent polls on large sessions.
                    for _ in range(5000):
                        line = stream.readline(2 * 1024 * 1024)
                        if not line or not line.endswith(b"\n"):
                            break
                        state["offset"] = stream.tell()
                        changed = True
                        try:
                            record = json.loads(line)
                        except (ValueError, UnicodeDecodeError):
                            continue
                        if isinstance(record, dict):
                            for event in self.convert(record, state):
                                self.emit(event)
            except OSError as error:
                print(f"No pude leer una sesión de Codex: {type(error).__name__}", file=sys.stderr)
        if changed:
            from archivos import escribir_atomico
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            escribir_atomico(self.state_file, json.dumps(self.state, ensure_ascii=False))

    def watch(self, stop):
        while not stop.is_set():
            try:
                self.poll()
            except Exception as error:
                print(f"Observador Codex: {type(error).__name__}", file=sys.stderr)
            stop.wait(2)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Neuromapa para Codex: mapa, memoria y actividad local")
    parser.add_argument("--codex-home", type=Path, default=codex_home())
    parser.add_argument("--data", type=Path, default=Path(__file__).resolve().parent / "codex-data")
    parser.add_argument("--project", action="append", default=[])
    parser.add_argument("command", choices=["init", "abrir", "mcp", "watch", "consulta"])
    args, extra = parser.parse_known_args(argv)
    if args.command in ("init", "mcp", "watch") and extra:
        parser.error("Argumentos desconocidos: " + " ".join(extra))
    data = args.data.resolve()
    data.mkdir(parents=True, exist_ok=True)
    config = data / "config.json"
    if not config.exists():
        from archivos import escribir_atomico
        escribir_atomico(config, json.dumps(make_config(args.codex_home.resolve(), args.project), indent=2))
    elif args.project:
        parser.error("La configuración ya existe; agregá los proyectos en " + str(config))
    os.environ["CEREBRO_CONFIG"] = str(config)
    if args.command == "init":
        print(config)
        return 0
    if args.command == "consulta":
        import neuromapa
        return neuromapa.correr(extra)
    if args.command == "mcp":
        import conector_mcp
        conector_mcp.HERRAMIENTAS[:] = [t for t in conector_mcp.HERRAMIENTAS if t["name"] != "avisar_charla"]
        conector_mcp.main()
        return 0
    import hook_evento
    import archivos
    stop = threading.Event()
    # One observer per data directory. MCP queries use the upstream connector, without a second observer.
    lock = archivos.tomar_candado(data / "codex-watch.lock")
    if lock is None:
        print("Ya hay un observador activo para estos datos (o no se pudo tomar el candado).", file=sys.stderr)
        return 1
    try:
        from codex_history import ActivityReader
        reader = ActivityReader(args.codex_home, data, hook_evento.escribir_evento)
        if args.command == "watch":
            try:
                reader.watch(stop)
            except KeyboardInterrupt:
                pass
            return 0
        thread = threading.Thread(target=reader.watch, args=(stop,), daemon=True)
        thread.start()
        try:
            sys.argv = ["servidor.py"] + extra
            import servidor
            return servidor.main()
        finally:
            stop.set()
            thread.join(5)
    finally:
        archivos.soltar_candado(lock)


if __name__ == "__main__":
    sys.exit(main())
