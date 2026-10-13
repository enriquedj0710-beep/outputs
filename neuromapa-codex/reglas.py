import datetime
import os
import re
import time
from collections import Counter
from pathlib import Path

import cerebro as nucleo
from archivos import dentro, es_sensible, escribir_atomico
from textos import cantidad, detalle

CARPETA = (".claude", "rules")
MARCA = "neuromapa"
DIAS_CARGAS = 30
MARCA_CARGA = b'"e":"regla"'
ENTERA = 2500
USADOS = 3
DICHAS = 2
SOLAS = 3
BASES = 5
PESO_CARPETA = 2
PARTE = 0.6
ANCHO = 0.2
CONOCIDOS = 20
DOCUMENTOS = {"md", "pdf", "html", "htm", "png", "jpg", "jpeg", "gif", "webp", "svg", "docx", "odt"}
PODADAS = {".claude", ".git", "node_modules", "__pycache__"}
RE_CODIGO = re.compile(r"`([^`\n]{3,200})`")
RE_RENGLON = re.compile(r":\d+(?:-\d+)?$")
RE_GLOB = re.compile(r"([\[\]{}*?])")
RE_WIKI = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
RE_PROPIA = re.compile(r"^" + MARCA + r":[ \t]*(.*?)[ \t]*$", re.M)
ESTADOS = {"nueva": "no existe todavía", "igual": "ya está escrita y al día",
           "propia": "ya está escrita, pero la memoria o la carpeta cambiaron: se puede volver a escribir",
           "ajena": "ya hay otra regla con ese nombre que no escribió Neuromapa: no se toca"}


def proyectos():
    import buscador
    import consultas
    lista = buscador.proyectos_conocidos()
    reales = {clave: Path(p["raiz"]) for clave, p in lista if p.get("raiz")}
    for carpeta in nucleo.carpetas_propias():
        reales.setdefault(consultas.clave(carpeta).rstrip("/"), Path(carpeta))
    return lista, reales


def clase_de(ruta, visto):
    k = os.path.normcase(str(ruta))
    if k not in visto:
        try:
            visto[k] = "carpeta" if ruta.is_dir() else "archivo" if ruta.is_file() else ""
        except (OSError, ValueError):
            visto[k] = ""
    return visto[k]


def relativa(completa, raiz):
    try:
        return Path(os.path.realpath(completa)).relative_to(os.path.realpath(raiz))
    except (ValueError, OSError):
        return None


def mejor(votos, total, minimo):
    buenas = [(k, v) for k, v in votos.items() if v >= minimo and v >= PARTE * total]
    return max(buenas, key=lambda x: (x[0][1].count("/"), x[1], x[0]))[0] if buenas else None


def carpeta_dicha(nodo, raiz, lista, reales, visto):
    import buscador
    import consultas
    votos = Counter()
    nombres = {}
    bases = Counter()
    sueltos = []
    base = reales.get(raiz)

    def sumar(donde, completa):
        que = clase_de(completa, visto)
        if not que or (que == "archivo" and completa.suffix.lower().lstrip(".") in DOCUMENTOS) or es_sensible(str(completa)):
            return False
        carpeta = completa if que == "carpeta" else completa.parent
        rel = relativa(carpeta, reales[donde])
        if rel is None or not rel.parts or PODADAS & {p.lower() for p in rel.parts}:
            return False
        peso = PESO_CARPETA if que == "carpeta" else 1
        bases[(donde, carpeta)] += peso
        for hondo in range(1, len(rel.parts) + 1):
            k = (donde, "/".join(rel.parts[:hondo]).lower())
            votos[k] += peso
            nombres[k] = "/".join(rel.parts[:hondo])
        return True

    for m in RE_CODIGO.finditer(nodo["_cuerpo"]):
        token = RE_RENGLON.sub("", m.group(1).strip().strip(".,;:()«»\"'")).replace("\\", "/")
        if any(x in token for x in "*?<>|") or "://" in token or " -" in token:
            continue
        ruta = Path(token)
        hallado = False
        if "/" in token:
            if ruta.is_absolute():
                donde, completa = buscador.raiz_que_contiene(consultas.clave(token).rstrip("/"), lista), ruta
            else:
                donde, completa = raiz, base / token if base is not None else None
            hallado = bool(donde) and donde in reales and completa is not None and sumar(donde, completa)
        if not hallado and not ruta.is_absolute() and "." in token.strip("."):
            sueltos.append(token)
    for (donde, carpeta), _ in bases.most_common(BASES):
        for token in sueltos:
            sumar(donde, carpeta / token)
    elegida = mejor(votos, sum(bases.values()), DICHAS)
    return {"raiz": elegida[0], "carpeta": elegida[1], "nombre": nombres[elegida], "dichas": votos[elegida]} if elegida else None


