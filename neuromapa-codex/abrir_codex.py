"""Desktop launcher: reuse the running map, or start it without a console."""
import os
import subprocess
import sys
import json
import urllib.request
import webbrowser
from pathlib import Path


def running_port():
    import servidor
    import firmas
    try:
        record = json.loads(servidor.EN_VIVO.joinpath("servidor.json").read_text(encoding="utf-8"))
        port = int(record["puerto"])
        if not 1 <= port <= 65535:
            return None
        challenge = firmas.numero()
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/hola?n={challenge}", timeout=3) as response:
            data = json.loads(response.read())
        if firmas.servidor_valido(servidor.clave(), challenge, data.get("firma")):
            return port
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def main():
    root = Path(__file__).resolve().parent
    os.environ["CEREBRO_CONFIG"] = str(root / "codex-data" / "config.json")
    import servidor
    port = running_port()
    if port:
        # A legacy map process may be running without the Codex observer.
        import archivos
        data = root / "codex-data"
        lock = archivos.tomar_candado(data / "codex-watch.lock")
        if lock is not None:
            archivos.soltar_candado(lock)
            with (data / "codex-watch.log").open("ab") as log:
                subprocess.Popen([sys.executable, str(root / "codex_adapter.py"), "watch"],
                    cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        webbrowser.open(servidor.direccion_para_abrir(port))
        return
    subprocess.Popen(
        [sys.executable, str(root / "codex_adapter.py"), "abrir"],
        cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


if __name__ == "__main__":
    main()
