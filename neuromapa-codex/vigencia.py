import bisect
import difflib
import os
import re
import time
from pathlib import Path

import configuracion
import historial
from textos import cantidad, citar

DIAS_RESUMEN = 2
TOPE_DIAS = 60
TOPE_NOTAS = 20
TANDA = 200
MINIMO_FRASE = 25
PARECIDO = 0.6
LARGO_MENOR = 0.4
LARGO_MAYOR = 2.5
TOPE_EVENTOS = 12
TOPE_VERSIONES_AVISO = 80
PRESUPUESTO_AVISO = 2.0
CAMBIOS_POR_TRAMO = 2
LARGO_CITA = 220
LARGO_AVISO = 160
ANTES_DEL_CAMBIO = 60
DESTINOS = 3
MUDADA = "mudada"
BORRADA = "borrada"
ESTADO = "estado"
NUMERO = "numero"
FECHA = "fecha"
AMPLIADA = "ampliada"
ACORTADA = "acortada"
OTRAS = "otras"
AVISAN = (ESTADO, NUMERO, OTRAS)
ROTULO = {ESTADO: "cambió el estado", NUMERO: "cambió un número", FECHA: "cambió una fecha o un commit",
          AMPLIADA: "se amplió", ACORTADA: "se acortó", OTRAS: "se reescribió", BORRADA: "se borró"}
RESUMEN = ((ESTADO, "de estado", "de estado"), (NUMERO, "de número", "de número"),
           (OTRAS, "con otras palabras", "con otras palabras"), (FECHA, "de fecha o commit", "de fecha o commit"),
           (AMPLIADA, "ampliada", "ampliadas"), (ACORTADA, "acortada", "acortadas"))
LARGO_VERSION = 7
RE_CABEZA = re.compile(r"\A---\n.*?\n---\n", re.S)
RE_BLOQUE = re.compile(r"\n\s*\n|\n(?=\s*(?:[-*]|\d+\.)\s)|\n(?=#)")
RE_FRASE = re.compile(r"(?<=[.;:!?»)])\s+(?=[A-ZÁÉÍÓÚÑ¿¡(«`*\d-])")
RE_ESPACIO = re.compile(r"\s+")
RE_NUMERO = re.compile(r"\d[\d.,]*")
RE_FECHA = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b20\d\d-\d\d-\d\d\b|\b\d{1,2}:\d\d\b")
RE_COMMIT = re.compile(r"`[0-9a-f]{7,40}`")
RE_SIGNOS = re.compile(r"[\W_]+")
RE_PALABRA = re.compile(r"\w+")
PALABRAS_COMUNES = 0.4
RE_ESTADO = re.compile(r"\b(?:FALTAN?|PENDIENTES?|SIN PROBAR|SIN HACER|SIN COMMIT|EN CURSO|ESCRIT[OA]|EDITAD[OA]|HECH[OA]S?|"
                       r"PROBAD[OA]S?|PUBLICAD[OA]S?|RESUELT[OA]S?|CERRAD[OA]S?|ANDANDO|COMMITEAD[OA]S?|APLICAD[OA]S?|"
                       r"VERIFICAD[OA]S?|APROBAD[OA]S?|sin probar|falta probar|falta commit|sin commit)\b")
PUNTAS = " .;:!?…"
NEGRITA = "**"


def cuerpo(texto):
    return RE_CABEZA.sub("", texto.replace("\r\n", "\n"), count=1).replace(NEGRITA, "")


def plano(texto):
    return RE_ESPACIO.sub(" ", cuerpo(texto))


def frases(texto):
    salida = {}
    for bloque in RE_BLOQUE.split(cuerpo(texto)):
        for frase in RE_FRASE.split(RE_ESPACIO.sub(" ", bloque).strip()):
            frase = frase.strip(" -*")
            if len(frase) >= MINIMO_FRASE:
                salida.setdefault(frase)
    return list(salida)


def sin_fechas(frase):
    return RE_FECHA.sub("", RE_COMMIT.sub("", frase))


def solo_signos(antes, ahora):
    return RE_SIGNOS.sub("", antes) == RE_SIGNOS.sub("", ahora)


