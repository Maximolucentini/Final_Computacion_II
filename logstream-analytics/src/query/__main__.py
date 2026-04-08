#!/usr/bin/env python3
"""
Entry point del módulo query de LogStream Analytics.

Subcomandos disponibles:
  engine   — iniciar el Query Engine (servidor TCP)
  logs     — consultar logs históricos
  alerts   — consultar alertas
  stats    — ver estadísticas agregadas

Uso:
    # Iniciar el servidor
    python3 -m src.query engine

    # Consultar logs
    python3 -m src.query logs
    python -m src.query logs --level ERROR
    python3 -m src.query logs --source webapp --level WARNING --limit 50
    python3 -m src.query logs --message "timeout" --start-date 2026-01-01
    python3 -m src.query logs --json

    # Consultar alertas
    python -m src.query alerts
    python -m src.query alerts --level CRITICAL
    python -m src.query alerts --mailed

    # Estadísticas
    python -m src.query stats
    python -m src.query stats --start-date 2026-03-01 --json
"""

import argparse
import json
import sys

from src.core.config import config


#  Subcomando: engine                                                  

def cmd_engine(args):
    """Iniciar el Query Engine."""
    import asyncio
    from .query_engine import QueryEngine

    engine = QueryEngine(
        host=args.host,
        port=args.port,
    )
    try:
        asyncio.run(engine.start())
    except KeyboardInterrupt:
        print("\n Adios!")


#  Subcomando: logs                                                    

def cmd_logs(args):
    """Consultar logs históricos."""
    from .query_client import QueryClient, _print_logs_table, _print_error

    filters = {}
    if args.source:     filters['source']     = args.source
    if args.level:      filters['level']      = args.level
    if args.message:    filters['message']    = args.message
    if args.start_date: filters['start_date'] = args.start_date
    if args.end_date:   filters['end_date']   = args.end_date
    if args.limit:      filters['limit']      = args.limit
    if args.offset:     filters['offset']     = args.offset

    client   = QueryClient(host=args.server_host, port=args.server_port)
    response = _do_query(client, 'logs', filters)
    if response is None:
        return

    if response.get('status') == 'error':
        _print_error(response)
        sys.exit(1)

    if args.json:
        print(json.dumps(response, indent=2, ensure_ascii=False))
    else:
        _print_logs_table(response.get('data', []), response.get('count', 0))


#  Subcomando: alerts                                                  

def cmd_alerts(args):
    """Consultar alertas."""
    from .query_client import QueryClient, _print_alerts_table, _print_error

    filters = {}
    if args.source:     filters['source']     = args.source
    if args.level:      filters['level']      = args.level
    if args.message:    filters['message']    = args.message
    if args.start_date: filters['start_date'] = args.start_date
    if args.end_date:   filters['end_date']   = args.end_date
    if args.limit:      filters['limit']      = args.limit
    if args.offset:     filters['offset']     = args.offset
    if args.mailed:     filters['notified_by_mail'] = True
    if args.not_mailed: filters['notified_by_mail'] = False

    client   = QueryClient(host=args.server_host, port=args.server_port)
    response = _do_query(client, 'alerts', filters)
    if response is None:
        return

    if response.get('status') == 'error':
        _print_error(response)
        sys.exit(1)

    if args.json:
        print(json.dumps(response, indent=2, ensure_ascii=False))
    else:
        _print_alerts_table(response.get('data', []), response.get('count', 0))


#  Subcomando: stats                                                   

def cmd_stats(args):
    """Ver estadísticas agregadas."""
    from .query_client import QueryClient, _print_stats_table, _print_error

    filters = {}
    if args.start_date: filters['start_date'] = args.start_date
    if args.end_date:   filters['end_date']   = args.end_date

    client   = QueryClient(host=args.server_host, port=args.server_port)
    response = _do_query(client, 'stats', filters)
    if response is None:
        return

    if response.get('status') == 'error':
        _print_error(response)
        sys.exit(1)

    if args.json:
        print(json.dumps(response, indent=2, ensure_ascii=False))
    else:
        _print_stats_table(response.get('data', {}))


#  Helper de conexión con manejo de errores                           

def _do_query(client, command: str, filters: dict):
    """Ejecutar query con manejo de error de conexión."""
    from .query_client import QueryClientError
    try:
        return client.query(command, filters)
    except QueryClientError as e:
        print(f"\n Error de conexión: {e}\n")
        sys.exit(1)


