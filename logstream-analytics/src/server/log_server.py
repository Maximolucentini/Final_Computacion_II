"""
Log Server - Servidor de ingesta de logs.

Recibe logs de múltiples clientes vía TCP (IPv4/IPv6) de forma asíncrona
y los encola en Redis para procesamiento posterior.

Toda la configuración se lee desde src.core.config (que carga el .env).
Los argumentos CLI pueden sobreescribir los valores del .env.
"""

import asyncio
import json
import socket
import redis
from datetime import datetime

from src.core.config import config
from .protocol import read_message, validate_log_entry


class LogServer:
    """
    Servidor asyncio que recibe logs y los encola en Redis.
    Soporta IPv4 e IPv6, múltiples clientes concurrentes.
    """

    def __init__(
        self,
        host: str = None,
        port: int = None,
        redis_host: str = None,
        redis_port: int = None
    ):
        """
        Args:
            host (str): IP para escuchar. Default: LOG_SERVER_HOST del .env.
            port (int): Puerto para escuchar. Default: LOG_SERVER_PORT del .env.
            redis_host (str): Host de Redis. Default: REDIS_HOST del .env.
            redis_port (int): Puerto de Redis. Default: REDIS_PORT del .env.
        """
        self.host       = host       or config.LOG_SERVER_HOST
        self.port       = port       or config.LOG_SERVER_PORT
        self.redis_host = redis_host or config.REDIS_HOST
        self.redis_port = redis_port or config.REDIS_PORT

        self.server       = None
        self.redis_client = None

        self.stats = {
            'total_received': 0,
            'total_enqueued': 0,
            'total_invalid':  0,
            'active_clients': 0,
            'started_at':     None
        }

    def connect_redis(self) -> bool:
        """Conectar a Redis. Retorna True si la conexión fue exitosa."""
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=config.REDIS_DB,
                decode_responses=False
            )
            self.redis_client.ping()
            print(f" Conectado a Redis: {self.redis_host}:{self.redis_port}")
            return True
        except redis.ConnectionError as e:
            print(f" No se pudo conectar a Redis: {e}")
            print(f"   Verificá que Redis esté corriendo: redis-server")
            return False

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Manejar conexión de un cliente TCP."""
        addr = writer.get_extra_info('peername')
        client_ip   = addr[0]
        client_port = addr[1]
        family      = "IPv6" if len(addr) == 4 else "IPv4"

        print(f"\n Cliente conectado ({family}): {client_ip}:{client_port}")
        self.stats['active_clients'] += 1

        try:
            while True:
                log = await read_message(reader)

                if log is None:
                    print(f" Cliente desconectado: {client_ip}:{client_port}")
                    break

                self.stats['total_received'] += 1

                is_valid, error_msg = validate_log_entry(log)
                if not is_valid:
                    self.stats['total_invalid'] += 1
                    print(f"  Log inválido de {client_ip}: {error_msg}")
                    continue

                log['ingested_at'] = datetime.now().isoformat()
                log['client_ip']   = client_ip

                try:
                    self.redis_client.rpush('log_queue', json.dumps(log))
                    self.stats['total_enqueued'] += 1

                    color = {
                        'INFO':     '\033[94m',
                        'WARNING':  '\033[93m',
                        'ERROR':    '\033[91m',
                        'CRITICAL': '\033[95m'
                    }.get(log['level'], '')
                    reset = '\033[0m'

                    print(
                        f" {color}[{log['level']:8s}]{reset} "
                        f"{log['source']:10s} | {log['message'][:60]}"
                    )

                    if self.stats['total_received'] % 100 == 0:
                        self.print_stats()

                except redis.RedisError as e:
                    print(f"Error al encolar en Redis: {e}")

        except asyncio.CancelledError:
            print(f" Cancelando conexión de {client_ip}:{client_port}")
        except Exception as e:
            print(f" Error manejando cliente {client_ip}:{client_port}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.stats['active_clients'] -= 1
            writer.close()
            await writer.wait_closed()

    def print_stats(self):
        """Imprimir estadísticas actuales."""
        print(f"\n Estadísticas:")
        print(f"   Recibidos:       {self.stats['total_received']}")
        print(f"   Encolados:       {self.stats['total_enqueued']}")
        print(f"   Inválidos:       {self.stats['total_invalid']}")
        print(f"   Clientes activos:{self.stats['active_clients']}")

        if self.stats['started_at']:
            elapsed = (datetime.now() - self.stats['started_at']).total_seconds()
            if elapsed > 0:
                rate = self.stats['total_received'] / elapsed
                print(f"   Rate promedio:   {rate:.2f} logs/seg")
        print()

    async def start(self):
        """Iniciar servidor con soporte IPv4 e IPv6."""
        if not self.connect_redis():
            return

        servers = []

        # Servidor IPv6
        try:
            server_v6 = await asyncio.start_server(
                self.handle_client,
                '::',
                self.port,
                family=socket.AF_INET6
            )
            servers.append(server_v6)
            print(f" Servidor IPv6 iniciado en [::]:{self.port}")
        except Exception as e:
            print(f"  IPv6 no disponible: {e}")

        # Servidor IPv4
        try:
            server_v4 = await asyncio.start_server(
                self.handle_client,
                '0.0.0.0',
                self.port,
                family=socket.AF_INET
            )
            servers.append(server_v4)
            print(f" Servidor IPv4 iniciado en 0.0.0.0:{self.port}")
        except Exception as e:
            print(f"  IPv4 no disponible: {e}")

        if not servers:
            print(" No se pudo iniciar ningún servidor")
            return

        print("\n" + "="*60)
        print(" Log Server iniciado")
        print("="*60)
        print(f" Escuchando en puerto: {self.port}")
        print(f" Redis:  {self.redis_host}:{self.redis_port}")
        print(f" Cola:   log_queue")
        print("\n Esperando conexiones de Log Producers...")
        print("   Presioná Ctrl+C para detener\n")
        print("="*60 + "\n")

        self.stats['started_at'] = datetime.now()

        try:
            await asyncio.gather(*[s.serve_forever() for s in servers])
        except KeyboardInterrupt:
            print("\n\n Deteniendo servidor...")
        finally:
            for s in servers:
                s.close()
                await s.wait_closed()
            await self.stop()

    async def stop(self):
        """Detener servidor y cerrar conexiones."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()

        if self.redis_client:
            self.redis_client.close()

        print("\n Estadísticas finales:")
        self.print_stats()
        print(" Servidor detenido")