def clase_de(antes, ahora):
    if RE_ESTADO.findall(antes) != RE_ESTADO.findall(ahora):
        return ESTADO
    if antes.rstrip(PUNTAS) in ahora:
        return AMPLIADA
    if ahora.rstrip(PUNTAS) in antes:
        return ACORTADA
    if RE_NUMERO.findall(sin_fechas(antes)) != RE_NUMERO.findall(sin_fechas(ahora)):
        return NUMERO
    if RE_FECHA.findall(antes) != RE_FECHA.findall(ahora) or RE_COMMIT.findall(antes) != RE_COMMIT.findall(ahora):
        return FECHA
    return OTRAS


def palabras(frase):
    return frozenset(RE_PALABRA.findall(frase.lower()))


def parecido(antes, ahora, de_antes, de_ahora):
    if not LARGO_MENOR < len(ahora) / len(antes) < LARGO_MAYOR:
        return 0.0
    if len(de_antes & de_ahora) < PALABRAS_COMUNES * min(len(de_antes), len(de_ahora)):
        return 0.0
    s = difflib.SequenceMatcher(None, antes, ahora, autojunk=False)
    if s.real_quick_ratio() < PARECIDO or s.quick_ratio() < PARECIDO:
        return 0.0
    return s.ratio()


def comparar(viejo, nuevo, otras):
    propio, anterior = plano(nuevo), plano(viejo)
    agregadas = [f for f in frases(nuevo) if f not in anterior]
    salida, sueltas = [], []
    for frase in frases(viejo):
        if frase in propio:
            continue
        destino = next((otra for otra, texto in otras.items() if frase in texto), None)
        if destino is None:
            sueltas.append(frase)
        else:
            salida.append({"clase": MUDADA, "antes": frase, "a": destino})
    pares = []
    de_nuevas = [palabras(nueva) for nueva in agregadas] if sueltas else []
    for i, frase in enumerate(sueltas):
        de_frase = palabras(frase)
        for j, nueva in enumerate(agregadas):
            r = parecido(frase, nueva, de_frase, de_nuevas[j])
            if r >= PARECIDO:
                pares.append((-r, i, j))
    pareja, usadas = {}, set()
    for _, i, j in sorted(pares):
        if i not in pareja and j not in usadas:
            pareja[i] = j
            usadas.add(j)
    for i, frase in enumerate(sueltas):
        if i in pareja:
            ahora = agregadas[pareja[i]]
            if not solo_signos(frase, ahora):
                salida.append({"clase": clase_de(frase, ahora), "antes": frase, "ahora": ahora})
        else:
            salida.append({"clase": BORRADA, "antes": frase})
    return salida


def versiones_con_archivos(carpeta):
    if not (historial.repo_de(carpeta) / "HEAD").is_file():
        return []
    salida = historial.git(carpeta, "log", "--format=@%h %ct", "--raw", "--no-abbrev", "--no-renames") or ""
    lista = []
    for linea in salida.splitlines():
        if linea.startswith("@"):
            entero, _, tiempo = linea[1:].partition(" ")
            lista.append({"hash": entero[:LARGO_VERSION], "t": int(tiempo), "archivos": {}})
        elif linea.startswith(":") and "\t" in linea and lista:
            meta, ruta = linea.split("\t", 1)
            campos = meta.split()
            if len(campos) >= 5:
                lista[-1]["archivos"][ruta] = (campos[4][:1], campos[2], campos[3])
    return lista


def contenidos(carpeta, pedidos, textos):
    pedidos = sorted(p for p in set(pedidos) if p.strip("0") and p not in textos)
    for desde in range(0, len(pedidos), TANDA):
        entrada = ("\n".join(pedidos[desde:desde + TANDA]) + "\n").encode("ascii")
        datos = historial.git(carpeta, "cat-file", "--batch", binario=True, entrada=entrada)
        i = 0
        while datos and i < len(datos):
            fin = datos.find(b"\n", i)
            if fin < 0:
                break
            campos = datos[i:fin].split()
            i = fin + 1
            if len(campos) == 3 and campos[1] == b"blob" and campos[2].isdigit():
                largo = int(campos[2])
                textos[campos[0].decode("ascii")] = datos[i:i + largo].decode("utf-8", "replace")
                i += largo + 1
    return textos