#  Argumentos comunes (server host/port + json + fechas)              

def _add_server_args(parser):
    """Agregar argumentos de conexión al engine."""
    parser.add_argument(
        '--server-host',
        default=config.QUERY_ENGINE_HOST,
        help=f'Host del Query Engine (default del .env: {config.QUERY_ENGINE_HOST})'
    )
    parser.add_argument(
        '--server-port',
        type=int,
        default=config.QUERY_ENGINE_PORT,
        dest='server_port',
        help=f'Puerto del Query Engine (default del .env: {config.QUERY_ENGINE_PORT})'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Salida en JSON crudo en lugar de tabla formateada'
    )


def _add_date_args(parser):
    """Agregar filtros de fecha."""
    parser.add_argument(
        '--start-date',
        dest='start_date',
        metavar='YYYY-MM-DD',
        help='Filtrar desde esta fecha (ISO 8601, ej: 2026-01-01)'
    )
    parser.add_argument(
        '--end-date',
        dest='end_date',
        metavar='YYYY-MM-DD',
        help='Filtrar hasta esta fecha (ISO 8601, ej: 2026-12-31)'
    )


def _add_common_filters(parser):
    """Agregar filtros comunes a logs y alerts."""
    parser.add_argument(
        '--source',
        choices=['webapp', 'database', 'api'],
        help='Filtrar por fuente'
    )
    parser.add_argument(
        '--level',
        choices=['INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Filtrar por nivel'
    )
    parser.add_argument(
        '--message',
        metavar='TEXTO',
        help='Búsqueda parcial por texto en el mensaje'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=100,
        help='Máximo de resultados (default: 100, máx: 1000)'
    )
    parser.add_argument(
        '--offset',
        type=int,
        default=0,
        help='Desplazamiento para paginación (default: 0)'
    )
    _add_date_args(parser)


#  main                                                                

def main():
    parser = argparse.ArgumentParser(
        prog='python -m src.query',
        description='LogStream Analytics — Query Client / Engine',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Iniciar el servidor de consultas
  python -m src.query engine

  # Ver últimos 100 logs
  python -m src.query logs

  # Logs de nivel ERROR de webapp
  python -m src.query logs --level ERROR --source webapp

  # Logs que contengan "timeout"
  python -m src.query logs --message "timeout"

  # Logs del día de hoy en JSON
  python -m src.query logs --start-date 2026-03-28 --json

  # Ver alertas críticas no notificadas por mail
  python -m src.query alerts --level CRITICAL --not-mailed

  # Estadísticas globales
  python -m src.query stats
        """
    )

    subparsers = parser.add_subparsers(dest='subcommand', metavar='SUBCOMANDO')
    subparsers.required = True

    # --- engine ---
    p_engine = subparsers.add_parser(
        'engine',
        help='Iniciar el Query Engine (servidor TCP)'
    )
    p_engine.add_argument(
        '--host',
        default=config.QUERY_ENGINE_HOST,
        help=f'IP para escuchar (default del .env: {config.QUERY_ENGINE_HOST})'
    )
    p_engine.add_argument(
        '--port',
        type=int,
        default=config.QUERY_ENGINE_PORT,
        help=f'Puerto para escuchar (default del .env: {config.QUERY_ENGINE_PORT})'
    )
    p_engine.set_defaults(func=cmd_engine)

    # --- logs ---
    p_logs = subparsers.add_parser(
        'logs',
        help='Consultar logs históricos'
    )
    _add_common_filters(p_logs)
    _add_server_args(p_logs)
    p_logs.set_defaults(func=cmd_logs)

    # --- alerts ---
    p_alerts = subparsers.add_parser(
        'alerts',
        help='Consultar alertas'
    )
    _add_common_filters(p_alerts)
    _add_server_args(p_alerts)
    p_alerts.add_argument(
        '--mailed',
        action='store_true',
        help='Solo alertas que fueron notificadas por mail'
    )
    p_alerts.add_argument(
        '--not-mailed',
        dest='not_mailed',
        action='store_true',
        help='Solo alertas que NO fueron notificadas por mail'
    )
    p_alerts.set_defaults(func=cmd_alerts)

    # --- stats ---
    p_stats = subparsers.add_parser(
        'stats',
        help='Ver estadísticas agregadas de logs'
    )
    _add_date_args(p_stats)
    _add_server_args(p_stats)
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
