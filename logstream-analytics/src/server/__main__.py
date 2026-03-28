#!/usr/bin/env python3
"""
Entry point para ejecutar el Log Server como módulo.

Los valores por defecto de los argumentos se leen del .env via config.
Los argumentos CLI tienen prioridad sobre el .env.

Uso:
    python3 -m src.server
    python3 -m src.server --port 8000
    python -m src.server --host 0.0.0.0 --redis-host 192.168.1.100
"""

import argparse
import asyncio
import sys

from src.core.config import config


def main():
    parser = argparse.ArgumentParser(
        description='Log Server - Servidor de ingesta de logs (IPv4/IPv6)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Los valores por defecto se leen del archivo .env del proyecto.

Ejemplos:
  # Usar valores del .env
  python -m src.server

  # Sobreescribir puerto
  python -m src.server --port 8000

  # Solo IPv4
  python -m src.server --host 0.0.0.0

  # Redis remoto
  python -m src.server --redis-host 192.168.1.100
        """
    )

    parser.add_argument(
        '--host',
        default=config.LOG_SERVER_HOST,
        help=f'IP para escuchar (default del .env: {config.LOG_SERVER_HOST})'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=config.LOG_SERVER_PORT,
        help=f'Puerto para escuchar (default del .env: {config.LOG_SERVER_PORT})'
    )
    parser.add_argument(
        '--redis-host',
        default=config.REDIS_HOST,
        help=f'Host de Redis (default del .env: {config.REDIS_HOST})'
    )
    parser.add_argument(
        '--redis-port',
        type=int,
        default=config.REDIS_PORT,
        help=f'Puerto de Redis (default del .env: {config.REDIS_PORT})'
    )

    args = parser.parse_args()

    try:
        from .log_server import LogServer
    except ImportError as e:
        print(f"   Error importando módulos: {e}")
        sys.exit(1)

    server = LogServer(
        host=args.host,
        port=args.port,
        redis_host=args.redis_host,
        redis_port=args.redis_port
    )

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n Adios!")


if __name__ == '__main__':
    main()
