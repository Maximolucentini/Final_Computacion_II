#!/usr/bin/env python3
"""
Entry point para ejecutar el Alert Manager como módulo independiente.

Los valores por defecto se leen del .env vía config.
Los argumentos CLI tienen prioridad sobre el .env.

Uso:
    python3 -m src.alerts
    python3 -m src.alerts --fifo /tmp/mi_pipe
    python3 -m src.alerts --no-mail
    python -m src.alerts --no-db
"""

import argparse
import sys
from pathlib import Path

from src.core.config import config


def main():
    parser = argparse.ArgumentParser(
        description='Alert Manager — consume alertas del FIFO y las despacha',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Los valores por defecto se leen del archivo .env del proyecto.

Ejemplos:
  # Usar configuración del .env
  python -m src.alerts

  # FIFO personalizado
  python -m src.alerts --fifo /tmp/mi_pipe

  # Deshabilitar mail para esta ejecución 
  python -m src.alerts --no-mail

  # Solo consola, sin DB ni mail
  python -m src.alerts --no-db --no-mail

Configuración actual (.env):
  FIFO:          {config.FIFO_PATH}
  Niveles:       {', '.join(config.ALERT_LEVELS)}
  Guardar DB:    {config.ALERT_STORE_IN_DB}
  Consola:       {config.ALERT_PRINT_TO_CONSOLE}
  Mail:          {config.ALERT_EMAIL_ENABLED}
  Mail niveles:  {', '.join(config.ALERT_MAIL_LEVELS)}
        """
    )

    parser.add_argument(
        '--fifo',
        default=str(config.FIFO_PATH),
        help=f'Ruta del FIFO nombrado (default del .env: {config.FIFO_PATH})'
    )
    parser.add_argument(
        '--no-mail',
        action='store_true',
        help='Deshabilitar envío de mail para esta ejecución'
    )
    parser.add_argument(
        '--no-db',
        action='store_true',
        help='Deshabilitar guardado en DB para esta ejecución'
    )
    parser.add_argument(
        '--no-console',
        action='store_true',
        help='Deshabilitar impresión en consola para esta ejecución'
    )

    args = parser.parse_args()

    # Sobreescribir config con flags CLI si se pasaron
    if args.no_mail:
        config.ALERT_EMAIL_ENABLED = False
        print(" Mail deshabilitado por argumento CLI (--no-mail)")

    if args.no_db:
        config.ALERT_STORE_IN_DB = False
        print(" Guardado en DB deshabilitado por argumento CLI (--no-db)")

    if args.no_console:
        config.ALERT_PRINT_TO_CONSOLE = False

    # Importar aquí para que las modificaciones al config ya estén aplicadas
    try:
        from .alert_manager import AlertManager
    except ImportError as e:
        print(f" Error importando AlertManager: {e}")
        sys.exit(1)

    manager = AlertManager(fifo_path=Path(args.fifo))

    try:
        manager.run()
    except KeyboardInterrupt:
        print("\n Adios!")


if __name__ == '__main__':
    main()
