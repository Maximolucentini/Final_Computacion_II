#!/usr/bin/env python3
# src/clients/__main__.py
"""
Entry point para ejecutar el Log Producer como módulo.

Uso:
    python -m src.clients --source webapp --rate 5
    python src/clients --source webapp --rate 5
"""

import argparse
import sys
from .log_producer import LogProducer

def main():
    """CLI con argparse."""
    
    parser = argparse.ArgumentParser(
        description='Log Producer - Genera logs sintéticos (IPv4/IPv6)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python -m src.clients --source webapp --rate 5
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
        default='127.0.0.1:9000',
        help='Servidor (IP:PORT o [IPv6]:PORT). Default: 127.0.0.1:9000'
    )
    
    parser.add_argument(
        '--rate',
        type=int,
        default=5,
        help='Logs/segundo. Default: 5'
    )
    
    parser.add_argument(
        '--error-rate',
        type=float,
        default=0.05,
        help='Prob. de ERROR (0.0-1.0). Default: 0.05'
    )
    
    parser.add_argument(
        '--anomaly-rate',
        type=float,
        default=0.01,
        help='Prob. de CRITICAL (0.0-1.0). Default: 0.01'
    )
    
    args = parser.parse_args()
    
    # Parsear server (IPv4 o IPv6)
    try:
        if args.server.startswith('['):
            # IPv6: [addr]:port
            host_port = args.server.split(']:')
            if len(host_port) != 2:
                raise ValueError("Formato IPv6 inválido")
            host = host_port[0][1:]
            port = int(host_port[1])
        else:
            # IPv4: addr:port
            host, port = args.server.split(':')
            port = int(port)
    except ValueError:
        print(f" Formato inválido: {args.server}")
        print(f"   IPv4: IP:PORT (ej: 127.0.0.1:9000)")
        print(f"   IPv6: [IP]:PORT (ej: [::1]:9000)")
        sys.exit(1)
    
    # Validar tasas
    if not (0.0 <= args.error_rate <= 1.0):
        print(" --error-rate debe estar entre 0.0 y 1.0")
        sys.exit(1)
    
    if not (0.0 <= args.anomaly_rate <= 1.0):
        print(" --anomaly-rate debe estar entre 0.0 y 1.0")
        sys.exit(1)
    
    # Crear y ejecutar
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