def usos_de(nodo, aprendido, lista, reales):
    import buscador
    import consultas
    from aprender_comun import es_nota
    votos = Counter()
    nombres = {}
    total = 0
    if aprendido is None:
        return votos, nombres, total
    for _, b in aprendido.vecinos(consultas.clave(nodo["ruta"]), filtro=lambda x: not es_nota(x), respaldo=False):
        raiz = buscador.raiz_que_contiene(b, lista)
        if not raiz or raiz not in reales or b == raiz:
            continue
        partes = b[len(raiz) + 1:].split("/")
        crudas = aprendido.rutas.get(b, b).replace("\\", "/").split("/")[-len(partes):]
        total += 1
        for hondo in range(1, len(partes)):
            k = (raiz, "/".join(partes[:hondo]))
            votos[k] += 1
            nombres[k] = "/".join(crudas[:hondo])
    return votos, nombres, total


def carpeta_usada(usos, reales):
    votos, nombres, total = usos
    elegida = mejor(votos, total, USADOS)
    if not elegida:
        return None
    rel = relativa(reales[elegida[0]] / nombres[elegida], reales[elegida[0]])
    if rel is None or not rel.parts or not (reales[elegida[0]] / rel).is_dir():
        return None
    return {"raiz": elegida[0], "carpeta": elegida[1], "nombre": rel.as_posix(), "usados": votos[elegida], "de": total}


def tocados_de(aprendido, lista, reales):
    import buscador
    from aprender_comun import es_nota, util
    salida = {}
    for c in (set(aprendido.veces) | set(aprendido.lazos)) if aprendido is not None else ():
        raiz = buscador.raiz_que_contiene(c, lista)
        if raiz and raiz in reales and c != raiz and not es_nota(c) and util(c):
            salida.setdefault(raiz, []).append(c[len(raiz) + 1:])
    return salida


def ancho_de(tocados, raiz, carpeta):
    todos = tocados.get(raiz, ())
    if len(todos) < CONOCIDOS:
        return None
    return sum(1 for c in todos if c.startswith(carpeta + "/")) / len(todos)


def candidatas(cerebro, aprendido=None):
    import buscador
    lista, reales = proyectos()
    de_nota = buscador.proyecto_de_cada_nota(cerebro)
    tocados = tocados_de(aprendido, lista, reales)
    visto = {}
    salida = []
    anchas = 0
    for nodo in cerebro.nodos:
        if not cerebro.fuente_de.get(nodo["id"], {}).get("memoria") or nodo["tipo"] == "indice" or nucleo.es_archivo(nodo):
            continue
        elegidas = {}
        usos = usos_de(nodo, aprendido, lista, reales)
        usada = carpeta_usada(usos, reales)
        dicha = carpeta_dicha(nodo, de_nota.get(nodo["id"], ""), lista, reales, visto)
        if dicha:
            juntos = usos[0].get((dicha["raiz"], dicha["carpeta"]), 0)
            if juntos >= USADOS:
                dicha.update(usados=juntos, de=usos[2])
            elif dicha["dichas"] < SOLAS or not entera(nodo):
                dicha = None
        for hallada in (usada, dicha):
            if hallada:
                k = (hallada["raiz"], hallada["carpeta"])
                elegidas.setdefault(k, {"nombre": hallada["nombre"], "usados": 0, "de": 0, "dichas": 0}).update(
                    {c: hallada[c] for c in ("usados", "de", "dichas") if c in hallada})
        halladas = len(elegidas)
        for (raiz, carpeta), datos in list(elegidas.items()):
            datos["ancho"] = ancho_de(tocados, raiz, carpeta)
            if datos["ancho"] is not None and datos["ancho"] > ANCHO:
                del elegidas[(raiz, carpeta)]
        anchas += 1 if halladas and not elegidas else 0
        for (raiz, carpeta) in sorted(elegidas, key=lambda k: len(k[1])):
            madre = next((k for k in elegidas if k[0] == raiz and carpeta.startswith(k[1] + "/")), None)
            if madre and (raiz, carpeta) in elegidas:
                hija = elegidas.pop((raiz, carpeta))
                for campo in ("usados", "de", "dichas"):
                    elegidas[madre][campo] = max(elegidas[madre][campo], hija[campo])
        for raiz in sorted({k[0] for k in elegidas}):
            carpetas = [dict(datos, carpeta=k[1]) for k, datos in sorted(elegidas.items()) if k[0] == raiz]
            salida.append({"nodo": nodo, "raiz": raiz, "donde": reales[raiz], "carpetas": carpetas})
    salida.sort(key=lambda c: (-min(1, max(x["usados"] for x in c["carpetas"])) - min(1, max(x["dichas"] for x in c["carpetas"])),
                               -max(x["usados"] for x in c["carpetas"]), -max(x["dichas"] for x in c["carpetas"]),
                               Path(c["nodo"]["ruta"]).name.lower(), c["raiz"]))
    return salida, anchas