def cambios_de(carpeta, ruta, lista=None, tope=None, textos=None):
    lista = versiones_con_archivos(carpeta) if lista is None else lista
    propias = [v for v in lista if ruta in v["archivos"]]
    tocan = [v for v in propias if v["archivos"][ruta][0] != "A"][:tope]
    pedidos = set()
    for v in tocan:
        for otra, (letra, viejo, nuevo) in v["archivos"].items():
            if otra == ruta:
                pedidos.update((viejo, nuevo))
            elif letra != "D":
                pedidos.add(nuevo)
    textos = contenidos(carpeta, pedidos, {} if textos is None else textos)
    eventos = []
    for v in tocan:
        letra, viejo, nuevo = v["archivos"][ruta]
        if viejo not in textos or (letra != "D" and nuevo not in textos):
            continue
        otras = {otra: plano(textos.get(d[2], "")) for otra, d in v["archivos"].items() if otra != ruta and d[0] != "D"}
        for evento in comparar(textos[viejo], "" if letra == "D" else textos[nuevo], otras):
            eventos.append(dict(evento, t=v["t"], hash=v["hash"]))
    return {"versiones": [(v["hash"], v["t"]) for v in propias], "eventos": eventos}


def con_renglones(texto):
    texto = texto.replace("\r\n", "\n")
    cabeza = RE_CABEZA.match(texto)
    salto = texto[:cabeza.end()].count("\n") if cabeza else 0
    partes, comienzos, numeros = [], [], []
    largo = 0
    for numero, renglon in enumerate(texto.split("\n")[salto:], salto + 1):
        limpio = " ".join(renglon.replace(NEGRITA, "").split())
        if limpio:
            comienzos.append(largo)
            numeros.append(numero)
            partes.append(limpio)
            largo += len(limpio) + 1
    return " ".join(partes), comienzos, numeros


def recortes(antes, ahora, largo=LARGO_CITA):
    comun = len(os.path.commonprefix([antes, ahora]))
    desde = 0
    if max(len(antes), len(ahora)) > largo and comun > ANTES_DEL_CAMBIO:
        desde = antes.rfind(" ", 0, comun - ANTES_DEL_CAMBIO) + 1

    def corte(texto):
        return ("…" if desde else "") + texto[desde:desde + largo].strip() + ("…" if desde + largo < len(texto) else "")

    return corte(antes), corte(ahora)


def leer(ruta):
    try:
        return Path(ruta).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def rutas_del_historial(carpeta, lista):
    return {ruta for v in lista for ruta in v["archivos"]}


def hallar(nota, carpetas):
    pedido = str(nota).strip().strip('"')
    nombre = pedido.replace("\\", "/").rsplit("/", 1)[-1].lower()
    nombre = nombre if nombre.endswith(".md") else f"{nombre}.md"
    real = os.path.normcase(os.path.realpath(pedido)) if os.path.isabs(pedido) else ""
    candidatos = []
    for carpeta in carpetas:
        lista = versiones_con_archivos(carpeta)
        base = os.path.normcase(os.path.realpath(carpeta)) + os.sep
        for ruta in sorted(rutas_del_historial(carpeta, lista)):
            if real.startswith(base):
                if os.path.normcase(os.path.normpath(ruta)) == real[len(base):]:
                    return (carpeta, ruta, lista), None
            elif not real and ruta.rsplit("/", 1)[-1].lower() == nombre:
                candidatos.append((carpeta, ruta, lista))
    if not candidatos:
        return None, f"no encontré la nota {pedido} en el historial de la memoria: pasá su nombre de archivo."
    if len(candidatos) > 1:
        rutas = "; ".join(str(Path(c) / r) for c, r, _ in candidatos[:5])
        return None, f"hay {len(candidatos)} notas que se llaman así ({rutas}): pasá la ruta entera."
    return candidatos[0], None


def frase_de_mudadas(mudadas):
    por_destino = {}
    for e in mudadas:
        por_destino.setdefault((e["a"], e["t"]), []).append(e)
    orden = sorted(por_destino.items(), key=lambda par: (-par[0][1], par[0][0]))
    partes = [f"{len(lista)} a {Path(destino).name} el {historial.fecha(t)}" for (destino, t), lista in orden[:DESTINOS]]
    if len(orden) > DESTINOS:
        partes.append(f"y otras {sum(len(lista) for _, lista in orden[DESTINOS:])} en "
                      f"{cantidad(len(orden) - DESTINOS, 'mudanza más', 'mudanzas más')}")
    return "; ".join(partes)


