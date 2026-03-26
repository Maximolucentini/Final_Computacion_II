#!/usr/bin/env python3

"""
Entry point para ejecutar el Log Server como módulo.

Uso:
    python -m src.server.log_server
    python -m src.server.log_server --host :: --port 9000
"""

import argparse
import asyncio
import sys


def main():
    """CLI con argparse."""
    
    parser = argparse.ArgumentParser(
        description='Log Server - Servidor de ingesta de logs (IPv4/IPv6)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Escuchar en todas las interfaces (IPv4 e IPv6)
  python -m src.server.log_server --host ::
  
  # Solo IPv4
  python -m src.server.log_server --host 0.0.0.0
  
  # Puerto personalizado
  python -m src.server.log_server --port 8000
  
  # Redis remoto
  python -m src.server.log_server --redis-host 192.168.1.100
        """
    )
    
    parser.add_argument(
        '--host',
        default='::',
        help='IP para escuchar (:: = todas IPv4/IPv6, 0.0.0.0 = todas IPv4). Default: ::'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=9000,
        help='Puerto para escuchar. Default: 9000'
    )
    
    parser.add_argument(
        '--redis-host',
        default='localhost',
        help='Host de Redis. Default: localhost'
    )
    
    parser.add_argument(
        '--redis-port',
        type=int,
        default=6379,
        help='Puerto de Redis. Default: 6379'
    )
    
    args = parser.parse_args()
    
    # Importar aquí para evitar errores si falta Redis
    try:
        from .log_server import LogServer
    except ImportError as e:
        print(f"   Error importando módulos: {e}")
        print(f"   Verifica que hayas instalado: pip install redis")
        sys.exit(1)
    
    # Crear servidor
    server = LogServer(
        host=args.host,
        port=args.port,
        redis_host=args.redis_host,
        redis_port=args.redis_port
    )
    
    # Ejecutar
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n Adios!")

if __name__ == '__main__':
    main()