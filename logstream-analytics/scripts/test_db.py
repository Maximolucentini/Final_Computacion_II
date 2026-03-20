#!/usr/bin/env python3

"""
Script para probar la base de datos SQLite.

Prueba:
- Inicialización
- Inserción de logs
- Consultas
- Estadísticas
- Concurrencia con Redis lock
"""

import sys
from pathlib import Path
from datetime import datetime
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.db import (
    init_db,
    insert_log,
    query_logs,
    get_stats,
    get_db_info
)


def test_insert():
    """Probar inserción de logs."""
    print("\n TEST: Inserción de logs")
    print("-" * 40)
    
    logs_test = [
        {
            'timestamp': '2026-03-16T22:00:00',
            'source': 'webapp',
            'level': 'INFO',
            'message': 'Usuario 1234 inició sesión',
            'metadata': {'user_id': 1234, 'ip': '192.168.1.100'},
            'ingested_at': datetime.now().isoformat(),
            'client_ip': '127.0.0.1'
        },
        {
            'timestamp': '2026-03-16T22:00:05',
            'source': 'database',
            'level': 'WARNING',
            'message': 'Query lento: 1500ms',
            'metadata': {'duration_ms': 1500, 'query': 'SELECT * FROM users'},
            'ingested_at': datetime.now().isoformat(),
            'client_ip': '127.0.0.1'
        },
        {
            'timestamp': '2026-03-16T22:00:10',
            'source': 'api',
            'level': 'ERROR',
            'message': 'Error 500: Internal server error',
            'metadata': {'endpoint': '/api/users', 'method': 'GET'},
            'ingested_at': datetime.now().isoformat(),
            'client_ip': '127.0.0.1'
        },
        {
            'timestamp': '2026-03-16T22:00:15',
            'source': 'webapp',
            'level': 'CRITICAL',
            'message': 'Sistema fuera de servicio',
            'metadata': {'reason': 'database_down'},
            'ingested_at': datetime.now().isoformat(),
            'client_ip': '127.0.0.1'
        },
        {
            'timestamp': '2026-03-16T22:00:20',
            'source': 'webapp',
            'level': 'INFO',
            'message': 'Usuario 5678 cerró sesión',
            'metadata': {'user_id': 5678},
            'ingested_at': datetime.now().isoformat(),
            'client_ip': '127.0.0.1'
        }
    ]
    
    for log in logs_test:
        log_id = insert_log(log)
        print(f"   Insertado log ID {log_id}: [{log['level']}] {log['message'][:50]}")
    
    print(f"\n  Total insertados: {len(logs_test)}")


def test_query():
    """Probar consultas."""
    print("\n TEST: Consultas")
    print("-" * 40)
    
    # Todos los logs
    print("\n   Últimos 10 logs:")
    logs = query_logs(limit=10)
    for log in logs:
        print(f"    [{log['level']:8s}] {log['source']:10s} | {log['message'][:40]}")
    
    # Solo errores
    print("\n   Solo errores:")
    errors = query_logs(level='ERROR')
    for log in errors:
        print(f"    {log['timestamp']} | {log['message']}")
    
    # Solo webapp
    print("\n   Solo webapp:")
    webapp_logs = query_logs(source='webapp', limit=5)
    for log in webapp_logs:
        print(f"    [{log['level']}] {log['message']}")


def test_stats():
    """Probar estadísticas."""
    print("\n TEST: Estadísticas")
    print("-" * 40)
    
    stats = get_stats()
    
    print(f"\n  Total de logs: {stats['total']:,}")
    
    print("\n  Por nivel:")
    for level, count in sorted(stats['by_level'].items()):
        print(f"    {level:10s}: {count:5d}")
    
    print("\n  Por source:")
    for source, count in sorted(stats['by_source'].items()):
        print(f"    {source:10s}: {count:5d}")
    
    print("\n  Por source y nivel:")
    for source, levels in sorted(stats['by_level_and_source'].items()):
        print(f"    {source}:")
        for level, count in sorted(levels.items()):
            print(f"      {level:10s}: {count:5d}")


def test_concurrency():
    """Probar escrituras concurrentes (simulado)."""
    print("\n TEST: Concurrencia (Redis lock)")
    print("-" * 40)
    
    print("\n  Insertando 10 logs rápidamente...")
    start_time = time.time()
    
    for i in range(10):
        log = {
            'timestamp': datetime.now().isoformat(),
            'source': 'webapp',
            'level': 'INFO',
            'message': f'Test concurrencia #{i+1}',
            'ingested_at': datetime.now().isoformat(),
            'client_ip': '127.0.0.1'
        }
        log_id = insert_log(log)
        print(f"     Log {log_id} insertado")
    
    elapsed = time.time() - start_time
    print(f"\n  Tiempo total: {elapsed:.2f}s")
    print(f"  Promedio: {elapsed/10:.3f}s por log")
    print("  (Incluye tiempo de adquisición de Redis lock)")


def main():
    """Ejecutar todas las pruebas."""
    
    print("="*60)
    print(" PRUEBAS DE BASE DE DATOS")
    print("="*60)
    
    # Inicializar DB
    print("\n  Inicializando base de datos...")
    init_db()
    
    # Info inicial
    info = get_db_info()
    print(f"\n Base de datos: {info['path']}")
    print(f"   Logs actuales: {info['total_logs']:,}")
    
    try:
        # Ejecutar pruebas
        test_insert()
        test_query()
        test_stats()
        test_concurrency()
        
        # Info final
        print("\n" + "="*60)
        info = get_db_info()
        print(f" Estadísticas finales:")
        print(f"   Total logs: {info['total_logs']:,}")
        print(f"   Tamaño DB: {info['size_mb']} MB")
        print(f"   WAL mode: {'SI' if info['wal_mode'] else 'NO'}")
        print("\nTODAS LAS PRUEBAS PASARON")
        print("="*60)
        
    except Exception as e:
        print(f"\nERROR EN PRUEBAS: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
