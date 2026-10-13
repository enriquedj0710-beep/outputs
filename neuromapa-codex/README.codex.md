# Neuromapa para Codex

Adaptación local del proyecto MIT de lumiel777. Requiere Python 3.10+.
Conserva el mapa 3D, el buscador y el diagnóstico de notas originales.

## Abrir

En esta carpeta:

```powershell
python codex_adapter.py init
python codex_adapter.py abrir
```

El segundo comando mantiene el mapa y el observador activos hasta cerrar la terminal.
Abre el navegador con la dirección local del servidor.
Para agregar instrucciones de un proyecto al crear una configuración nueva:

```powershell
python codex_adapter.py --project C:\ruta\proyecto init
```

Si ya existe `codex-data/config.json`, editá sus fuentes para agregar proyectos.
`--codex-home` selecciona otra instalación; por defecto usa `CODEX_HOME` o `~/.codex`.
`--data` elige otro directorio de datos. Estas opciones van antes del comando.

## Consultar notas desde Codex

Registrar el conector MCP usando la ruta absoluta a esta copia:

```powershell
codex mcp add neuromapa -- python C:\ruta\neuromapa-codex\codex_adapter.py mcp
```

Reiniciá Codex después de registrarlo. Las herramientas son `sobre`, `buscar` y
`leer_nota`. También están `revisar_memorias`, `aprobar_memoria` y `descartar_memoria`.
También se puede consultar desde la terminal:

```powershell
python codex_adapter.py consulta --sobre "tema"
python codex_adapter.py consulta --salud
```

## Alcance y datos

- Indexa Markdown de `~/.codex/memories`, `~/.codex/AGENTS.md` y los AGENTS.md de
  proyectos agregados explícitamente. No indexa `auth.json` ni configura credenciales.
- Lee el historial SQLite de Codex desktop (`thread_history_1.sqlite`) y observa
  `sessions/**/*.jsonl` como alternativa para sesiones sin proyección SQLite.
  Evita duplicar actividad presente en ambas fuentes. Muestra inicio, turnos, herramientas,
  respuestas de herramientas y compactación cuando el registro los contiene.
- Guarda sólo metadatos: fechas, identificadores, nombres de herramientas y rutas.
  No copia mensajes, resultados, razonamiento ni cuerpos de cambios al registro del mapa.
- Recupera una hora de historial de escritorio (diez minutos para JSONL) y continúa
  desde identificadores y offsets persistentes. Lee sólo
  registros completos. Un candado evita dos observadores sobre los mismos datos.
- Las bases de Codex no se modifican. Usa copias temporales del archivo y su WAL,
  descarta copias tomadas durante una escritura y las elimina al terminar la consulta.
  Los textos privados se procesan sólo para extraer metadatos; nunca se guardan en
  los eventos ni en los identificadores persistentes del observador.
- `codex-data/codex-status.json` informa cuándo se comprobó la actividad, cuántos
  eventos se importaron y si hubo algún error de lectura.
- Los archivos de sesión son un formato interno de Codex: futuras versiones pueden
  necesitar ajustes. Herramientas ejecutadas dentro de `exec` se muestran como un
  evento genérico; no se interpretan ni ejecutan los programas JavaScript registrados.
- No implementa los hooks específicos de Claude, su freno de gasto ni su modo dormir
  con Claude. Tampoco atribuye precios de Claude a tokens de Codex.
- Conserva textos de interfaz originales que mencionan Claude. El mapa usa recursos
  WebGL del proyecto original; puede necesitar Internet para cargar sus bibliotecas.
- Las notas contienen información privada: no compartas el HTML generado sin revisarlo.

## Verificar

```powershell
python -m unittest test_codex_adapter -v
python -m unittest test_codex_history -v
python herramientas/prueba_humo.py
```

El registro MCP es un paso separado; esta adaptación no altera la configuración
global de Codex al ejecutarse.

## Contexto automático

```powershell
python instalar_contexto.py
```

Después abrí `/hooks` en Codex CLI y revisá/confiá en el hook de Neuromapa.
Codex exige esa revisión; registrar el archivo no activa el hook por sí solo.
Reiniciá Codex después de confiar en la definición. En cada mensaje, el hook busca
hasta tres notas relevantes y ofrece como máximo 4000 caracteres de referencias.
No guarda el mensaje del usuario, no bloquea tareas y no ejecuta el texto de las notas.

## Propuestas de memoria

El observador detecta algunas frases explícitas de decisiones, causas y soluciones
en respuestas finales recientes. Es una detección por patrones, no una evaluación
de veracidad: puede omitir decisiones o sugerir algo que no deba conservarse.
Los borradores quedan privados en `codex-data/memoria-propuestas.json`.

En Codex, pedí «revisa las memorias propuestas». Podés corregir el texto y aceptar
o descartar cada propuesta. La herramienta de aprobación necesita la confirmación
`APROBAR <id>` de esa propuesta concreta; el agente no debe aceptarlas por su cuenta.
Las aceptadas se guardan en `codex-data/memorias-aprobadas/`, se indexan en el mapa
y quedan disponibles para las consultas MCP y el contexto automático.
No se escriben automáticamente en `~/.codex/memories`, ni se suben a GitHub.
