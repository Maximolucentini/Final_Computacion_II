# src/query/query_client.py
"""
Query Client — cliente CLI para consultar el Query Engine por TCP.

Envía un request JSON al Query Engine y muestra los resultados
como tabla formateada (default) o JSON crudo (--json).

Subcomandos:
    logs    — consultar logs históricos
    alerts  — consultar alertas
    stats   — ver estadísticas agregadas

Uso:
    python -m src.query logs
    python -m src.query logs --level ERROR --source webapp
    python -m src.query logs --message "timeout" --limit 20
    python -m src.query alerts --level CRITICAL --json
    python -m src.query stats
    python -m src.query stats --start-date 2026-01-01
"""

import json
import socket
import struct
import sys
from typing import Any, Dict, List, Optional

from src.core.config import config


# Colores ANSI
_C = {
    'CRITICAL': '\033[95m',
    'ERROR':    '\033[91m',
    'WARNING':  '\033[93m',
    'INFO':     '\033[94m',
    'BOLD':     '\033[1m',
    'DIM':      '\033[2m',
    'GREEN':    '\033[92m',
    'RESET':    '\033[0m',
}


class QueryClientError(Exception):
    """Error de comunicación con el Query Engine."""
    pass


class QueryClient:
    """
    Cliente TCP que se conecta al Query Engine, envía un request
    y retorna la respuesta deserializada.
    """

    def __init__(self, host: str = None, port: int = None):
        self.host = host or config.QUERY_ENGINE_HOST
        self.port = port or config.QUERY_ENGINE_PORT

        # Normalizar host para conexión saliente
        # Si es '::' o '0.0.0.0' (bind address del server),
        # usar loopback apropiado para el cliente
        # El engine puede usar '::' o '0.0.0.0' como bind address (escucha en todo).
        # El cliente necesita una dirección de conexión concreta:
        # - 0.0.0.0 → 127.0.0.1 (loopback IPv4)
        # - ::      → ::1        (loopback IPv6)
        # Si QUERY_ENGINE_HOST tiene una IP real (ej: 192.168.1.100),
        # no entra en ningún if y se conecta directo, permite conexión remota.
        if self.host == '0.0.0.0':
            self.host = '127.0.0.1'
        elif self.host == '::':
            self.host = '::1'

    def _send_recv(self, request: dict) -> dict:
        """
        Conectar al engine, enviar request y recibir respuesta.
        Usa el mismo protocolo [4 bytes len][JSON payload].

        Args:
            request (dict): Request a enviar.

        Returns:
            dict: Respuesta del engine.

        Raises:
            QueryClientError: Si hay error de conexión o protocolo.
        """
        try:
            addr_info = socket.getaddrinfo(
                self.host, self.port,
                socket.AF_UNSPEC, socket.SOCK_STREAM
            )
        except socket.gaierror as e:
            raise QueryClientError(
                f"No se pudo resolver '{self.host}': {e}"
            )

        last_err = None
        for family, socktype, proto, _, sockaddr in addr_info:
            try:
                sock = socket.socket(family, socktype, proto)
                sock.settimeout(10)
                sock.connect(sockaddr)

                # Enviar [4 bytes len][JSON]
                payload = json.dumps(request).encode('utf-8')
                sock.sendall(struct.pack('>I', len(payload)) + payload)

                # Recibir respuesta
                raw_len = _recv_exact(sock, 4)
                length  = struct.unpack('>I', raw_len)[0]
                raw     = _recv_exact(sock, length)
                sock.close()

                return json.loads(raw.decode('utf-8'))

            except (ConnectionRefusedError, OSError) as e:
                last_err = e
                continue

        raise QueryClientError(
            f"No se pudo conectar al Query Engine "
            f"({self.host}:{self.port}): {last_err}\n"
            f"  Verificá que el Query Engine esté corriendo: "
            f"python -m src.query engine"
        )

    def query(self, command: str, filters: dict = None) -> dict:
        """
        Ejecutar una consulta en el Query Engine.

        Args:
            command (str): 'logs', 'alerts' o 'stats'.
            filters (dict): Filtros opcionales.

        Returns:
            dict: Respuesta del engine.
        """
        request = {
            'command': command,
            'filters': filters or {},
        }
        return self._send_recv(request)


#  Helpers de presentación                                             