def patron(nombre):
    return RE_GLOB.sub(r"\\\1", nombre) + "/**/*"


def entre_comillas(texto):
    return "'" + texto.replace("'", "''") + "'"


def entera(nodo):
    return len(nodo["_cuerpo"].strip().encode("utf-8")) <= ENTERA


def cuerpo_de(nodo):
    archivo = Path(nodo["ruta"]).name
    cuerpo = nodo["_cuerpo"].strip()
    lineas = [] if cuerpo.startswith("# ") and entera(nodo) else [f'# {nodo["titulo"] or Path(nodo["ruta"]).stem}', ""]
    if entera(nodo):
        lineas += [RE_WIKI.sub(r"`\1`", cuerpo), "",
                   f"Esta regla es una copia de la memoria `{archivo}`: si no coinciden, vale la memoria."]
    else:
        descripcion = (nodo.get("descripcion") or "").strip()
        lineas += ([descripcion, ""] if descripcion else []) + [
            f"Antes de tocar estos archivos leé la memoria `{archivo}`: ahí está el detalle."]
    return "\n".join(lineas) + "\n"


def texto_de(c):
    cabeza = ["---", "paths:"] + [f'  - {entre_comillas(patron(x["nombre"]))}' for x in c["carpetas"]]
    cabeza += [f'{MARCA}: {entre_comillas(Path(c["nodo"]["ruta"]).name)}', "---", "", ""]
    return "\n".join(cabeza) + cuerpo_de(c["nodo"])


def destino_de(c):
    return Path(c["donde"]).joinpath(*CARPETA, Path(c["nodo"]["ruta"]).stem + ".md")


def estado_de(c):
    destino = destino_de(c)
    try:
        actual = destino.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
    except OSError:
        return "nueva"
    if actual == texto_de(c):
        return "igual"
    cabeza = actual.split("\n---\n", 1)[0] if actual.startswith("---\n") and "\n---\n" in actual else ""
    return "propia" if RE_PROPIA.search(cabeza) else "ajena"


def codigo_de(c):
    import ordenar
    return ordenar.huella_de(str(destino_de(c)), texto_de(c))


def escribir(c, datos, ahora=None):
    import ordenar
    destino = destino_de(c)
    estado = estado_de(c)
    if estado == "ajena":
        return None, None, f"{destino} ya existe y no la escribió Neuromapa: no la toco."
    if estado == "igual":
        return destino, None, None
    if not dentro(destino, c["donde"]):
        return None, None, f"{destino} queda afuera de la carpeta del proyecto."
    respaldo = ordenar.respaldar(datos, [destino], ahora, que="regla") if estado == "propia" else None
    destino.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(destino, texto_de(c))
    return destino, respaldo, None


