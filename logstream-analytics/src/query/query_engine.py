# src/query/query_engine.py
"""
Query Engine — servidor asyncio TCP para consultas históricas.

Escucha en el puerto configurado (default 9001), recibe un JSON de consulta
del Query Client, ejecuta contra la DB SQLite y devuelve los resultados
usando el mismo protocolo que el Log Server: [4 bytes length][JSON payload].

"""

import asyncio
import json
import socket
from datetime import datetime

from src.core.config import config
from src.core.db import query_logs, query_alerts, get_stats
from src.server.protocol import read_message, send_message


# Comandos válidos
VALID_COMMANDS = {'logs', 'alerts', 'stats'}

# Filtros válidos por comando
VALID_FILTERS = {
    'logs': {'source', 'level', 'message', 'start_date', 'end_date', 'limit', 'offset'},
    'alerts': {'source', 'level', 'message', 'start_date', 'end_date',
               'notified_by_mail', 'limit', 'offset'},
    'stats': {'start_date', 'end_date'},
}


class QueryEngine:
    """
    Servidor asyncio que atiende consultas históricas sobre la DB.

    Un cliente se conecta, envía un único request JSON, recibe
    la respuesta JSON y la conexión se cierra.
    """

    def __init__(self, host: str = None, port: int = None):
        """
        Args:
            host (str): IP para escuchar. Default: QUERY_ENGINE_HOST del .env.
            port (int): Puerto para escuchar. Default: QUERY_ENGINE_PORT del .env.
        """
        self.host = host or config.QUERY_ENGINE_HOST
        self.port = port or config.QUERY_ENGINE_PORT

        self.stats = {
            'total_queries':  0,
            'total_errors':   0,
            'active_clients': 0,
            'started_at':     None,
        }

    #  Validación de requests                                              

    def _validate_request(self, request: dict) -> tuple[bool, str]:
        """
        Validar el request recibido del cliente.

        Returns:
            (True, "") si es válido.
            (False, "mensaje de error") si no lo es.
        """
        if not isinstance(request, dict):
            return False, "El request debe ser un objeto JSON"

        command = request.get('command')
        if not command:
            return False, "Falta el campo 'command'"
        if command not in VALID_COMMANDS:
            return False, f"Comando inválido: '{command}'. Válidos: {sorted(VALID_COMMANDS)}"

        filters = request.get('filters', {})
        if not isinstance(filters, dict):
            return False, "El campo 'filters' debe ser un objeto JSON"

        unknown = set(filters.keys()) - VALID_FILTERS[command]
        if unknown:
            return False, f"Filtros desconocidos para '{command}': {sorted(unknown)}"

        # Validar tipos de filtros numéricos
        for field in ('limit', 'offset'):
            if field in filters:
                val = filters[field]
                if not isinstance(val, int) or val < 0:
                    return False, f"'{field}' debe ser un entero >= 0"

        if 'limit' in filters and filters['limit'] > 1000:
            return False, "El límite máximo es 1000 resultados por consulta"

        return True, ""

    #  Ejecución de consultas                                              

    def _execute(self, command: str, filters: dict) -> dict:
        """
        Ejecutar la consulta en la DB y retornar el dict de respuesta.

        Args:
            command (str): 'logs', 'alerts' o 'stats'.
            filters (dict): Filtros validados.

        Returns:
            dict: Respuesta lista para serializar como JSON.
        """
        if command == 'logs':
            results = query_logs(
                source=filters.get('source'),
                level=filters.get('level'),
                message=filters.get('message'),
                start_date=filters.get('start_date'),
                end_date=filters.get('end_date'),
                limit=filters.get('limit', 100),
                offset=filters.get('offset', 0),
            )
            return {
                'status':  'ok',
                'command': 'logs',
                'count':   len(results),
                'data':    results,
            }

        elif command == 'alerts':
            notified = filters.get('notified_by_mail')
            # El cliente manda bool o None
            if isinstance(notified, str):
                notified = notified.lower() == 'true'

            results = query_alerts(
                source=filters.get('source'),
                level=filters.get('level'),
                message=filters.get('message'),
                start_date=filters.get('start_date'),
                end_date=filters.get('end_date'),
                notified_by_mail=notified,
                limit=filters.get('limit', 100),
                offset=filters.get('offset', 0),
            )
            return {
                'status':  'ok',
                'command': 'alerts',
                'count':   len(results),
                'data':    results,
            }

        elif command == 'stats':
            data = get_stats(
                start_date=filters.get('start_date'),
                end_date=filters.get('end_date'),
            )
            return {
                'status':  'ok',
                'command': 'stats',
                'data':    data,
            }

    #  Handler de clientes                                                 

    async def handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ):
        """
        Manejar una conexión entrante.

        Flujo: leer request → validar → ejecutar → enviar response → cerrar.
        """
        addr = writer.get_extra_info('peername')
        client_ip   = addr[0]
        client_port = addr[1]
        family      = "IPv6" if len(addr) == 4 else "IPv4"

        self.stats['active_clients'] += 1
        print(f" Query Client conectado ({family}): {client_ip}:{client_port}")

        try:
            # Leer request
            request = await read_message(reader)

            if request is None:
                print(f" Cliente {client_ip} cerró conexión sin enviar request")
                return

            self.stats['total_queries'] += 1
            command = request.get('command', '?')
            filters = request.get('filters', {})
            print(f" Query [{command}] filtros={filters} desde {client_ip}")

            # Validar
            valid, error_msg = self._validate_request(request)
            if not valid:
                response = {
                    'status':  'error',
                    'command': command,
                    'error':   error_msg,
                }
                self.stats['total_errors'] += 1
                print(f" Request inválido: {error_msg}")
            else:
                # Ejecutar consulta
                try:
                    response = self._execute(command, filters)
                    count_info = f" → {response.get('count', '')} resultados"
                    print(f" Query [{command}] OK{count_info}")
                except Exception as e:
                    response = {
                        'status':  'error',
                        'command': command,
                        'error':   f"Error ejecutando consulta: {e}",
                    }
                    self.stats['total_errors'] += 1
                    print(f" Error en query [{command}]: {e}")

            # Enviar respuesta
            await send_message(writer, response)

        except Exception as e:
            print(f" Error inesperado con {client_ip}: {e}")
            import traceback
            traceback.print_exc()
            self.stats['total_errors'] += 1
        finally:
            self.stats['active_clients'] -= 1
            writer.close()
            await writer.wait_closed()

    def _detect_families(self) -> set:
        """
        Detectar qué familias de red (IPv4, IPv6) tiene disponibles
        esta máquina usando socket.getaddrinfo() en modo pasivo.

        Returns:
            set: Subconjunto de {socket.AF_INET, socket.AF_INET6}
        """
        families = set()
        try:
            results = socket.getaddrinfo(
                None,
                self.port,
                socket.AF_UNSPEC,
                socket.SOCK_STREAM,
                0,
                socket.AI_PASSIVE
            )
            for family, *_ in results:
                if family in (socket.AF_INET, socket.AF_INET6):
                    families.add(family)
        except socket.gaierror as e:
            print(f"  Advertencia al detectar familias de red: {e}")

        return families

    #  Start / stop                                                        

    async def start(self):
        """Iniciar el servidor detectando automáticamente IPv4/IPv6."""
        servers = []

        families = self._detect_families()

        if not families:
            print(" No se detectó ninguna familia de red disponible")
            return

        has_ipv4 = socket.AF_INET in families
        has_ipv6 = socket.AF_INET6 in families

        print(
            f" Familias detectadas: "
            f"{'IPv4 ' if has_ipv4 else ''}"
            f"{'IPv6' if has_ipv6 else ''}"
        )

        try:
            if has_ipv6:
                sv6 = await asyncio.start_server(
                    self.handle_client, '::', self.port,
                    family=socket.AF_INET6
                )
                servers.append(sv6)
                print(f" Query Engine IPv6 en [::]:{self.port}")
        except Exception as e:
            print(f"  IPv6 no disponible: {e}")

        try:
            if has_ipv4:
                sv4 = await asyncio.start_server(
                    self.handle_client, '0.0.0.0', self.port,
                    family=socket.AF_INET
                )
                servers.append(sv4)
                print(f" Query Engine IPv4 en 0.0.0.0:{self.port}")
        except Exception as e:
            print(f"  IPv4 no disponible: {e}")

        if not servers:
            print(" No se pudo iniciar el Query Engine")
            return

        print("\n" + "="*60)
        print(" Query Engine iniciado")
        print("="*60)
        print(f" Puerto:   {self.port}")
        print(f" Comandos: logs | alerts | stats")
        print("\n Esperando consultas del Query Client...")
        print("   Presioná Ctrl+C para detener\n")
        print("="*60 + "\n")

        self.stats['started_at'] = datetime.now()

        try:
            await asyncio.gather(*[s.serve_forever() for s in servers])
        except KeyboardInterrupt:
            print("\n\n Deteniendo Query Engine...")
        finally:
            for s in servers:
                s.close()
                await s.wait_closed()
            self._print_stats()
            print(" Query Engine detenido.")

    def _print_stats(self):
        """Imprimir estadísticas finales."""
        print(f"\n Estadísticas:")
        print(f"   Total queries:   {self.stats['total_queries']}")
        print(f"   Errores:         {self.stats['total_errors']}")
        if self.stats['started_at']:
            elapsed = (datetime.now() - self.stats['started_at']).total_seconds()
            print(f"   Uptime:          {elapsed:.0f}s")