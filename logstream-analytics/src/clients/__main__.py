#!/usr/bin/env python3
"""
Entry point para ejecutar el Log Producer como módulo.

Los valores por defecto de los argumentos se leen del .env via config.
Los argumentos CLI tienen prioridad sobre el .env.

Uso:
    python3 -m src.clients --source webapp
    python3 -m src.clients --source database --rate 10
    python -m src.clients --source api --server 192.168.1.100:9000
"""

import argparse
import sys

from src.core.config import config
from .log_producer import LogProducer


def main():
    parser = argparse.ArgumentParser(
        description='Log Producer - Genera y envía logs sintéticos al Log Server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Los valores por defecto se leen del archivo .env del proyecto.

Ejemplos:
  python -m src.clients --source webapp
  python -m src.clients --source database --rate 10 --error-rate 0.2
  python -m src.clients --source api --server [::1]:9000
  python -m src.clients --source webapp --server 192.168.1.100:9000
        """
    )

    parser.add_argument(
        '--source',
        required=True,
        choices=['webapp', 'database', 'api'],
        help='Tipo de fuente de logs'
    )
    parser.add_argument(
        '--server',
        default=f'{config.PRODUCER_DEFAULT_HOST}:{config.PRODUCER_DEFAULT_PORT}',
        help=(
            f'Servidor IP:PORT o [IPv6]:PORT '
            f'(default del .env: '
            f'{config.PRODUCER_DEFAULT_HOST}:{config.PRODUCER_DEFAULT_PORT})'
        )
    )
    parser.add_argument(
        '--rate',
        type=int,
        default=config.PRODUCER_DEFAULT_RATE,
        help=f'Logs por segundo (default del .env: {config.PRODUCER_DEFAULT_RATE})'
    )
    parser.add_argument(
        '--error-rate',
        type=float,
        default=config.PRODUCER_DEFAULT_ERROR_RATE,
        help=(
            f'Probabilidad de ERROR 0.0-1.0 '
            f'(default del .env: {config.PRODUCER_DEFAULT_ERROR_RATE})'
        )
    )
    parser.add_argument(
        '--anomaly-rate',
        type=float,
        default=config.PRODUCER_DEFAULT_ANOMALY_RATE,
        help=(
            f'Probabilidad de CRITICAL 0.0-1.0 '
            f'(default del .env: {config.PRODUCER_DEFAULT_ANOMALY_RATE})'
        )
    )

    args = parser.parse_args()

    # Parsear --server (IPv4 o IPv6)
    try:
        if args.server.startswith('['):
            # IPv6: [addr]:port
            host_part, port_part = args.server.split(']:')
            host = host_part[1:]
            port = int(port_part)
        else:
            # IPv4: addr:port
            host, port_str = args.server.rsplit(':', 1)
            port = int(port_str)
    except (ValueError, IndexError):
        print(f" Formato de servidor inválido: '{args.server}'")
        print(f"   IPv4: IP:PORT     (ej: 127.0.0.1:9000)")
        print(f"   IPv6: [IP]:PORT   (ej: [::1]:9000)")
        sys.exit(1)

    # Validar tasas
    for name, value in [('--error-rate', args.error_rate), ('--anomaly-rate', args.anomaly_rate)]:
        if not (0.0 <= value <= 1.0):
            print(f" {name} debe estar entre 0.0 y 1.0 (recibido: {value})")
            sys.exit(1)

    try:
        producer = LogProducer(
            source=args.source,
            server_host=host,
            server_port=port,
            rate=args.rate,
            error_rate=args.error_rate,
            anomaly_rate=args.anomaly_rate
        )
        producer.run()
    except ValueError as e:
        print(f" {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
