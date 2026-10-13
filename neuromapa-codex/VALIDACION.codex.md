# Validación de Neuromapa para Codex

La app escribe la actividad reciente en thread_history_1.sqlite; los JSONL pueden
quedar sin actualizar. El adaptador ahora lee una copia consistente de SQLite y
su WAL sin escribir a las bases originales. Conserva JSONL como alternativa.

- 6 pruebas pasan: registros parciales, reinicio, eventos de herramientas completadas,
  lectura con WAL activo, privacidad, aprendizaje, deduplicación SQLite/JSONL y
  cambios de varios archivos.
- Servidor local autenticado: HTTP 200.
- Navegador: panel Ahora conectado, chat trabajando y ediciones reales visibles.
  No hay errores de JavaScript en el registro del navegador durante esta comprobación.
- Observador en vivo: comprobación cada dos segundos; 229 eventos reales importados.
- Aprendizaje real: 5 rutas y 4 entradas de conexiones.
- El acceso directo abre el mapa existente y arranca el observador si falta.

Los metadatos se guardan en codex-data, excluido de Git. Las copias temporales de
las bases se eliminan al terminar cada lectura. No se publican mensajes, resultados,
credenciales, bases de datos ni eventos personales.

La integración usa el esquema interno actual de Codex desktop; cambios futuros
pueden requerir ajustes. Las consultas de memoria son por MCP; no hay inyección
automática de contexto en cada mensaje ni se crean notas nuevas automáticamente.

## Contexto y propuestas de memoria

- 9 pruebas focalizadas pasan, incluidos recuperación de contexto, límite de salida,
  entradas inválidas no bloqueantes, borradores sin escritura de notas, aprobación
  concreta, deduplicación, detección desde SQLite y descarte de credenciales evidentes.
- MCP por stdio: initialize, tools/list y revisar_memorias responden sin errores.
  Están disponibles sobre, buscar, leer_nota, revisar_memorias, aprobar_memoria y
  descartar_memoria. Reiniciar Codex carga la lista actualizada de herramientas.
- El hook probado contra las notas locales produjo 1361 caracteres de referencias.
- La definición UserPromptSubmit quedó registrada en ~/.codex/hooks.json.
  La activación automática todavía necesita la revisión y confianza nativas de
  Codex mediante /hooks; no se omitió ni alteró ese control.
- Las propuestas son extracción por patrones de respuestas finales, no hechos
  verificados ni recuerdos guardados automáticamente. Aprobarlas requiere que el
  usuario acepte la propuesta concreta. Los datos personales quedan en codex-data.
