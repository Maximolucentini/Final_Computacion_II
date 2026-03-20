#!/usr/bin/env python3



import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.db import init_db, get_db_info
import argparse


def main():
    """Inicializar base de datos."""
    
    parser = argparse.ArgumentParser(
        description='Inicializar base de datos SQLite para LogStream Analytics'
    )
    
    parser.add_argument(
        '--db-path',
        help='Ruta personalizada para la base de datos',
        default=None
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Forzar reinicialización (NO borra datos existentes)'
    )
    
    args = parser.parse_args()
    
    print("="*60)
    print("  INICIALIZACIÓN DE BASE DE DATOS")
    print("="*60)
    
    # Inicializar
    try:
        init_db(args.db_path)
        print()
        
        # Mostrar info
        info = get_db_info()
        print("Información de la base de datos:")
        print(f"   Ruta: {info['path']}")
        print(f"   Existe: {'Sí' if info['exists'] else 'No'}")
        print(f"   Tamaño: {info['size_mb']} MB")
        print(f"   Total logs: {info['total_logs']:,}")
        print(f"   WAL mode: {'Habilitado' if info['wal_mode'] else 'Deshabilitado'}")
        print()
        print("Base de datos lista para usar")
        print("="*60)
        
    except Exception as e:
        print(f"\nError al inicializar base de datos: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
