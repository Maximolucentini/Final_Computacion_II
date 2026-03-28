# src/alerts/alert_manager.py
"""
Alert Manager — proceso independiente de LogStream Analytics.

Lee alertas desde el FIFO nombrado (escrito por los workers Celery),
y para cada alerta dispara hasta tres handlers según configuración del .env:

  1. Consola  — imprime con color si ALERT_PRINT_TO_CONSOLE=true
  2. DB       — guarda en tabla `alerts` si ALERT_STORE_IN_DB=true
  3. Mail     — envía mail SMTP si ALERT_EMAIL_ENABLED=true y el nivel
                está en ALERT_MAIL_LEVELS

El proceso corre indefinidamente hasta recibir SIGINT/SIGTERM (Ctrl+C).

Uso:
    python -m src.alerts
    python -m src.alerts --fifo /tmp/mi_pipe
"""

import json
import os
import signal
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from src.core.config import config
from src.core.db import init_db, insert_alert
from .mailer import Mailer


_COLORS = {
    'CRITICAL': '\033[95m',  
    'ERROR':    '\033[91m',  
    'WARNING':  '\033[93m',  
    'INFO':     '\033[94m',  
    'RESET':    '\033[0m',
    'BOLD':     '\033[1m',
    'DIM':      '\033[2m',
}