def texto_cambios(carpeta, ruta, datos, todo=False):
    nombre = Path(ruta).name
    tiempos = [t for _, t in datos["versiones"]]
    existe = (Path(carpeta) / ruta).is_file()
    lineas = [f"Cambios de {nombre} según el historial: {cantidad(len(tiempos), 'versión', 'versiones')} de la nota, "
              f"del {historial.fecha(min(tiempos))} al {historial.fecha(max(tiempos))}."
              + ("" if existe else " Hoy esa nota no existe.")]
    eventos = datos["eventos"]
    mudadas = [e for e in eventos if e["clase"] == MUDADA]
    visibles = [e for e in eventos if e["clase"] != MUDADA]
    reescritas = [e for e in visibles if e["clase"] != BORRADA]
    borradas = len(visibles) - len(reescritas)
    partes = []
    if reescritas:
        cuenta = {clase: sum(1 for e in reescritas if e["clase"] == clase) for clase, _, _ in RESUMEN}
        detalle = ", ".join(f"{cuenta[clase]} {una if cuenta[clase] == 1 else varias}"
                            for clase, una, varias in RESUMEN if cuenta[clase])
        partes.append(f"{cantidad(len(reescritas), 'frase reescrita', 'frases reescritas')} ({detalle})")
    if borradas:
        partes.append(cantidad(borradas, "borrada", "borradas") if reescritas
                      else cantidad(borradas, "frase borrada", "frases borradas"))
    lineas.append(" y ".join(partes) + "." if partes else
                  "Ningún dato cambió: lo que tenía sigue igual" + (" o se mudó tal cual a otra nota." if mudadas else "."))
    if mudadas:
        lineas.append(f"{cantidad(len(mudadas), 'frase se mudó', 'frases se mudaron')} tal cual a otra nota y no "
                      f"{'cuenta' if len(mudadas) == 1 else 'cuentan'} como cambio: {frase_de_mudadas(mudadas)}.")
    actual = plano(leer(Path(carpeta) / ruta)) if existe else ""
    mostradas = visibles if todo else visibles[:TOPE_EVENTOS]
    version = None
    for e in mostradas:
        if e["hash"] != version:
            version = e["hash"]
            lineas.append(f"  {historial.fecha(e['t'])} (versión {version}):")
        lineas.append(f"    · {ROTULO[e['clase']]}")
        if e["clase"] == BORRADA:
            lineas.append(f"        decía: {citar(e['antes'], LARGO_CITA)}")
            continue
        antes, ahora = recortes(e["antes"], e["ahora"])
        sigue = " (así sigue hoy)" if e["ahora"] in actual else ""
        lineas.append(f"        antes decía:  {citar(antes)}")
        lineas.append(f"        pasó a decir: {citar(ahora)}{sigue}")
    if len(visibles) > len(mostradas):
        lineas.append(f"  … y {cantidad(len(visibles) - len(mostradas), 'cambio más antiguo', 'cambios más antiguos')}: con "
                      "--todo salen todos.")
    if mostradas:
        lineas.append(f'Para leer la nota entera como estaba antes de un cambio: git --git-dir="{historial.repo_de(carpeta)}" '
                      f'show {mostradas[0]["hash"]}^:"{ruta}"')
    return lineas


def resumen_de(carpeta, dias, ahora=None):
    desde = (time.time() if ahora is None else ahora) - dias * 86400
    lista = [v for v in versiones_con_archivos(carpeta) if v["t"] >= desde]
    textos = {}
    filas = []
    for ruta in sorted(rutas_del_historial(carpeta, lista)):
        visibles = [e for e in cambios_de(carpeta, ruta, lista, textos=textos)["eventos"] if e["clase"] != MUDADA]
        if visibles:
            borradas = sum(1 for e in visibles if e["clase"] == BORRADA)
            filas.append((max(e["t"] for e in visibles), ruta, len(visibles) - borradas, borradas))
    return sorted(filas, key=lambda fila: (-fila[0], fila[1]))


