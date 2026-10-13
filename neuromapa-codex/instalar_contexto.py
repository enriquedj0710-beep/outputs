"""Register the native hook definition; trust is reviewed separately in Codex."""
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path


def definition():
    script = str(Path(__file__).resolve().parent / "codex_context_hook.py")
    command = subprocess.list2cmdline([sys.executable, script]) if os.name == "nt" else shlex.join([sys.executable, script])
    return {"hooks": [{"type": "command", "command": command, "timeout": 10,
                       "additionalContextLimit": 1200, "statusMessage": "Buscando memorias relevantes"}]}


def main():
    from codex_adapter import codex_home
    path = codex_home() / "hooks.json"
    value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"description": "Hooks locales de Codex"}
    groups = value.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
    group = definition()
    command = group["hooks"][0]["command"]
    if not any(handler.get("command") == command for entry in groups for handler in entry.get("hooks", [])):
        groups.append(group)
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Hook registrado en " + str(path))
    print("Para activarlo, abrí /hooks en Codex CLI y revisá/confiá en esta definición. Reiniciá Codex.")


if __name__ == "__main__":
    main()
