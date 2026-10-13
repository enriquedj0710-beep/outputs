import os
import re
import unicodedata
from collections import Counter
from pathlib import Path

import cerebro as nucleo
from archivos import dentro, escribir_atomico
from textos import cantidad, detalle

CARPETA = (".claude", "skills")
ARCHIVO = "SKILL.md"
MARCA = "neuromapa"
PASOS = 3
COMANDOS = 2
SEGUIDO = 3.0
LARGO_NOMBRE = 64
LARGO_TITULO = 90
RE_COMIENZO = re.compile(r"(?:RECETA|Receta|Pasos|Procedimiento|C[oó]mo\s+(?:se\s+\w+|\w+(?:ar|er|ir)(?:se|lo|la|los|las)?)"
                         r"|Para\s+\w+(?:ar|er|ir)(?:se|lo|la|los|las)?|How\s+to|Steps)\b")
RE_PASO = re.compile(r"^[ \t]*\d{1,2}[.)][ \t]+\S", re.M)
RE_COMANDO = re.compile(r"`[^`\n]*(?:\.(?:py|ps1|bat|cmd|sh|exe|js|mjs)\b|[ \t]--?\w|\b(?:git|npm|npx|python|dotnet|node|pip|cargo|make) )"
                        r"[^`\n]*`|^[ \t]*(?:```|~~~)\w*[ \t]*$", re.M)
RE_WIKI = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
RE_PROPIA = re.compile(r"^[ \t]+" + MARCA + r":[ \t]*(.*?)[ \t]*$", re.M)
RE_NUMERADA = re.compile(r"^(.*?):(\d{1,3})$")
ESTADOS = {"nueva": "no existe todavía", "igual": "ya está escrita y al día",
           "propia": "ya está escrita, pero la memoria cambió: se puede volver a escribir",
           "ajena": "ya hay una skill con ese nombre que no escribió Neuromapa: no se toca"}


def recortar(texto, largo):
    return texto if len(texto) <= largo else texto[:largo - 1].rstrip() + "…"


def titulo_de(crudo):
    import ordenar
    limpio = ordenar.limpiar(crudo.split("\n", 1)[0])
    corte = re.search(r"[:.;]\s", limpio + " ")
    etiqueta = bool(corte) and corte.group(0)[0] == ":" and corte.start() <= LARGO_TITULO
    return recortar((limpio[:corte.start()] if corte else limpio).strip(" :"), LARGO_TITULO), etiqueta


def sin_sangria(renglones):
    cuerpo = [r.rstrip("\r\n") for r in renglones]
    while cuerpo and not cuerpo[-1].strip():
        cuerpo.pop()
    return "\n".join(cuerpo)


def de_la_nota(nodo):
    import medico
    import ordenar
    renglones = ordenar.renglones_de(nodo["_cuerpo"])
    piezas = ordenar.piezas_de(renglones)
    salida = []
    hasta_donde = -1
    desfase = [0]
    for r in renglones:
        desfase.append(desfase[-1] + len(r))
    for p in piezas:
        if p["clase"] not in ("titulo", "item", "parrafo") or p["desde"] < hasta_donde:
            continue
        titulo, etiqueta = titulo_de(p["titulo"])
        if not RE_COMIENZO.match(titulo) or (p["clase"] != "titulo" and not etiqueta):
            continue
        hasta = piezas[p["fin_seccion"] - 1]["hasta"] if p["clase"] == "titulo" else p["hasta"]
        texto = sin_sangria(renglones[p["desde"]:hasta])
        pasos, comandos = len(RE_PASO.findall(texto)), len(RE_COMANDO.findall(texto))
        if pasos < PASOS and comandos < COMANDOS:
            continue
        hasta_donde = hasta
        salida.append({"nota": nodo["id"], "ruta": nodo["ruta"], "titulo": titulo, "texto": texto,
                       "linea": medico.linea_en(nodo, desfase[p["desde"]]), "pasos": pasos, "comandos": comandos,
                       "numero": len(salida) + 1})
    return salida


def juntar(cerebro, aprendido=None):
    import buscador
    import consultas
    lista = buscador.proyectos_conocidos()
    reales = {clave: Path(p["raiz"]) for clave, p in lista if p.get("raiz")}
    for carpeta in nucleo.carpetas_propias():
        reales.setdefault(consultas.clave(carpeta).rstrip("/"), Path(carpeta))
    de_nota = buscador.proyecto_de_cada_nota(cerebro)
    salida = []
    for nodo in cerebro.nodos:
        if not cerebro.fuente_de.get(nodo["id"], {}).get("memoria") or nodo["tipo"] == "indice" or nucleo.es_archivo(nodo):
            continue
        raiz = de_nota.get(nodo["id"], "")
        veces = aprendido.veces.get(consultas.clave(nodo["ruta"]), 0.0) if aprendido is not None else 0.0
        for receta in de_la_nota(nodo):
            receta.update(raiz=raiz if raiz in reales else "", donde=reales.get(raiz), veces=veces,
                          nota_titulo=nodo["titulo"] or Path(nodo["ruta"]).stem)
            salida.append(receta)
    salida.sort(key=lambda r: (-r["veces"], Path(r["ruta"]).name.lower(), r["numero"]))
    return salida