def texto_resumen(carpeta, dias, filas, todo=False):
    plazo = "el último día" if dias == 1 else f"los últimos {dias} días"
    if not filas:
        return [f"Ningún dato de la memoria de {carpeta} cambió en {plazo}, según el historial."]
    lineas = [f"Datos que cambiaron en la memoria de {carpeta} en {plazo}, según el historial "
              f"({cantidad(len(filas), 'nota', 'notas')}):"]
    mostradas = filas if todo else filas[:TOPE_NOTAS]
    for t, ruta, reescritas, borradas in mostradas:
        partes = [cantidad(n, una, varias) for n, una, varias in ((reescritas, "frase reescrita", "frases reescritas"),
                                                                  (borradas, "borrada", "borradas")) if n]
        lineas.append(f"  {Path(ruta).name}: {' y '.join(partes)}; lo último, el {historial.fecha(t)}")
    if len(filas) > len(mostradas):
        lineas.append(f"  … y {cantidad(len(filas) - len(mostradas), 'nota más', 'notas más')}: con --todo salen todas.")
    return lineas


def main_resumen(dias, todo=False):
    carpetas = historial.carpetas()
    for carpeta in carpetas:
        for linea in texto_resumen(carpeta, dias, resumen_de(carpeta, dias), todo):
            print(linea)
    print(f"Para ver qué decía cada una y qué dice ahora: {configuracion.comando()} --cambios NOTA. Lo que solo se mudó "
          "tal cual a otra nota no cuenta.")
    return 0


def main(pedido, todo=False):
    lista = historial.carpetas()
    if not lista or not historial.hay_git():
        print(historial.linea_salud() or "No hay carpetas de memoria en la configuración.")
        return 1
    historial.guardar()
    nota = str(pedido or "").strip()
    if not nota or nota.isdigit():
        return main_resumen(max(1, min(int(nota or DIAS_RESUMEN), TOPE_DIAS)), todo)
    hallada, error = hallar(nota, lista)
    if error:
        print(f"Error: {error}")
        return 2
    carpeta, ruta, versiones = hallada
    for linea in texto_cambios(carpeta, ruta, cambios_de(carpeta, ruta, versiones), todo):
        print(linea)
    return 0


def carpeta_de(ruta, carpetas):
    real = os.path.normcase(os.path.realpath(ruta))
    for carpeta in carpetas:
        base = os.path.normcase(os.path.realpath(carpeta)) + os.sep
        if real.startswith(base):
            return carpeta, real[len(base):].replace(os.sep, "/")
    return None, None


def vigentes(ruta, carpetas, guardadas):
    carpeta, relativa = carpeta_de(ruta, carpetas)
    if carpeta is None:
        return []
    if carpeta not in guardadas:
        guardadas[carpeta] = versiones_con_archivos(carpeta)
    lista = guardadas[carpeta]
    propia = next((r for r in rutas_del_historial(carpeta, lista) if os.path.normcase(r) == relativa), None)
    if propia is None:
        return []
    texto, comienzos, numeros = con_renglones(leer(ruta))
    salida, vistas = [], set()
    for e in cambios_de(carpeta, propia, lista, TOPE_VERSIONES_AVISO)["eventos"]:
        if e["clase"] not in AVISAN or e["ahora"] in vistas:
            continue
        donde = texto.find(e["ahora"])
        if donde < 0:
            continue
        vistas.add(e["ahora"])
        salida.append({"linea": numeros[bisect.bisect_right(comienzos, donde) - 1],
                       "fin": numeros[bisect.bisect_right(comienzos, donde + len(e["ahora"]) - 1) - 1],
                       "cuando": historial.fecha(e["t"]), "clase": e["clase"],
                       "antes": recortes(e["antes"], e["ahora"], LARGO_AVISO)[0]})
    return salida


def anotar(resultado):
    if not historial.hay_git():
        return resultado
    renglones = {}
    for grupo in resultado.get("grupos", ()):
        for nota in grupo["notas"]:
            renglones[os.path.normcase(nota["ruta"])] = [p["linea"] for p in nota["pasajes"]]
    carpetas = historial.carpetas()
    guardadas = {}
    limite = time.monotonic() + PRESUPUESTO_AVISO
    previo = historial._limite[0]
    historial._limite[0] = limite
    try:
        for p in resultado.get("leerPrimero", ()):
            citados = [n for n in renglones.get(os.path.normcase(p["ruta"]), ()) if p["linea"] <= n <= p["fin"]]
            if not citados or time.monotonic() >= limite:
                continue
            cambios = [c for c in vigentes(p["ruta"], carpetas, guardadas)
                       if any(c["linea"] <= n <= c["fin"] for n in citados)]
            if cambios:
                p["cambios"] = cambios[:CAMBIOS_POR_TRAMO]
    finally:
        historial._limite[0] = previo
    return resultado
