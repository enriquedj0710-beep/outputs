"""Native UserPromptSubmit hook. Only JSON output, bounded context, never block."""
import json
import os
import sys
from pathlib import Path


def main():
    data = Path(os.environ.get("NEUROMAPA_DATA", Path(__file__).resolve().parent / "codex-data"))
    os.environ["CEREBRO_CONFIG"] = str(data / "config.json")
    try:
        payload = json.loads(sys.stdin.buffer.read(1024 * 1024))
        from codex_memory import prompt_context
        context = prompt_context(payload.get("prompt", ""))
        result = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}} if context else {}
    except Exception:
        result = {}
    sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
