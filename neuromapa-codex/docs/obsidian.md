# Neuromapa y Obsidian

No compiten: la diferencia es **quién los usa**. Obsidian es un cuaderno para que vos escribas y leas tus notas.
Neuromapa trabaja con la memoria de Claude mientras Claude trabaja: muestra qué nota lee cada chat, avisa cuando una
nota quedó vieja y, si prendés el contexto automático, le acerca a Claude la nota justa en cada pedido.

Se pueden usar juntos sobre la misma carpeta, porque la memoria de Claude Code ya es lo que Obsidian sabe abrir:
archivos Markdown con un encabezado YAML y `[[enlaces]]` entre notas.

## Abrir la memoria de Claude Code en Obsidian

1. Buscá la carpeta de la memoria de tu proyecto: `~/.claude/projects/<proyecto>/memory/` (en Windows,
   `C:\Users\<tu usuario>\.claude\projects\<proyecto>\memory\`). Adentro están `MEMORY.md` y una nota por tema.
2. En Obsidian, elegí «Abrir carpeta como bóveda» («Open folder as vault») y marcá esa carpeta. En Mac, las carpetas
   que empiezan con punto no se ven en el selector: con Cmd + Mayús + punto aparecen.
3. Listo. Los `[[enlaces]]` funcionan porque Claude Code le pone a cada nota el mismo nombre que a su archivo, y
   `MEMORY.md` se ve como una nota índice, con sus enlaces comunes de Markdown.

Obsidian muestra solo los cambios que hace Claude: se pone al día cuando otro programa toca un archivo de la bóveda.

## Qué te da cada uno

| | Obsidian | Neuromapa |
|---|---|---|
| Para quién | Para vos: escribir, leer y navegar tus notas | Para Claude, y para que vos veas lo que hace |
| Qué muestra | Las notas, sus enlaces, el grafo y lo que enlaza a cada nota | Lo mismo como un cerebro, más qué lee y edita cada chat en vivo y qué notas se usan juntas |
| Qué revisa | — | El médico: enlaces a notas que ya no existen, memorias que el índice no lista, encabezados incompletos y notas que ya no entran en una lectura; con tus proyectos cargados, también citas `archivo:línea` corridas y commits que no existen |
| Qué le da a Claude | Nada: Claude no se entera de que existe | La búsqueda `sobre`, los avisos y, si lo prendés, el contexto automático |

## Cuidados

- **La carpeta `.obsidian`.** Obsidian guarda sus opciones en una carpeta `.obsidian` adentro de la bóveda, o sea
  adentro de la memoria. No molesta: Neuromapa lee solo los `.md` que están sueltos en la carpeta de la memoria, y su
  historial de versiones saltea las carpetas ocultas.
- **No muevas notas a subcarpetas.** Con la configuración de fábrica, Neuromapa lee la carpeta de la memoria sin
  subcarpetas: una nota que metas en una carpeta deja de verse en el mapa y en la búsqueda.
- **Al cambiarle el nombre a una nota,** Obsidian puede arreglar solo los enlaces de las otras notas y los de
  `MEMORY.md` (opción «Automatically update internal links»). Lo que no cambia es el `name:` del encabezado, que
  tiene que ser igual al nombre del archivo: cambialo a mano. Si te olvidás, el médico te lo marca.
- **El encabezado, mejor en modo fuente.** Las notas de Claude Code suelen llevar el tipo adentro de `metadata:`, y el
  panel de propiedades de Obsidian no maneja propiedades anidadas. Para ver y tocar el encabezado, usá el modo fuente
  («Source mode»), que lo muestra como texto.
- **Una nota creada en Obsidian** necesita lo mismo que las de Claude para que Claude la encuentre: el encabezado con
  `name`, `description` y el tipo, y un renglón en `MEMORY.md` que diga cuándo abrirla. Si falta algo, el médico lo
  avisa (`/neuromapa:salud`).
- **De a uno por nota.** Si editás una nota a mano mientras un chat la está cambiando, uno de los dos puede pisar al
  otro. Si pasa, `neuromapa --historial "texto"` busca el renglón perdido en las versiones guardadas (hace falta git).
- **Lo que suba Obsidian ya no es local.** Neuromapa no manda tus notas a ningún lado. Si prendés Obsidian Sync,
  Obsidian Publish o un plugin de la comunidad sobre esa bóveda, tu memoria sale de tu computadora por ese camino.

## Si ya tenés una bóveda de Obsidian

También sirve al revés: tu bóveda puede entrar al mapa como una fuente más del `config.json` (campo `fuentes`, con su
carpeta en `raices`; ahí sí puede leer las subcarpetas). Ojo: al escribir `fuentes` dejan de usarse las de fábrica,
así que hay que listar también la memoria de Claude Code. [Cómo funciona](como-funciona.md) explica cada campo y
[demo/config.json](../demo/config.json) sirve de ejemplo.

Esas notas aparecen en el mapa y en la búsqueda, y Neuromapa no las cambia por su cuenta. Todavía no lo probamos con
bóvedas grandes: si algo de la tuya no se lee bien, abrí un issue.
