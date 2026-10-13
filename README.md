# Neuromapa para OpenAI Codex

Memoria local para agentes de IA, mapa cerebral 3D y actividad en vivo. Adaptación de [Neuromapa](https://github.com/lumiel777/neuromapa), escrita en Python y conectada a Codex por MCP.

- Visualiza notas y conexiones en un mapa 3D.
- Lee actividad de Codex desktop desde SQLite y sesiones JSONL.
- Busca memorias mediante MCP: `sobre`, `buscar` y `leer_nota`.
- Ofrece contexto relevante antes de cada mensaje con un hook nativo.
- Propone decisiones y soluciones para guardar; cada memoria necesita aprobación del usuario.

[Guía de instalación y uso](neuromapa-codex/README.codex.md) · [Validación](neuromapa-codex/VALIDACION.codex.md)

## Empezar

```powershell
cd neuromapa-codex
python codex_adapter.py init
python codex_adapter.py abrir
```

Para registrar el contexto automático: `python instalar_contexto.py`. Después revisa y confía en la definición desde `/hooks` en Codex CLI y reinicia Codex. El hook no se activa sin esa revisión.

Para revisar propuestas, pide a Codex «revisa las memorias propuestas» y acepta o descarta cada una.

Las memorias, conversaciones, propuestas y credenciales permanecen en tu computadora. No se incluyen datos personales en este repositorio. La detección de propuestas usa patrones y no verifica automáticamente su veracidad.

Código original y adaptación bajo licencia MIT; consulta [LICENSE](neuromapa-codex/LICENSE).
