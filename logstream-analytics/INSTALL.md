# INSTALL.md — LogStream Analytics

Instrucciones para clonar, instalar y lanzar el sistema.

---

## Requisitos previos

- Python 3.11+
- Redis 7+
- Git

---

## 1. Clonar el repositorio

```bash
git clone <URL_DEL_REPOSITORIO>
cd logstream-analytics
```

---

## 2. Crear entorno virtual e instalar dependencias

```bash
python -m venv venv
source venv/bin/activate        # Linux / macOS
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

### `requirements.txt` completo

```
redis==5.0.1
celery==5.3.4
python-dotenv==1.0.0
psutil==5.9.6
```

---

## 3. Configurar variables de entorno

```bash
cp .env.example .env
```

Editá `.env` con tus valores. Las variables mínimas para levantar el sistema son:

```env
# Redis (ajustar si Redis no corre en localhost)
REDIS_HOST=localhost
REDIS_PORT=6379

# Base de datos
DB_PATH=data/logstream.db

# Puertos de los servidores
LOG_SERVER_PORT=9000
QUERY_ENGINE_PORT=9001

# Alert Manager
ALERT_LEVELS=ERROR,CRITICAL
ALERT_STORE_IN_DB=true
ALERT_PRINT_TO_CONSOLE=true
ALERT_EMAIL_ENABLED=false
```

Para habilitar notificaciones por mail, completar también:

```env
ALERT_EMAIL_ENABLED=true
ALERT_MAIL_LEVELS=CRITICAL
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USER=tu_usuario@gmail.com
SMTP_PASSWORD=tu_app_password
ALERT_MAIL_FROM=tu_usuario@gmail.com
ALERT_MAIL_TO=destinatario@example.com
```

> **Nota Gmail:** usá una *App Password* (no tu contraseña normal).  
> Menú Google → Seguridad → Verificación en dos pasos → Contraseñas de aplicación.

---

## 4. Inicializar la base de datos

```bash
python scripts/init_db.py
```

Esto crea el archivo SQLite en `data/logstream.db` con las tablas `logs`, `alerts` y `stats`.

---

## 5. Levantar Redis

Si Redis no está corriendo como servicio del sistema:

```bash
redis-server
```

Verificar que responde:

```bash
redis-cli ping
# esperado: PONG
```

---

## 6. Lanzar los componentes

Cada componente corre en una terminal separada.

### Terminal 1 — Log Server (ingesta)

```bash
python -m src.server
```

Acepta conexiones de Log Producers en el puerto `LOG_SERVER_PORT` (default 9000).

### Terminal 2 — Workers Celery

```bash
celery -A src.workers.celery_config worker --loglevel=info -Q log_processing
```

Para lanzar múltiples workers en paralelo:

```bash
celery -A src.workers.celery_config worker --loglevel=info -Q log_processing --concurrency=4
```

### Terminal 3 — Consumidor Redis → Celery

```bash
python scripts/consume_logs.py
```

Puente entre la cola Redis (`log_queue`) y las tareas Celery.

### Terminal 4 — Alert Manager

```bash
python -m src.alerts
```

Lee el FIFO nombrado y despacha alertas a consola, DB y/o mail.

### Terminal 5 — Query Engine

```bash
python -m src.query engine
```

Servidor TCP de consultas históricas en el puerto `QUERY_ENGINE_PORT` (default 9001).

### Terminal 6 — Log Producer (simulador de clientes)

```bash
# Fuente webapp a 5 logs/seg
python -m src.clients --source webapp --rate 5

# Fuente database con más errores
python -m src.clients --source database --rate 10 --error-rate 0.2

# Fuente api desde otra máquina
python -m src.clients --source api --server 192.168.1.100:9000
```

---

## 7. Consultar datos con el Query Client

```bash
# Últimos 100 logs
python -m src.query logs

# Logs de nivel ERROR de webapp
python -m src.query logs --level ERROR --source webapp

# Buscar por texto en el mensaje
python -m src.query logs --message "timeout"

# Alertas críticas no notificadas por mail
python -m src.query alerts --level CRITICAL --not-mailed

# Estadísticas globales
python -m src.query stats

# Salida JSON cruda
python -m src.query logs --json
```

---

## 8. Argumentos CLI disponibles (resumen)

| Componente       | Comando de inicio                              | Argumento clave              |
|------------------|------------------------------------------------|------------------------------|
| Log Server       | `python -m src.server`                         | `--port`, `--redis-host`     |
| Log Producer     | `python -m src.clients --source <src>`         | `--rate`, `--error-rate`     |
| Alert Manager    | `python -m src.alerts`                         | `--fifo`, `--no-mail`        |
| Query Engine     | `python -m src.query engine`                   | `--host`, `--port`           |
| Query Client     | `python -m src.query logs\|alerts\|stats`      | `--level`, `--source`, `--json` |

Cualquier componente acepta `--help` para ver todos sus argumentos.

---

## Estructura del proyecto

```
logstream-analytics/
├── .env                    # Variables de entorno (NO commitear)
├── .env.example            # Plantilla de variables (sí commitear)
├── requirements.txt
├── data/                   # Generado en runtime (DB + FIFO)
├── doc/                    # Documentación de arquitectura
├── scripts/
│   ├── init_db.py
│   ├── consume_logs.py
│   └── test_db.py
└── src/
    ├── clients/            # Log Producer
    ├── server/             # Log Server (asyncio)
    ├── workers/            # Celery tasks
    ├── alerts/             # Alert Manager + Mailer
    ├── query/              # Query Engine + Query Client
    └── core/               # Config, DB, Redis client
```
