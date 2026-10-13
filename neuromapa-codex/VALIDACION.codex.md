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