def cargas(en_vivo=None, ahora=None):
    import consultas
    import registro
    en_vivo = consultas.EN_VIVO if en_vivo is None else Path(en_vivo)
    desde = (time.time() if ahora is None else ahora) - DIAS_CARGAS * 86400
    pruebas = registro.sesiones_de_prueba(en_vivo)
    cuenta = {}
    for ev in registro.eventos(registro.lineas_desde(en_vivo, desde), desde, (MARCA_CARGA,)):
        ruta = ev.get("f")
        if ev.get("e") != "regla" or not isinstance(ruta, str) or registro.de_prueba(ev, pruebas):
            continue
        k = consultas.clave(ruta)
        veces, ultima = cuenta.get(k, (0, 0))
        cuenta[k] = (veces + 1, max(ultima, registro.numero(ev.get("t"))))
    return cuenta


def renglon_de_cargas(c, cuenta):
    import consultas
    if cuenta is None or estado_de(c) not in ("igual", "propia"):
        return None
    veces, ultima = cuenta.get(consultas.clave(destino_de(c)), (0, 0))
    if not veces:
        return (f"sin cargas anotadas en los últimos {DIAS_CARGAS} días (se anotan desde que está puesto el hook "
                "InstructionsLoaded)")
    d = datetime.datetime.fromtimestamp(ultima)
    return (f'Claude Code la cargó {cantidad(veces, "vez", "veces")} en los últimos {DIAS_CARGAS} días (la última, el '
            f"{d.day}/{d.month} a las {d:%H:%M})")


def porque(x):
    partes = []
    if x["usados"]:
        partes.append(f'se leyó junto con {cantidad(x["usados"], "archivo", "archivos")} de esa carpeta '
                      f'(de {x["de"]} con los que se usó)')
    if x["dichas"]:
        partes.append("la nota nombra esa carpeta o archivos suyos")
    if x["ancho"] is not None:
        parte = round(100 * x["ancho"])
        cuanto = "menos del 1" if parte < 1 else f"el {parte}"
        partes.append(f"ahí está {cuanto} % de lo que se toca del proyecto")
    return "; ".join(partes)


def renglones_de(c, cuenta=None):
    import ordenar
    nodo = c["nodo"]
    tamano = len(nodo["_cuerpo"].strip().encode("utf-8"))
    forma = "va entera" if entera(nodo) else "va su descripción y el aviso de leerla"
    lineas = [f'  {Path(nodo["ruta"]).stem} · «{nodo["titulo"] or nodo["id"]}» ({ordenar.kb(tamano)}: {forma})']
    for x in c["carpetas"]:
        lineas.append(f'      carpeta: {x["nombre"]}/ — {porque(x)}')
    lineas.append(f'      iría en: {destino_de(c)} ({ESTADOS[estado_de(c)]})')
    cargada = renglon_de_cargas(c, cuenta)
    if cargada:
        lineas.append(f"      {cargada}")
    return lineas


def texto(lista, anchas, grupos, elegido, comando, con_uso=True, cuenta=None):
    nombre = {g["clave"]: g["nombre"] for g in grupos}
    propias = [c for c in lista if elegido is None or c["raiz"] == elegido["clave"]]
    donde = f' para «{elegido["nombre"]}»' if elegido else ""
    if not propias:
        lineas = [f"No encontré memorias que convenga pasar a regla por carpeta{donde}."]
    else:
        lineas = [f'Memorias que pueden ser una regla por carpeta{donde}: {len(propias)}.']
        for raiz in dict.fromkeys(c["raiz"] for c in propias):
            if elegido is None:
                lineas.append(f'{nombre.get(raiz, raiz)}:')
            for c in propias:
                if c["raiz"] == raiz:
                    lineas += renglones_de(c, cuenta)
        lineas.append(f"Para ver el texto de una (no cambia nada): {comando} --regla NOTA. Ahí sale el código para "
                      "escribirla con --confirmar.")
    if elegido:
        otros = Counter(nombre.get(c["raiz"], c["raiz"]) for c in lista if c["raiz"] != elegido["clave"])
        if otros:
            lineas.append("En los otros proyectos: " + ", ".join(f"{n} {v}" for n, v in otros.most_common())
                          + f'. Para verlas: {comando} --reglas "NOMBRE" (o todos).')
    if anchas:
        lineas.append(f'{cantidad(anchas, "memoria se usa", "memorias se usan")} con una carpeta demasiado ancha (más del '
                      f"{round(100 * ANCHO)} % de lo que se toca del proyecto): así no sirve como regla por carpeta.")
    if not con_uso:
        lineas.append("Todavía no hay nada aprendido del uso: solo miré las carpetas que nombra cada memoria.")
    lineas.append("Una regla por carpeta es un archivo en .claude/rules/ del proyecto, que Claude Code carga solo cuando lee "
                  "o edita un archivo de esa carpeta. Son propuestas: salen de con qué archivos se leyó cada memoria y de "
                  "las carpetas que nombra. Ninguna se escribe sola.")
    return lineas


