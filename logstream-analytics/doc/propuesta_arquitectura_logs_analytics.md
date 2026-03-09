# Propuesta Final — LogStream Analytics ()
**Carrera:** Ingeniería Informática  
**Materia:** Computacion II 
**Estudiante:** Maximo Lucentini  
**Fecha:** ...

---

# Propuesta de Proyecto Final — LogStream Analytics ()


## 1) Título del proyecto
**LogStream Analytics (): Sistema distribuido de monitoreo y análisis de logs**

## 2) Problema que resuelve
En muchos sistemas, los logs están dispersos entre servicios y máquinas.  
Eso dificulta detectar errores críticos a tiempo y hacer análisis histórico sin trabajo manual.

**LogStream** centraliza eventos en tiempo real, los procesa de forma concurrente y permite:
- detectar alertas críticas,
- consultar histórico por filtros,
- y obtener métricas de salud del sistema.

## 3) Objetivo general
Diseñar e implementar un sistema distribuido CLI-server para ingestión, procesamiento, alerta y consulta de logs, aplicando asincronismo, paralelismo e IPC.

## 4) Objetivos específicos
1. Recibir logs desde múltiples clientes TCP de forma asíncrona.
2. Desacoplar ingesta/procesamiento con cola distribuida.
3. Procesar logs en paralelo con workers.
4. Detectar eventos críticos y emitir alertas por IPC.
5. Persistir resultados para consultas históricas.
6. Exponer consultas por un servidor TCP + cliente CLI.

## 5) Alcance
### Alcance  
- Ingesta TCP asíncrona multicliente.
- Redis + Celery para cola distribuida y workers.
- Persistencia en DB (SQLite o PostgreSQL).
- Alertas mínimas (2 reglas).
- Query Engine TCP con cliente CLI y filtros.
- Manejo básico de errores, timeouts y cierre limpio.

### Fuera de alcance inicial (extensiones)
- Dashboard web.
- Correlación compleja multi-fuente.



## 7) Resultado esperado
flujo completo:
**cliente log -> servidor ingestión -> cola -> worker -> DB + alerta -> consulta CLI**

---

# Arquitectura — LogStream Analytics ()

## 1) Componentes principales

1. **Log Producer (CLI simulador)**
   - Envía logs JSON por TCP al servidor de ingesta.
   - Permite configurar ritmo, severidad y fuente.

2. **Log Server (Ingesta, asyncio)**
   - Puerto sugerido: `9000`.
   - Maneja múltiples conexiones concurrentes (`asyncio.start_server`).
   - Valida formato básico y publica tareas en Redis.

3. **Redis (Broker de mensajes)**
   - Cola distribuida para desacoplar ingreso y procesamiento.

4. **Workers Celery**
   - Consumen tareas en paralelo.
   - Parsean, normalizan, clasifican severidad.
   - Guardan en DB y disparan alerta si corresponde.

5. **Alert Manager (IPC por FIFO)**
   - Lee pipe nombrado (ej: `/tmp/alert_pipe`).
   - Registra/imprime alertas críticas.
   - Permite desacoplar alertas del worker.

6. **Base de Datos**
   - Guarda logs procesados y alertas.
   - Base inicial sugerida: SQLite (rápido para ).

7. **Query Engine (asyncio) + Query Client CLI**
   - Puerto sugerido: `9001`.
   - Recibe filtros de consulta y responde resultados.

---

## 2) Flujo de datos end-to-end

1. Productor envía log JSON a Log Server.
2. Log Server encola tarea en Redis.
3. Worker Celery toma tarea y procesa.
4. Worker persiste resultado en DB.
5. Si regla crítica se cumple, worker escribe alerta en FIFO.
6. Alert Manager consume FIFO y notifica.
7. Query Client consulta histórico al Query Engine por TCP.

---

## 3. Arquitectura General ()

[CLIENTES - LOG PRODUCERS / SIMULADORES]
  |  |  |
  Producer 1 (webapp)  \
  Producer 2 (db)       } ---> TCP --->+
  Producer 3 (api)     /              | 
                                      v
                          +---------------------------+
                          |        LOG SERVER         |
                          |     (asyncio TCP)         |
                          |        Puerto --          |
                          |---------------------------|
                          | - Valida formato básico   |
                          | - Contador simple (logs/s)|
                          |   (: métrica)             |
                          +------------+--------------+
                                       |
                                       | Encola tarea ()
                                       v
                          +---------------------------+
                          |       REDIS BROKER        |
                          |---------------------------|
                          | : Cola "tasks"            |
                          | Pub/Sub                   |
                          +------------+--------------+
                                       |
                                       | Workers consumen de la cola
                                       v
        +------------------+   +------------------+    +------------------+
        |    Worker 1      |   |    Worker 2      |    |    Worker N      |
        |    (Celery)      |   |    (Celery)      |    |    (Celery)      |
        |------------------|   |------------------|    |------------------|
        | - Parse          |   | - Parse          |    | - Parse          |
        | - Valida         |   | - Valida         |    | - Valida         |
        | - Guarda en DB   |   | - Guarda en DB   |    | - Guarda en DB   |
        | - Reglas críticas|   | - Reglas críticas|    | - Reglas críticas|
        +---------+--------+   +---------+--------+    +---------+--------+
                  \                 |                       /
                   \                |                      /
                    \               |                     /
                     \              |                    /
                      \             |                   /
                       +------------+------------------+
                                    |
                        Si regla crítica se cumple ()
                                    |
                                    v
                          +---------------------------+
                          |      NAMED PIPE (FIFO)    |
                          |      /tmp/alert_pipe      |
                          |        (IPC )             |
                          +------------+--------------+
                                       |
                                       | Alert Manager lee (no bloqueante)
                                       v
                          +---------------------------+
                          |       ALERT MANAGER       |
                          |         (Proceso)         |
                          |---------------------------|
                          | - Clasifica               |
                          | - Notifica (stdout/log)   |
                          | - Guarda alerta en DB     |
                          +------------+--------------+

                          +---------------------------+
                          |      BASE DE DATOS        |
                          |---------------------------|
                          | : tablas logs, alerts     |
                          | stats/agregados           |
                          | (SQLite  )                |
                          +------------+--------------+
                                       ^
                                       | Query Engine lee
                                       |
                          +------------+--------------+
                          |       QUERY ENGINE        |
                          |     (asyncio TCP)         |
                          |        Puerto 9001        |
                          |---------------------------|
                          | - Filtros (SQL)           |
                          | - Paginación              |
                          +------------+--------------+
                                       |
                                       v
                          +---------------------------+
                          |      QUERY CLIENT (CLI)   |
                          +---------------------------+

```

