# Propuesta Final — LogStream Analytics 
**Carrera:** Ingeniería Informática  
**Materia:** Computacion II 
**Estudiante:** Maximo Lucentini  
**Fecha:** ...

---

# Propuesta de Proyecto Final — LogStream Analytics 


## 1) Título del proyecto
**LogStream Analytics: Sistema distribuido de monitoreo y análisis de logs**

## 2) Problema que resuelve
En muchos sistemas, los logs se generan en varios servicios o máquinas distintas. Eso dificulta detectar errores críticos a tiempo, centralizar la información y consultar el historial de eventos de manera ordenada.

**LogStream Analytics** centraliza la recepción de logs, los procesa de forma desacoplada y paralela, genera alertas cuando detecta eventos importantes y permite consultar logs, alertas y estadísticas desde una interfaz de consola.

## 3) Objetivo general
Diseñar e implementar un sistema CLI-servidor para ingesta, procesamiento, alerta y consulta de logs, aplicando sockets TCP, asincronismo de I/O, colas distribuidas, procesamiento en paralelo, mecanismos de IPC, sincronización y persistencia en base de datos.

## 4) Objetivos específicos
1. Recibir logs desde múltiples clientes TCP de forma concurrente usando `asyncio`.
2. Desacoplar la ingesta del procesamiento mediante Redis.
3. Convertir los logs recibidos en tareas individuales de Celery.
4. Procesar logs en paralelo mediante workers Celery.
5. Persistir logs y alertas en SQLite.
6. Generar alertas mediante un mecanismo de IPC local usando FIFO.
7. Permitir consultas históricas mediante Query Engine TCP y Query Client CLI.
8. Centralizar configuración con `.env` y permitir sobrescritura por argumentos de consola.

## 5) Alcance
Incluye:

- Producers CLI que generan logs simulados.
- Log Server TCP asincrónico con `asyncio`.
- Redis como cola de logs, broker de Celery y lock distribuido.
- Script `consume_logs.py` como puente entre `log_queue` y Celery.
- Workers Celery para procesamiento paralelo.
- SQLite como base de datos local.
- FIFO nombrado para comunicación entre workers y Alert Manager.
- Alert Manager para consola, base de datos y mail.
- Query Engine TCP asincrónico y Query Client CLI.
- Filtros, paginado y salida JSON en consultas.

Fuera de alcance inicial:

- Dashboard web.
- Autenticación de usuarios.
- Correlación compleja de eventos.
- Despliegue distribuido real con PostgreSQL.

---

# Arquitectura del sistema

## 1) Componentes principales

### 1. Log Producer / Client
Cliente de consola que simula servicios generadores de logs, como `webapp`, `database` o `api`.

Funciones:

- Genera logs en formato JSON.
- Permite configurar fuente, tasa de envío, probabilidad de errores y probabilidad de críticos.
- Se conecta por socket TCP al Log Server.
- Envía cada log usando el protocolo `[4 bytes de longitud][JSON]`.

### 2. Log Server
Servidor TCP de ingesta implementado con `asyncio`.

Funciones:

- Escucha conexiones de múltiples producers, por defecto en el puerto `9000`.
- Maneja clientes concurrentes mediante coroutines y event loop.
- Recibe logs por socket TCP.
- Valida el formato básico del log.
- Agrega metadatos como `ingested_at` y `client_ip`.
- Encola el log crudo en Redis usando la cola `log_queue`.

Justificación:

- Se usa `asyncio` porque esta parte es I/O-bound: espera datos por red y encola en Redis, sin hacer procesamiento pesado de CPU.
- Evita crear un thread por cliente.

### 3. Redis
Redis cumple tres roles en el proyecto:

1. **Cola de logs crudos:** `log_queue`, donde el Log Server deja los logs recibidos.
2. **Broker de Celery:** cola `log_processing`, donde Celery guarda tareas pendientes para los workers.
3. **Lock distribuido:** `db_write_lock`, usado para ordenar escrituras concurrentes sobre SQLite.

Redis no procesa los logs; funciona como intermediario de comunicación y sincronización.

### 4. consume_logs.py
Script intermedio entre Redis y Celery.

Funciones:

- Lee logs desde `log_queue` usando Redis.
- Toma logs en lotes configurables con `--batch-size`.
- Por cada log llama a `process_log_task.delay(log_json)`.
- Convierte cada log en una tarea individual de Celery.

Justificación:

- Desacopla el Log Server del procesamiento.
- Mantiene liviano el event loop del servidor.
- Permite controlar el ritmo de despacho hacia los workers.

### 5. Workers Celery
Procesos encargados de procesar los logs.

Funciones:

- Consumen tareas desde la cola Celery `log_processing`.
- Parsean el JSON recibido.
- Insertan el log en SQLite.
- Si el nivel del log está dentro de los niveles de alerta, escriben el evento en el FIFO.
- Pueden reintentar tareas ante errores.

Justificación:

- Celery permite procesamiento paralelo mediante workers.
- Con `--pool=prefork`, Celery usa procesos separados, permitiendo paralelismo real y separación del servidor principal.

### 6. SQLite
Base de datos local del sistema.

Funciones:

- Guarda los logs procesados en la tabla `logs`.
- Guarda las alertas en la tabla `alerts`.
- Permite consultas históricas desde el Query Engine.

Justificación:

- SQLite es simple, local y fácil de ejecutar para una demo académica.
- Como usa un archivo local, se protege la escritura concurrente con un lock distribuido en Redis.

### 7. FIFO / Named Pipe
Mecanismo de IPC local usado para alertas.

Funciones:

- Los workers escriben alertas en `data/alert_pipe`.
- El Alert Manager lee desde ese FIFO.
- Permite comunicar procesos independientes dentro de la misma máquina.

Justificación:

- Se usa como mecanismo de IPC del proyecto.
- Desacopla la detección de alertas del manejo de alertas.

### 8. Alert Manager
Proceso independiente que consume alertas desde el FIFO.

Funciones:

- Lee alertas desde `data/alert_pipe`.
- Muestra alertas por consola.
- Guarda alertas en la tabla `alerts`.
- Puede enviar mail para alertas críticas si el mail está habilitado.
- Permite desactivar consola, DB o mail con argumentos de línea de comandos.

### 9. Query Engine
Servidor TCP de consultas implementado con `asyncio`.

Funciones:

- Escucha consultas del Query Client, por defecto en el puerto `9001`.
- Recibe requests JSON con comando y filtros.
- Valida comandos y filtros permitidos.
- Ejecuta consultas sobre SQLite.
- Devuelve respuestas JSON al cliente.

Comandos principales:

- `logs`
- `alerts`
- `stats`

Justificación:

- Se usa `asyncio` porque el Query Engine también es un servidor de red I/O-bound.
- Puede atender varios clientes de consulta sin crear un thread por conexión.

### 10. Query Client
Cliente CLI para consultar la información persistida.

Funciones:

- Permite consultar logs, alertas y estadísticas.
- Arma un JSON con el comando y los filtros.
- Se conecta por TCP al Query Engine.
- Muestra la respuesta como tabla o JSON.

---

# Flujo end-to-end

## A) Flujo de ingesta y procesamiento de logs

1. El usuario ejecuta un Log Producer desde consola.
2. El Producer genera un log JSON.
3. El Producer se conecta por TCP al Log Server.
4. El Producer envía el mensaje usando el protocolo `[4 bytes length][JSON]`.
5. El Log Server recibe el log mediante `asyncio`.
6. El Log Server valida el formato básico.
7. Si el log es inválido, lo descarta y aumenta el contador de inválidos.
8. Si el log es válido, agrega `ingested_at` y `client_ip`.
9. El Log Server encola el log crudo en Redis, en `log_queue`.
10. `consume_logs.py` toma logs desde `log_queue`.
11. Por cada log, `consume_logs.py` crea una tarea Celery con `process_log_task.delay(log_json)`.
12. Celery guarda la tarea en Redis, dentro de la cola `log_processing`.
13. Un worker Celery toma la tarea.
14. El worker parsea el JSON.
15. El worker adquiere el lock distribuido de Redis para escribir en SQLite.
16. El worker guarda el log en la tabla `logs`.
17. Si el nivel es `ERROR` o `CRITICAL`, el worker escribe la alerta en el FIFO `data/alert_pipe`.
18. El Alert Manager lee la alerta desde el FIFO.
19. El Alert Manager muestra la alerta por consola, la guarda en la tabla `alerts` y, si corresponde, envía mail.