def nombre_de(receta):
    plano = unicodedata.normalize("NFKD", f'{Path(receta["ruta"]).stem} {receta["titulo"]}')
    plano = "".join(c for c in plano if not unicodedata.combining(c)).lower()
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", plano)).strip("-")[:LARGO_NOMBRE].strip("-")


def entre_comillas(texto):
    return "'" + texto.replace("'", "''") + "'"


def texto_de(receta):
    archivo = Path(receta["ruta"]).name
    titulo = receta["titulo"]
    descripcion = f'{titulo} ({receta["nota_titulo"]}). Usar cuando haya que hacer eso; los pasos salen de la memoria {archivo}.'
    cabeza = ["---", f"name: {nombre_de(receta)}", f"description: {entre_comillas(descripcion)}", "metadata:",
              f"  {MARCA}: {entre_comillas(archivo)}", "---", ""]
    cabeza += [] if receta["texto"].lstrip().startswith("#") else [f"# {titulo}", ""]
    cabeza += [RE_WIKI.sub(r"`\1`", receta["texto"]), "",
               f"Esta skill es una copia de una receta de la memoria `{archivo}`: si no coinciden, vale la memoria."]
    return "\n".join(cabeza) + "\n"


def destino_de(receta):
    import configuracion
    base = Path(receta["donde"]).joinpath(*CARPETA) if receta["donde"] else configuracion.carpeta_de_claude() / CARPETA[-1]
    return base / nombre_de(receta) / ARCHIVO


def estado_de(receta):
    try:
        actual = destino_de(receta).read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
    except OSError:
        return "nueva"
    if actual == texto_de(receta):
        return "igual"
    cabeza = actual.split("\n---\n", 1)[0] if actual.startswith("---\n") and "\n---\n" in actual else ""
    return "propia" if RE_PROPIA.search(cabeza) else "ajena"


def codigo_de(receta):
    import ordenar
    return ordenar.huella_de(str(destino_de(receta)), texto_de(receta))


def escribir(receta, datos, ahora=None):
    import configuracion
    import ordenar
    destino = destino_de(receta)
    estado = estado_de(receta)
    if estado == "ajena":
        return None, None, f"{destino} ya existe y no la escribió Neuromapa: no la toco."
    if estado == "igual":
        return destino, None, None
    if not dentro(destino, receta["donde"] or configuracion.carpeta_de_claude()):
        return None, None, f"{destino} queda afuera de la carpeta del proyecto."
    respaldo = ordenar.respaldar(datos, [destino], ahora, que="skill") if estado == "propia" else None
    destino.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(destino, texto_de(receta))
    return destino, respaldo, None


def pedido_de(receta):
    return f'{Path(receta["ruta"]).stem}:{receta["numero"]}'


def renglones_de(receta):
    import ordenar
    medida = "; ".join(x for x in (cantidad(receta["pasos"], "paso numerado", "pasos numerados") if receta["pasos"] else "",
                                   cantidad(receta["comandos"], "comando", "comandos") if receta["comandos"] else "") if x)
    uso = f'la nota se leyó {ordenar.decimal(receta["veces"])} veces' if receta["veces"] else "sin lecturas anotadas"
    seguido = " (se usa seguido)" if receta["veces"] >= SEGUIDO else ""
    escrita = {"igual": "; ya es una skill y está al día", "propia": "; ya es una skill, pero la memoria cambió"}.get(
        estado_de(receta), "")
    return [f'  {pedido_de(receta)} · «{receta["titulo"]}» — {Path(receta["ruta"]).name}:{receta["linea"]}',
            f'      {ordenar.kb(len(receta["texto"].encode("utf-8")))}, {medida}; {uso}{seguido}{escrita}']


