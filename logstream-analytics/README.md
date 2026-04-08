# LogStream Analytics

Sistema distribuido de monitoreo y análisis de logs en tiempo real.

**Materia:** Computación II — Ingeniería Informática  
**Alumno:** Maximo Lucentini

---

## ¿Qué hace?

LogStream centraliza eventos de log provenientes de múltiples servicios y máquinas,
los procesa de forma concurrente y permite:

- Detectar alertas críticas en tiempo real
- Consultar histórico con filtros
- Obtener métricas de salud del sistema
- Recibir notificaciones por mail ante eventos CRITICAL

---

## Flujo del sistema

```
Log Producer(s)
    │  TCP [4 bytes len][JSON]
    ▼
Log Server (asyncio, puerto 9000)
    │  Redis RPUSH log_queue
    ▼
Redis Broker
    │  Celery consume_logs.py
    ▼
Workers Celery (paralelo)
    ├── SQLite (tabla logs)
    └── FIFO /data/alert_pipe  ←── solo si ERROR o CRITICAL
                │
                ▼
        Alert Manager (proceso independiente)
            ├── Consola (colores por nivel)
            ├── SQLite (tabla alerts)
            └── Mail SMTP (solo CRITICAL, configurable)

Query Client (CLI)
    │  TCP [4 bytes len][JSON]
    ▼
Query Engine (asyncio, puerto 9001)
    │  SQLite READ
    ▼
Resultados (tabla formateada o JSON)
```

---

## Uso rápido

### Consultar logs

```bash
# Últimos 100 logs (tabla formateada)
python -m src.query logs

# Filtrar por nivel y fuente
python -m src.query logs --level ERROR --source webapp

# Buscar texto en el mensaje
python -m src.query logs --message "timeout" --limit 20

# Rango de fechas
python -m src.query logs --start-date 2026-03-01 --end-date 2026-03-28

# Salida JSON cruda (útil para scripts)
python -m src.query logs --level CRITICAL --json
```

### Consultar alertas

```bash
# Todas las alertas
python -m src.query alerts

# Solo alertas críticas
python -m src.query alerts --level CRITICAL

# Alertas que no recibieron notificación por mail
python -m src.query alerts --not-mailed

# Alertas de base de datos con texto específico
python -m src.query alerts --source database --message "deadlock"
```

### Ver estadísticas

```bash
# Estadísticas globales (total, por nivel, por fuente)
python -m src.query stats

# Estadísticas de un período
python -m src.query stats --start-date 2026-03-01

# En JSON
python -m src.query stats --json
```

### Simular clientes (Log Producers)

```bash
# Webapp a 5 logs/seg (default)
python -m src.clients --source webapp

# Base de datos con alta tasa de errores
python -m src.clients --source database --rate 10 --error-rate 0.3

# API con anomalías frecuentes (CRITICAL)
python -m src.clients --source api --anomaly-rate 0.05

# Conectar a servidor remoto
python -m src.clients --source webapp --server 192.168.1.100:9000
```

### Alert Manager

```bash
# Comportamiento según .env
python -m src.alerts

# Sin mail para esta ejecución
python -m src.alerts --no-mail

# FIFO personalizado
python -m src.alerts --fifo /tmp/mi_pipe
```

---

## Filtros disponibles

| Filtro          | Aplica a       | Descripción                              | Ejemplo                       |
|-----------------|----------------|------------------------------------------|-------------------------------|
| `--level`       | logs, alerts   | Nivel exacto                             | `--level ERROR`               |
| `--source`      | logs, alerts   | Fuente del log                           | `--source webapp`             |
| `--message`     | logs, alerts   | Búsqueda parcial en el mensaje           | `--message "timeout"`         |
| `--start-date`  | logs, alerts, stats | Desde esta fecha ISO              | `--start-date 2026-01-01`     |
| `--end-date`    | logs, alerts, stats | Hasta esta fecha ISO              | `--end-date 2026-12-31`       |
| `--limit`       | logs, alerts   | Máximo de resultados (default 100)       | `--limit 50`                  |
| `--offset`      | logs, alerts   | Desplazamiento para paginación           | `--offset 100`                |
| `--mailed`      | alerts         | Solo alertas notificadas por mail        | `--mailed`                    |
| `--not-mailed`  | alerts         | Solo alertas sin notificación por mail   | `--not-mailed`                |
| `--json`        | logs, alerts, stats | Salida JSON cruda                   | `--json`                      |

---

## Niveles de log

| Nivel      | Color    | Descripción                        |
|------------|----------|------------------------------------|
| `INFO`     | Azul     | Operación normal                   |
| `WARNING`  | Amarillo | Situación anómala no crítica       |
| `ERROR`    | Rojo     | Error que requiere atención        |
| `CRITICAL` | Magenta  | Falla grave, dispara alerta y mail |

---

## Fuentes soportadas

| Fuente       | Descripción                      |
|--------------|----------------------------------|
| `webapp`     | Servidor web / frontend          |
| `database`   | Base de datos                    |
| `api`        | Capa de API / gateway            |

---

## Para más información

- Instalación detallada: [`INSTALL.md`](INSTALL.md)
- Decisiones de diseño: [`INFO.md`](INFO.md)
- Mejoras pendientes: [`TODO.md`](TODO.md)
- Arquitectura: [`doc/propuesta_arquitectura_logs_analytics.md`](doc/propuesta_arquitectura_logs_analytics.md)