## B) Flujo de consulta

1. El usuario ejecuta una consulta desde el Query Client.
2. El Query Client parsea los argumentos de consola.
3. El Query Client arma un JSON con `command` y `filters`.
4. El Query Client se conecta por TCP al Query Engine.
5. El Query Engine recibe el JSON mediante el mismo protocolo `[4 bytes length][JSON]`.
6. El Query Engine valida el comando y los filtros.
7. Según el comando, llama a funciones específicas de base de datos:
   - `query_logs` para logs.
   - `query_alerts` para alertas.
   - `get_stats` para estadísticas.
8. La función de base de datos arma consultas SQL parametrizadas contra SQLite.
9. SQLite devuelve los resultados.
10. El Query Engine arma una respuesta JSON.
11. El Query Client recibe la respuesta y la muestra por consola.

---

## 3. Arquitectura General ()

                  ┌────────────────────────────┐
                  │      LOG PRODUCERS CLI      │
                  │ webapp / database / api     │
                  └──────────────┬─────────────┘
                                 │
                                 │ TCP [4 bytes len][JSON]
                                 ▼
                  ┌────────────────────────────┐
                  │       LOG SERVER            │
                  │       asyncio TCP           │
                  │       puerto 9000           │
                  │----------------------------│
                  │ - acepta múltiples clientes │
                  │ - valida formato básico     │
                  │ - agrega ingested_at/IP     │
                  └──────────────┬─────────────┘
                                 │
                                 │ RPUSH log_queue
                                 ▼
                  ┌────────────────────────────┐
                  │            REDIS            │
                  │----------------------------│
                  │ - log_queue                 │
                  │ - broker Celery             │
                  │ - db_write_lock             │
                  └──────────────┬─────────────┘
                                 │
                                 │ LPOP log_queue
                                 ▼
                  ┌────────────────────────────┐
                  │      consume_logs.py        │
                  │----------------------------│
                  │ - toma logs de Redis        │
                  │ - los manda a Celery        │
                  │ - crea tareas individuales  │
                  └──────────────┬─────────────┘
                                 │
                                 │ process_log_task.delay(log)
                                 ▼
                  ┌────────────────────────────┐
                  │       CELERY BROKER         │
                  │       Redis / log_processing│
                  └──────────────┬─────────────┘
                                 │
                                 │ tareas
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
       ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
       │ Worker 1     │   │ Worker 2     │   │ Worker N     │
       │ Celery       │   │ Celery       │   │ Celery       │
       │--------------│   │--------------│   │--------------│
       │ parsea log   │   │ parsea log   │   │ parsea log   │
       │ guarda DB    │   │ guarda DB    │   │ guarda DB    │
       │ detecta alert│   │ detecta alert│   │ detecta alert│
       └──────┬───────┘   └──────┬───────┘   └──────┬───────┘
              │                  │                  │
              └──────────┬───────┴──────────┬───────┘
                         │                  │
                         │ write logs       │ si ERROR/CRITICAL
                         ▼                  ▼
              ┌─────────────────┐   ┌──────────────────────┐
              │ SQLite DB        │   │ FIFO / data/alert_pipe│
              │ tabla logs       │   │ IPC local             │
              │ tabla alerts     │   └──────────┬───────────┘
              └────────┬────────┘              │
                       ▲                       │ lee alertas
                       │                       ▼
                       │            ┌──────────────────────┐
                       │            │    ALERT MANAGER      │
                       │            │----------------------│
                       │            │ - consola             │
                       │            │ - guarda alertas DB   │
                       │            │ - mail si CRITICAL    │
                       │            └──────────────────────┘
                       │
                       │ SQLite READ
                       │
              ┌────────┴─────────┐
              │   QUERY ENGINE    │
              │   asyncio TCP     │
              │   puerto 9001     │
              │------------------│
              │ logs/alerts/stats │
              │ filtros/paginado  │
              └────────┬─────────┘
                       │
                       │ TCP [4 bytes len][JSON]
                       ▼
              ┌──────────────────┐
              │  QUERY CLIENT CLI│
              └──────────────────┘