def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Leer exactamente n bytes del socket."""
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise QueryClientError("Conexión cerrada por el servidor")
        data += chunk
    return data


def _level_color(level: str) -> str:
    return _C.get(level, '')


def _print_error(response: dict):
    print(
        f"\n{_C['ERROR']} Error del servidor:{_C['RESET']} "
        f"{response.get('error', 'desconocido')}\n"
    )


def _print_logs_table(data: List[Dict[str, Any]], count: int):
    """Imprimir logs como tabla formateada."""
    bold  = _C['BOLD']
    dim   = _C['DIM']
    reset = _C['RESET']

    print(f"\n{bold} Logs — {count} resultado(s){reset}\n")

    if not data:
        print(f"{dim}  Sin resultados.{reset}\n")
        return

    # Cabecera
    print(
        f"{bold}"
        f"{'ID':>6}  {'TIMESTAMP':19}  {'LEVEL':8}  "
        f"{'SOURCE':10}  {'MESSAGE'}"
        f"{reset}"
    )
    print("─" * 100)

    for row in data:
        level  = row.get('level', '')
        color  = _level_color(level)
        ts     = (row.get('timestamp') or '')[:19]
        source = row.get('source', '')
        msg    = row.get('message', '')
        rid    = row.get('id', '')

        # Truncar mensaje largo
        if len(msg) > 60:
            msg = msg[:57] + '...'

        print(
            f"{dim}{rid:>6}{reset}  "
            f"{dim}{ts:19}{reset}  "
            f"{color}{level:8}{reset}  "
            f"{source:10}  "
            f"{msg}"
        )

    print()


def _print_alerts_table(data: List[Dict[str, Any]], count: int):
    """Imprimir alertas como tabla formateada."""
    bold  = _C['BOLD']
    dim   = _C['DIM']
    reset = _C['RESET']
    green = _C['GREEN']

    print(f"\n{bold} Alertas — {count} resultado(s){reset}\n")

    if not data:
        print(f"{dim}  Sin resultados.{reset}\n")
        return

    print(
        f"{bold}"
        f"{'ID':>6}  {'TIMESTAMP':19}  {'LEVEL':8}  "
        f"{'SOURCE':10}  {'MAIL':4}  {'MESSAGE'}"
        f"{reset}"
    )
    print("─" * 105)

    for row in data:
        level    = row.get('level', '')
        color    = _level_color(level)
        ts       = (row.get('timestamp') or '')[:19]
        source   = row.get('source', '')
        msg      = row.get('message', '')
        rid      = row.get('id', '')
        mailed   = row.get('notified_by_mail', 0)
        mail_str = f"{green}✓{reset}" if mailed else f"{dim}✗{reset}"

        if len(msg) > 55:
            msg = msg[:52] + '...'

        print(
            f"{dim}{rid:>6}{reset}  "
            f"{dim}{ts:19}{reset}  "
            f"{color}{level:8}{reset}  "
            f"{source:10}  "
            f"{mail_str:4}  "
            f"{msg}"
        )

    print()


def _print_stats_table(data: Dict[str, Any]):
    """Imprimir estadísticas de forma estructurada."""
    bold  = _C['BOLD']
    dim   = _C['DIM']
    reset = _C['RESET']

    total = data.get('total', 0)
    print(f"\n{bold} Estadísticas de logs{reset}\n")
    print(f"  Total logs: {bold}{total:,}{reset}\n")

    # Por nivel
    by_level = data.get('by_level', {})
    if by_level:
        print(f"{bold}  Por nivel:{reset}")
        for level in ['CRITICAL', 'ERROR', 'WARNING', 'INFO']:
            count = by_level.get(level, 0)
            if count:
                color = _level_color(level)
                bar   = '█' * min(int(count / max(total, 1) * 40), 40)
                pct   = count / total * 100 if total else 0
                print(
                    f"    {color}{level:8}{reset}  "
                    f"{count:>6,}  {dim}{bar:<40}  {pct:.1f}%{reset}"
                )
        print()

    # Por source
    by_source = data.get('by_source', {})
    if by_source:
        print(f"{bold}  Por fuente:{reset}")
        for source, count in sorted(by_source.items()):
            pct = count / total * 100 if total else 0
            bar = '█' * min(int(count / max(total, 1) * 40), 40)
            print(
                f"    {source:10}  {count:>6,}  "
                f"{dim}{bar:<40}  {pct:.1f}%{reset}"
            )
        print()

    # Por source y nivel
    by_both = data.get('by_level_and_source', {})
    if by_both:
        print(f"{bold}  Por fuente y nivel:{reset}")
        for source in sorted(by_both.keys()):
            levels = by_both[source]
            parts  = []
            for level in ['CRITICAL', 'ERROR', 'WARNING', 'INFO']:
                c = levels.get(level, 0)
                if c:
                    color = _level_color(level)
                    parts.append(f"{color}{level}:{c}{reset}")
            print(f"    {source:10}  {', '.join(parts)}")
        print()
