# INFO.md — Decisiones de diseño

Este documento resume las decisiones de arquitectura tomadas para balancear simplicidad de implementación, concurrencia y desacoplamiento entre componentes.

---

## 1. Protocolo TCP: [4 bytes length][JSON payload]

**Decisión:** Todo el transporte TCP (Log Server y Query Engine) usa un
protocolo de longitud prefijada: 4 bytes big-endian que indican el tamaño
del payload JSON que sigue.

**Justificación:** TCP es un protocolo de stream, no de mensajes. Sin un
delimitador o longitud explícita, no hay forma de saber dónde termina un
mensaje y empieza el siguiente. Alternativas consideradas:

- *Newline como delimitador:* simple pero rompe si el JSON tiene saltos de
  línea embebidos o si un mensaje llega partido en varios segmentos TCP.
- *Longitud prefijada:* desacopla completamente el transporte del contenido.
  Permite mensajes arbitrariamente grandes y es determinista. Se eligió esta
  opción.

El mismo protocolo se reutiliza en ambos servidores (`log_server.py` y
`query_engine.py`) a través del módulo `src/server/protocol.py`, evitando
duplicación de código.

---

## 2. Asincronismo con asyncio (Log Server y Query Engine)

**Decisión:** Los servidores TCP de ingesta (puerto 9000) y consultas
(puerto 9001) usan `asyncio.start_server` para manejar múltiples clientes
concurrentes.

**Justificación:** Ambos servidores son intensivos en I/O, no en CPU:
el Log Server solo recibe, valida y encola; el Query Engine recibe, consulta
la DB y devuelve. Para I/O concurrente, el modelo de un único hilo con
event loop (asyncio) es más eficiente que crear un thread o proceso por
cliente, ya que evita el overhead de context switching y el consumo de
memoria de múltiples threads. Se prefirió asyncio sobre threads porque
el GIL de Python no representa una limitación aquí: el cuello de botella
es la red, no la CPU.

---

## 3. Cola distribuida con Redis + Celery

**Decisión:** La ingesta y el procesamiento están desacoplados mediante
una cola en Redis. El Log Server publica mensajes con `RPUSH` en
`log_queue`, y un proceso consumidor (`consume_logs.py`) los toma con
`LPOP` y los despacha como tareas Celery.

**Justificación:** El desacoplamiento resuelve tres problemas:

1. **Backpressure:** si los workers no dan abasto, los mensajes se acumulan
   en Redis sin bloquear al Log Server ni a los productores.
2. **Paralelismo real:** Celery lanza múltiples workers como procesos
   separados, eludiendo el GIL. Cada worker procesa una tarea en paralelo,
   lo que es adecuado porque el procesamiento incluye escritura en SQLite
   (I/O de disco) y lógica de clasificación (CPU).
3. **Resiliencia:** si un worker falla, Celery reintenta la tarea
   automáticamente (hasta 3 veces con `max_retries=3`).

Se eligió Redis como broker y no RabbitMQ porque ya era una dependencia
del proyecto (se usa también para el lock distribuido de SQLite), reduciendo
la cantidad de servicios externos necesarios.

---

## 4. IPC con FIFO nombrado (Named Pipe)

**Decisión:** Los workers Celery escriben alertas en un FIFO nombrado
(`/data/alert_pipe`) en modo no bloqueante (`O_NONBLOCK`). El Alert Manager
corre como proceso independiente y lee del mismo FIFO.

**Justificación:** El FIFO desacopla el procesamiento de logs del manejo de
alertas. Alternativas consideradas:

- *Socket Unix:* más flexible pero requiere gestión de conexiones.
- *Señales (signals):* solo sirven para notificaciones simples, no para
  pasar datos estructurados.
- *Redis Pub/Sub:* agregaría una dependencia extra de red para algo que
  ocurre en la misma máquina.

El FIFO es la opción más simple y directa para comunicación entre procesos
en la misma máquina. Se usa `O_WRONLY | O_NONBLOCK` en el writer para no
bloquear al worker si el Alert Manager no está corriendo, y
`O_RDONLY | O_NONBLOCK` en el reader para que el Alert Manager pueda hacer
polling sin bloquearse.