def contexto():
    import aprender_pista
    import buscador
    from aprender_comun import prendido
    cerebro = nucleo.desde_disco()
    try:
        aprendido = aprender_pista.cargar() if prendido() else None
    except Exception:
        aprendido = None
    lista, anchas = candidatas(cerebro, aprendido)
    return lista, anchas, buscador.grupos_base(), aprendido is not None


def cargas_anotadas():
    try:
        return cargas()
    except Exception:
        return None


def main(pedido):
    import configuracion
    import pendientes
    try:
        lista, anchas, grupos, con_uso = contexto()
    except Exception as error:
        print(f"No pude buscar las reglas por carpeta ({detalle(error)}).")
        return 1
    visibles = [g for g in grupos if not g["clave"].startswith("@") and g["clave"]]
    elegido, error = pendientes.elegir(pedido, visibles, None, os.getcwd())
    if error:
        print(f"Error: {error}")
        return 1
    for linea in texto(lista, anchas, visibles, elegido, configuracion.comando(), con_uso, cargas_anotadas()):
        print(linea)
    return 0


def main_regla(nota, confirmar=""):
    import configuracion
    try:
        lista, _, grupos, _ = contexto()
    except Exception as error:
        print(f"No pude buscar las reglas por carpeta ({detalle(error)}).")
        return 1
    pedido = Path(str(nota).strip().strip("\"'")).name.lower()
    pedido = pedido[:-3] if pedido.endswith(".md") else pedido
    halladas = [c for c in lista if Path(c["nodo"]["ruta"]).stem.lower() == pedido]
    if not halladas:
        print(f"Error: «{nota}» no está entre las memorias que pueden ser una regla por carpeta. La lista sale con "
              f"{configuracion.comando()} --reglas todos.")
        return 2
    nombre = {g["clave"]: g["nombre"] for g in grupos}
    comando = f'{configuracion.comando()} --regla "{Path(halladas[0]["nodo"]["ruta"]).stem}"'
    if confirmar:
        elegidas = [c for c in halladas if codigo_de(c) == confirmar.strip().lower()]
        if not elegidas:
            print("Error: ese código ya no vale: la memoria, la carpeta o la regla cambiaron después de mostrarla. "
                  f"Volvé a mirarla: {comando}")
            return 2
        antes = estado_de(elegidas[0])
        destino, respaldo, error = escribir(elegidas[0], nucleo.DATOS)
        if error:
            print(f"Error: {error}")
            return 2
        print(f"La regla ya estaba escrita y al día: {destino}" if antes == "igual" else f"Regla escrita: {destino}")
        if respaldo:
            print(f"La que había quedó copiada en {respaldo}.")
        print("Claude Code la carga desde el próximo chat de ese proyecto, cuando lea o edite un archivo de esa carpeta. "
              "Para sacarla, borrá ese archivo.")
        return 0
    cuenta = cargas_anotadas()
    for c in halladas:
        estado = estado_de(c)
        print(f'Regla para «{nombre.get(c["raiz"], c["raiz"])}», sacada de la memoria {Path(c["nodo"]["ruta"]).name}:')
        for x in c["carpetas"]:
            print(f'  carpeta: {x["nombre"]}/ — {porque(x)}')
        print(f"  iría en: {destino_de(c)} ({ESTADOS[estado]})")
        cargada = renglon_de_cargas(c, cuenta)
        if cargada:
            print(f"  {cargada}")
        print("  --- el texto ---")
        for renglon in texto_de(c).rstrip("\n").split("\n"):
            print(f"  {renglon}")
        print("  --- fin ---")
        if estado in ("nueva", "propia"):
            print(f"  Para escribirla: {comando} --confirmar {codigo_de(c)}")
    print("La regla copia texto de la memoria a la carpeta del proyecto: si ese proyecto se sube a un repositorio y "
          ".claude/ no está ignorada, la regla viaja con él.")
    return 0