class AlertManager:
    """
    Proceso independiente que consume alertas del FIFO y las despacha.

    Diseño:
    - Lee el FIFO en modo no bloqueante para no quedar colgado si no
      hay writers (workers).
    - Si no hay datos, duerme ALERT_FIFO_POLL_INTERVAL segundos.
    - Si ALERT_MAIL_BATCH_SECONDS > 0, acumula alertas en un buffer
      y las envía en un solo mail cada N segundos.
    - Si ALERT_MAIL_BATCH_SECONDS == 0, manda un mail por cada alerta.
    """

    def __init__(self, fifo_path: Path = None):
        """
        Args:
            fifo_path (Path, optional): Ruta del FIFO. Default: config.FIFO_PATH.
        """
        self.fifo_path    = fifo_path or config.FIFO_PATH
        self.running      = True
        self.mailer       = Mailer()
        self._fd          = None   # file descriptor del FIFO abierto

        # Buffer para modo batch
        self._mail_buffer: List[Dict[str, Any]] = []
        self._last_batch_sent: float = time.time()

        # Estadísticas
        self.stats = {
            'total_received':    0,
            'total_db':          0,
            'total_mail_sent':   0,
            'total_mail_failed': 0,
            'total_errors':      0,
            'started_at':        None,
        }


    def _ensure_fifo(self):
        """Crear el FIFO si no existe."""
        self.fifo_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.fifo_path.exists():
            os.mkfifo(self.fifo_path)
            print(f" FIFO creado: {self.fifo_path}")
        else:
            print(f" FIFO existente: {self.fifo_path}")

    def _open_fifo(self):
        """
        Abrir el FIFO en modo no bloqueante para lectura.

        O_RDONLY | O_NONBLOCK: abre sin bloquearse aunque no haya writer.
        Retorna True si se abrió correctamente.
        """
        try:
            self._fd = os.open(self.fifo_path, os.O_RDONLY | os.O_NONBLOCK)
            return True
        except OSError as e:
            print(f" Error abriendo FIFO: {e}")
            return False

    def _close_fifo(self):
        """Cerrar el file descriptor del FIFO."""
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def _setup_signals(self):
        """Registrar handlers para SIGINT y SIGTERM."""
        signal.signal(signal.SIGINT,  self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        """Handler de señales de apagado."""
        print(f"\n\n Señal {signum} recibida — deteniendo Alert Manager...")
        self.running = False

    #  Lectura del FIFO                                                    

    def _read_lines(self) -> List[str]:
        """
        Leer todas las líneas disponibles en el FIFO sin bloquearse.

        El FIFO recibe líneas JSON terminadas en '\\n'.
        Si no hay datos, retorna lista vacía.

        Returns:
            List[str]: Líneas leídas (pueden ser varias por llamada).
        """
        try:
            raw = os.read(self._fd, 65536)   # leer hasta 64 KB de una vez
            if not raw:
                return []
            return [
                line for line in raw.decode('utf-8').split('\n')
                if line.strip()
            ]
        except BlockingIOError:
            # EAGAIN / EWOULDBLOCK: no hay datos disponibles ahora
            return []
        except OSError as e:
            # El pipe fue cerrado por el lado writer; reabrirlo en el próximo ciclo
            print(f" FIFO cerrado por writer, reabriendo... ({e})")
            self._close_fifo()
            time.sleep(1)
            self._open_fifo()
            return []

    def _parse_alert(self, line: str) -> Dict[str, Any] | None:
        """
        Parsear una línea JSON del FIFO.

        Args:
            line (str): Línea JSON cruda.

        Returns:
            dict | None: Alerta parseada, o None si el JSON es inválido.
        """
        try:
            return json.loads(line)
        except json.JSONDecodeError as e:
            print(f" JSON inválido en FIFO: {e} | contenido: {line[:80]}")
            self.stats['total_errors'] += 1
            return None

    #  Handlers de alerta                                                  

    def _handle_console(self, alert: Dict[str, Any]):
        """Imprimir alerta en consola con color."""
        if not config.ALERT_PRINT_TO_CONSOLE:
            return

        level   = alert.get('level', 'UNKNOWN')
        source  = alert.get('source', '?')
        message = alert.get('message', '')
        ts      = alert.get('timestamp', datetime.now().isoformat())[:19]

        color = _COLORS.get(level, '')
        bold  = _COLORS['BOLD']
        reset = _COLORS['RESET']
        dim   = _COLORS['DIM']

        print(
            f"{bold}{color}[ALERTA][{level:8s}]{reset} "
            f"{dim}{ts}{reset} "
            f"{color}{source:10s}{reset} | "
            f"{message}"
        )

    def _handle_db(self, alert: Dict[str, Any], mail_sent: bool) -> int | None:
        """
        Guardar alerta en la tabla alerts de SQLite.

        Args:
            alert (dict): Alerta a guardar.
            mail_sent (bool): Si ya se envió mail para esta alerta.

        Returns:
            int | None: ID del registro insertado, o None si falló.
        """
        if not config.ALERT_STORE_IN_DB:
            return None

        try:
            alert_id = insert_alert(alert, notified_by_mail=mail_sent)
            self.stats['total_db'] += 1
            return alert_id
        except Exception as e:
            print(f" Error guardando alerta en DB: {e}")
            self.stats['total_errors'] += 1
            return None

    def _handle_mail(self, alert: Dict[str, Any]) -> bool:
        """
        Enviar mail para la alerta si corresponde.

        Modo inmediato (ALERT_MAIL_BATCH_SECONDS == 0):
            Envía un mail por cada alerta.
        Modo batch (ALERT_MAIL_BATCH_SECONDS > 0):
            Acumula en buffer; el flush lo hace _flush_mail_batch().

        Args:
            alert (dict): Alerta a notificar.

        Returns:
            bool: True si se envió mail (solo en modo inmediato).
        """
        if not self.mailer.is_enabled():
            return False

        if not self.mailer.should_mail_level(alert.get('level', '')):
            return False

        if config.ALERT_MAIL_BATCH_SECONDS > 0:
            # Modo batch: agregar al buffer
            self._mail_buffer.append(alert)
            return False   # aún no enviado

        # Modo inmediato
        sent = self.mailer.send_alert(alert)
        if sent:
            self.stats['total_mail_sent'] += 1
        else:
            self.stats['total_mail_failed'] += 1
        return sent

    def _flush_mail_batch(self):
        """
        Enviar mail resumen con las alertas acumuladas en el buffer.
        Solo se ejecuta en modo batch (ALERT_MAIL_BATCH_SECONDS > 0).
        """
        if not self._mail_buffer:
            return

        elapsed = time.time() - self._last_batch_sent
        if elapsed < config.ALERT_MAIL_BATCH_SECONDS:
            return

        sent = self.mailer.send_batch(self._mail_buffer)
        count = len(self._mail_buffer)

        if sent:
            self.stats['total_mail_sent'] += count
        else:
            self.stats['total_mail_failed'] += count

        self._mail_buffer.clear()
        self._last_batch_sent = time.time()

    #  Loop principal                                                      

    def _process_alert(self, alert: Dict[str, Any]):
        """
        Despachar una alerta a los tres handlers en orden:
        mail → consola → DB (el orden importa: guardamos si el mail fue ok).
        """
        self.stats['total_received'] += 1

        # 1. Mail 
        mail_sent = self._handle_mail(alert)

        # 2. Consola
        self._handle_console(alert)

        # 3. DB — registra también si se mandó mail
        self._handle_db(alert, mail_sent)

    def run(self):
        """
        Loop principal del Alert Manager.

        1. Crea el FIFO si no existe.
        2. Abre el FIFO en modo no bloqueante.
        3. En cada iteración: lee líneas → parsea → despacha.
        4. Si no hay datos, duerme ALERT_FIFO_POLL_INTERVAL segundos.
        5. Si modo batch: revisa si hay que hacer flush del buffer.
        6. Imprime estadísticas cada 50 alertas.
        """
        self._setup_signals()
        self._ensure_fifo()

        # Inicializar DB (crea tablas si no existen)
        if config.ALERT_STORE_IN_DB:
            init_db()

        if not self._open_fifo():
            print(" No se pudo abrir el FIFO. Abortando.")
            return

        self.stats['started_at'] = time.time()

        self._print_banner()

        while self.running:
            try:
                lines = self._read_lines()

                if not lines:
                    # Modo batch: verificar si hay que hacer flush
                    if config.ALERT_MAIL_BATCH_SECONDS > 0:
                        self._flush_mail_batch()
                    time.sleep(config.ALERT_FIFO_POLL_INTERVAL)
                    continue

                for line in lines:
                    if not self.running:
                        break
                    alert = self._parse_alert(line)
                    if alert:
                        self._process_alert(alert)

                # Flush batch si corresponde
                if config.ALERT_MAIL_BATCH_SECONDS > 0:
                    self._flush_mail_batch()

                # Stats cada 50 alertas
                if self.stats['total_received'] % 50 == 0:
                    self._print_stats()

            except Exception as e:
                print(f" Error inesperado en loop principal: {e}")
                traceback.print_exc()
                self.stats['total_errors'] += 1
                time.sleep(1)

        # Flush final del buffer batch antes de salir
        if config.ALERT_MAIL_BATCH_SECONDS > 0 and self._mail_buffer:
            print(f" Enviando {len(self._mail_buffer)} alertas pendientes en buffer...")
            self._flush_mail_batch()

        self._close_fifo()
        self._print_stats()
        print(" Alert Manager detenido.")

    #  Helpers de presentación                                             

    def _print_banner(self):
        """Imprimir banner de inicio."""
        bold  = _COLORS['BOLD']
        reset = _COLORS['RESET']
        dim   = _COLORS['DIM']

        print("\n" + "="*60)
        print(f"{bold} Alert Manager iniciado{reset}")
        print("="*60)
        print(f" FIFO:         {self.fifo_path}")
        print(f" Niveles:      {', '.join(config.ALERT_LEVELS)}")
        print(f" Guardar DB:   {'✓' if config.ALERT_STORE_IN_DB else '✗'}")
        print(f" Consola:      {'✓' if config.ALERT_PRINT_TO_CONSOLE else '✗'}")

        if self.mailer.is_enabled():
            batch = config.ALERT_MAIL_BATCH_SECONDS
            modo  = f"batch cada {batch}s" if batch > 0 else "inmediato"
            print(f" Mail:         ✓ ({modo}) → {', '.join(config.ALERT_MAIL_TO)}")
            print(f" Mail niveles: {', '.join(config.ALERT_MAIL_LEVELS)}")
        else:
            print(f" Mail:         ✗ (deshabilitado o sin configurar)")

        print(f"\n{dim} Presioná Ctrl+C para detener{reset}")
        print("="*60 + "\n")

    def _print_stats(self):
        """Imprimir estadísticas actuales."""
        elapsed = time.time() - (self.stats['started_at'] or time.time())
        rate = (
            self.stats['total_received'] / elapsed
            if elapsed > 0 else 0
        )
        print(
            f"\n Estadísticas:"
            f"  Recibidas: {self.stats['total_received']}"
            f"  |  DB: {self.stats['total_db']}"
            f"  |  Mails OK: {self.stats['total_mail_sent']}"
            f"  |  Mails fail: {self.stats['total_mail_failed']}"
            f"  |  Errores: {self.stats['total_errors']}"
            f"  |  Rate: {rate:.2f}/seg\n"
        )