def texto(lista, grupos, elegido, comando, con_uso=True):
    nombre = {g["clave"]: g["nombre"] for g in grupos}
    propias = [r for r in lista if elegido is None or r["raiz"] == elegido["clave"]]
    donde = f' de «{elegido["nombre"]}»' if elegido else ""
    if not propias:
        lineas = [f"No encontré recetas en las memorias{donde}."]
    else:
        seguidas = sum(1 for r in propias if r["veces"] >= SEGUIDO)
        lineas = [f'Recetas en las memorias{donde}: {len(propias)}'
                  + (f' ({cantidad(seguidas, "de una nota que se usa seguido", "de notas que se usan seguido")})' if seguidas else "")
                  + "."]
        for raiz in dict.fromkeys(r["raiz"] for r in propias):
            if elegido is None:
                lineas.append(f'{nombre.get(raiz, "Sin proyecto")}:')
            for r in propias:
                if r["raiz"] == raiz:
                    lineas += renglones_de(r)
        lineas.append(f"Para ver cómo quedaría una como skill (no cambia nada): {comando} --receta NOTA:N. Ahí sale el "
                      "código para escribirla con --confirmar.")
    if elegido:
        otros = Counter(nombre.get(r["raiz"], "Sin proyecto") for r in lista if r["raiz"] != elegido["clave"])
        if otros:
            lineas.append("En los otros proyectos: " + ", ".join(f"{n} {v}" for n, v in otros.most_common())
                          + f'. Para verlas: {comando} --recetas "NOMBRE" (o todos).')
    if not con_uso:
        lineas.append("Todavía no hay nada aprendido del uso: no sé cuáles se usan seguido.")
    lineas.append("Una receta es un tramo de una memoria que dice cómo se hace algo, con pasos o comandos. Pasada a skill, "
                  "Claude Code la carga sola cuando hace falta y la sigue paso a paso. Son propuestas: ninguna se escribe "
                  "sola, y conviene revisar su descripción, que es lo que Claude lee para decidir si la usa.")
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
    return juntar(cerebro, aprendido), [g for g in buscador.grupos_base() if g["clave"] and not g["clave"].startswith("@")], \
        aprendido is not None


def main(pedido):
    import configuracion
    import pendientes
    try:
        lista, grupos, con_uso = contexto()
    except Exception as error:
        print(f"No pude buscar las recetas ({detalle(error)}).")
        return 1
    elegido, error = pendientes.elegir(pedido, grupos, None, os.getcwd())
    if error:
        print(f"Error: {error}")
        return 1
    for linea in texto(lista, grupos, elegido, configuracion.comando(), con_uso):
        print(linea)
    return 0


def main_receta(pedido, confirmar=""):
    import configuracion
    try:
        lista, _, _ = contexto()
    except Exception as error:
        print(f"No pude buscar las recetas ({detalle(error)}).")
        return 1
    crudo = str(pedido).strip().strip("\"'")
    m = RE_NUMERADA.match(crudo)
    nota, numero = (m.group(1), int(m.group(2))) if m else (crudo, None)
    nota = Path(nota).name.lower()
    nota = nota[:-3] if nota.endswith(".md") else nota
    de_la = [r for r in lista if Path(r["ruta"]).stem.lower() == nota]
    halladas = [r for r in de_la if numero is None or r["numero"] == numero]
    comando = configuracion.comando()
    if not halladas:
        print(f"Error: no encontré esa receta. La lista sale con {comando} --recetas todos."
              if not de_la else f"Error: esa nota tiene {cantidad(len(de_la), 'receta', 'recetas')}: no hay número {numero}.")
        return 2
    if len(halladas) > 1:
        print(f"Esa nota tiene {len(halladas)} recetas; decí cuál con su número:")
        for r in halladas:
            for linea in renglones_de(r):
                print(linea)
        return 2 if confirmar else 0
    receta = halladas[0]
    estado = estado_de(receta)
    if confirmar:
        if codigo_de(receta) != confirmar.strip().lower():
            print("Error: ese código ya no vale: la memoria o la skill cambiaron después de mostrarla. Volvé a mirarla: "
                  f'{comando} --receta "{pedido_de(receta)}"')
            return 2
        destino, respaldo, error = escribir(receta, nucleo.DATOS)
        if error:
            print(f"Error: {error}")
            return 2
        print(f"La skill ya estaba escrita y al día: {destino}" if estado == "igual" else f"Skill escrita: {destino}")
        if respaldo:
            print(f"La que había quedó copiada en {respaldo}.")
        print("Claude Code la ofrece desde el próximo chat. Para sacarla, borrá su carpeta.")
        return 0
    print(f'Skill sacada de la receta «{receta["titulo"]}» de {Path(receta["ruta"]).name}:{receta["linea"]}:')
    print(f"  iría en: {destino_de(receta)} ({ESTADOS[estado]})")
    print("  --- el texto ---")
    for renglon in texto_de(receta).rstrip("\n").split("\n"):
        print(f"  {renglon}")
    print("  --- fin ---")
    if estado in ("nueva", "propia"):
        print(f'  Para escribirla: {comando} --receta "{pedido_de(receta)}" --confirmar {codigo_de(receta)}')
    print("La skill copia texto de la memoria a esa carpeta: si es la de un proyecto que se sube a un repositorio y .claude/ "
          "no está ignorada, viaja con él. Antes de escribirla conviene mejorar su descripción.")
    return 0
