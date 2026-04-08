# TODO.md — Mejoras y features futuras

Lista de mejoras planificadas y posibles nuevas características
para versiones futuras de LogStream Analytics.

---

## Alta prioridad

### Migración a PostgreSQL
SQLite funciona bien para desarrollo y demos, pero tiene limitaciones
de concurrencia para producción. Migrar a PostgreSQL permitiría escrituras
verdaderamente concurrentes sin necesidad del lock distribuido en Redis,
y habilitaría features avanzadas como búsqueda full-text con `tsvector`.

### Tests automatizados
Agregar suite de tests con `pytest`:
- Tests unitarios para `config.py`, `db.py`, `mailer.py`, `protocol.py`
- Tests de integración para el flujo completo (producer → server → worker → db)
- Mocks para Redis y SQLite en tests unitarios
- Tests de carga para medir throughput del Log Server

### Reintentos y dead letter queue
Los workers Celery reintentan tareas fallidas hasta 3 veces, pero no hay
manejo de mensajes que fallan definitivamente. Implementar una cola
`dead_letter` en Redis donde se muevan los logs que no pudieron procesarse
para revisión manual.

### Healthcheck endpoints
Agregar un endpoint HTTP mínimo (usando `aiohttp` o similar) a cada
componente para exponer su estado (`/health`), permitiendo integración con
herramientas de monitoreo como Prometheus o un balanceador de carga.

---

## Media prioridad

### Dashboard web
Implementar una interfaz web (Flask o FastAPI + algún frontend simple)
que muestre en tiempo real:
- Gráficos de logs por nivel y fuente
- Stream de alertas en vivo
- Tabla de logs con filtros interactivos
- Métricas de throughput del sistema

### Correlación de eventos
Detectar patrones entre logs de distintas fuentes dentro de una ventana
de tiempo. Por ejemplo: si `database` reporta un `CRITICAL` y `webapp`
reporta varios `ERROR` en los siguientes 30 segundos, generar una alerta
correlacionada de mayor prioridad.

### Paginación interactiva en el Query Client
Actualmente el cliente muestra los resultados de una sola consulta.
Agregar modo interactivo con navegación por páginas (`n` para siguiente,
`p` para anterior) similar a `less`.

### Retención configurable de logs
Implementar la tarea `cleanup_old_logs` como tarea periódica de Celery
Beat con schedule configurable desde el `.env` (actualmente existe la
función pero no se ejecuta automáticamente).

```env
# Ejemplo de variables a agregar
CLEANUP_ENABLED=true
CLEANUP_RETENTION_DAYS=30
CLEANUP_SCHEDULE_CRON=0 3 * * *   # todos los días a las 3am
```

### Autenticación en el Query Engine
El Query Engine acepta conexiones sin autenticación. Agregar un esquema
de token simple: el cliente envía un token en el campo `auth` del request,
el engine lo valida contra una variable del `.env` antes de ejecutar la
consulta.

---

## Baja prioridad / ideas a futuro

### Despliegue con Docker Compose
Crear un `docker-compose.yml` que levante todos los servicios con un solo
comando:
- Redis
- Log Server
- Workers Celery (N réplicas)
- Alert Manager
- Query Engine

### Soporte para múltiples FIFOs
Actualmente hay un único FIFO para todas las alertas. Con múltiples
Alert Managers especializados (uno para mail, otro para Slack, otro para
webhook) se podría tener un FIFO por destino.

### Integración con Slack / webhooks
Agregar un handler de notificaciones alternativo al mail: enviar alertas
a un canal de Slack o a un webhook HTTP genérico, configurable desde el
`.env`.

### Búsqueda full-text en mensajes
La búsqueda actual usa `LIKE '%texto%'` que no usa índices. Implementar
búsqueda full-text con SQLite FTS5 para consultas más rápidas sobre
mensajes largos.

### Compresión de logs históricos
Los logs más viejos que N días podrían comprimirse o archivarse en un
almacenamiento más barato (S3, archivo gzip local), manteniendo solo un
resumen estadístico en la DB principal.

### Modo replay
Capacidad de reproducir logs históricos desde la DB como si fueran en
tiempo real, útil para debugging y análisis post-mortem.

### Soporte para fuentes dinámicas
Actualmente las fuentes válidas (`webapp`, `database`, `api`) están
definidas en el código. Permitir registrar nuevas fuentes dinámicamente
desde el `.env` o desde una tabla de configuración en la DB.

### CLI de administración
Agregar subcomandos administrativos al Query Client:
```bash
python -m src.query admin stats-reset
python -m src.query admin cleanup --days 7
python -m src.query admin fifo-status
```