---

## 5. Lock distribuido en Redis para escrituras SQLite

**Decisión:** Antes de cada escritura en SQLite, los workers adquieren
un lock distribuido en Redis (`redis.lock('db_write_lock')`).

**Justificación:** SQLite soporta múltiples lectores concurrentes pero solo
un escritor a la vez. Con varios workers Celery escribiendo en paralelo,
sin coordinación se producen errores de `database is locked`. El lock de
Redis garantiza exclusión mutua entre procesos (algo que un `threading.Lock`
no puede hacer, ya que solo funciona dentro de un proceso). Se eligió WAL
mode (`PRAGMA journal_mode=WAL`) en SQLite para que las lecturas no bloqueen
a los escritores y viceversa, mejorando el throughput general.

---

## 6. Configuración centralizada en config.py + .env

**Decisión:** Todas las variables de configuración se leen desde un único
archivo `.env` a través del módulo `src/core/config.py`, que expone un
singleton `config`. Ningún módulo hardcodea valores ni llama a `os.getenv`
directamente.

**Justificación:** Centralizar la configuración tiene tres ventajas:

1. **Un solo lugar para cambiar valores:** cambiar el puerto del servidor,
   la ruta de la DB o las credenciales SMTP no requiere tocar código.
2. **El `.env` nunca se commitea** (está en `.gitignore`); el `.env.example`
   documenta todas las variables disponibles.
3. **Los argumentos CLI sobreescriben al `.env`** en todos los componentes:
   los defaults de argparse leen de `config`, pero el usuario puede pasarlos
   explícitamente. Esto permite levantar múltiples instancias con distintas
   configuraciones sin modificar el archivo.

---

## 7. Alert Manager como proceso independiente

**Decisión:** El Alert Manager es un proceso separado con su propio
`__main__.py`, no un hilo dentro del worker ni del servidor.

**Justificación:** El desacoplamiento permite que el Alert Manager falle
o se reinicie sin afectar al pipeline de ingesta. También permite
configurarlo de forma independiente (por ejemplo, deshabilitar el mail con
`--no-mail` para una ejecución puntual sin tocar el `.env`). Al ser un
proceso separado, puede correr en una máquina diferente siempre que tenga
acceso al mismo FIFO (en un sistema de archivos compartido) o pueda ser
reemplazado por otro mecanismo de IPC.

---

## 8. Modelo de datos SQLite

**Decisión:** Tres tablas: `logs` (todos los logs procesados), `alerts`
(subconjunto de logs que dispararon una alerta), `stats` (reservada para
agregados futuros). Se usaron índices en `level`, `source`, `timestamp`
y `created_at`.

**Justificación:** Se eligió SQLite por su simplicidad operativa: no requiere
un servidor separado, el archivo es portable y el rendimiento es suficiente
para el volumen esperado en un entorno académico/demo. Los índices en los
campos más consultados (level, source, timestamp) evitan full table scans
en las queries del Query Engine. La tabla `alerts` es separada de `logs`
porque tiene campos propios (`notified_by_mail`, `mail_sent_at`) y permite
consultas específicas sobre alertas sin filtrar toda la tabla de logs.

---

## 9. Soporte dual IPv4/IPv6

**Decisión:** Los servidores TCP detectan dinámicamente las familias de red disponibles mediante socket.getaddrinfo() y levantan sockets de escucha según el entorno. Si la máquina soporta IPv4 e IPv6, se inician ambos; si solo soporta una de las dos, se inicia únicamente esa. Los clientes siguen usando socket.getaddrinfo() con AF_UNSPEC para conectarse automáticamente por la familia disponible.

**Justificación:** Usar `::` solo no es suficiente en todos los sistemas
operativos: en algunos Linux la opción `IPV6_V6ONLY` está activada por
defecto y el socket IPv6 no acepta conexiones IPv4. Levantar ambos sockets
explícitamente garantiza compatibilidad universal sin depender de la
configuración del SO.
