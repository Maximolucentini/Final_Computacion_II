#!/usr/bin/env python3
# scripts/consume_logs.py
"""
Script que consume logs de Redis (log_queue) y los envía a workers Celery.

Este script hace de "puente" entre Redis y Celery:
1. Saca logs de 'log_queue' (donde el Server los puso)
2. Los envía a workers Celery para procesarlos
3. Los workers guardan en SQLite y manejan alertas

Uso:
    python3 scripts/consume_logs.py
    python3 scripts/consume_logs.py --queue log_queue --batch-size 10
"""

import sys
import time
import signal
from pathlib import Path

# Agregar src/ al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.redis_client import get_redis_client
from src.workers.tasks import process_log_task
import argparse


class LogConsumer:
    """
    Consumidor de logs desde Redis.
    
    Saca logs de la cola Redis y los envía a workers Celery.
    """
    
    def __init__(self, queue_name='log_queue', batch_size=10):
        """
        Args:
            queue_name (str): Nombre de la cola en Redis
            batch_size (int): Cuántos logs procesar por lote
        """
        self.queue_name = queue_name
        self.batch_size = batch_size
        self.redis_client = None
        self.running = True
        
        # Stats
        self.stats = {
            'consumed': 0,
            'sent_to_workers': 0,
            'errors': 0,
            'started_at': None
        }
    
    def connect_redis(self):
        """Conectar a Redis."""
        try:
            self.redis_client = get_redis_client()
            print(f" Conectado a Redis")
            return True
        except Exception as e:
            print(f" Error conectando a Redis: {e}")
            return False
    
    def consume(self):
        """
        Consumir logs de Redis y enviarlos a workers.
        Loop infinito hasta Ctrl+C.
        """
        if not self.connect_redis():
            return
        
        print("="*60)
        print(" LOG CONSUMER")
        print("="*60)
        print(f" Cola Redis: {self.queue_name}")
        print(f" Batch size: {self.batch_size}")
        print(f"  Workers Celery: Procesarán los logs")
        print("\n Consumiendo logs... Presiona Ctrl+C para detener\n")
        print("="*60 + "\n")
        
        self.stats['started_at'] = time.time()
        
        # Manejar Ctrl+C
        signal.signal(signal.SIGINT, self.handle_shutdown)
        
        while self.running:
            try:
                # Obtener lote de logs
                logs = self.get_batch()
                
                if not logs:
                    # No hay logs, esperar un poco
                    time.sleep(0.1)
                    continue
                
                # Enviar cada log a workers Celery
                for log_json in logs:
                    try:
                        # Enviar tarea asíncrona a worker
                        result = process_log_task.delay(log_json)
                        
                        self.stats['consumed'] += 1
                        self.stats['sent_to_workers'] += 1
                        
                        # Mostrar cada 10 logs
                        if self.stats['consumed'] % 10 == 0:
                            self.print_stats()
                        
                    except Exception as e:
                        print(f" Error enviando log a worker: {e}")
                        self.stats['errors'] += 1
            
            except Exception as e:
                print(f" Error en loop de consumo: {e}")
                self.stats['errors'] += 1
                time.sleep(1)
        
        print("\n Deteniendo consumer...")
        self.print_stats()
        print(" Consumer detenido")
    
    def get_batch(self):
        """
        Obtener lote de logs de Redis.
        
        """
        logs = []
        
        for _ in range(self.batch_size):
            # Sacar log de la cola 
            log_json = self.redis_client.lpop(self.queue_name)
            
            if log_json is None:
                break  # No hay más logs
            
            # Decodificar bytes a string
            if isinstance(log_json, bytes):
                log_json = log_json.decode('utf-8')
            
            logs.append(log_json)
        
        return logs
    
    def print_stats(self):
        """Imprimir estadísticas."""
        elapsed = time.time() - self.stats['started_at']
        rate = self.stats['consumed'] / elapsed if elapsed > 0 else 0
        
        # Ver cuántos hay en cola
        queue_len = self.redis_client.llen(self.queue_name)
        
        print(f" Consumidos: {self.stats['consumed']} | "
              f"Enviados a workers: {self.stats['sent_to_workers']} | "
              f"En cola: {queue_len} | "
              f"Rate: {rate:.2f}/seg")
    
    def handle_shutdown(self, signum, frame):
        """Manejar señal de apagado (Ctrl+C)."""
        print("\n\n  Señal de apagado recibida...")
        self.running = False


def main():
    
    parser = argparse.ArgumentParser(
        description='Consumir logs de Redis y enviarlos a workers Celery'
    )
    
    parser.add_argument(
        '--queue',
        default='log_queue',
        help='Nombre de la cola en Redis (default: log_queue)'
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='Cuántos logs procesar por lote (default: 10)'
    )
    
    args = parser.parse_args()
    
    # Crear consumer
    consumer = LogConsumer(
        queue_name=args.queue,
        batch_size=args.batch_size
    )
    
    # Iniciar consumo
    consumer.consume()


if __name__ == '__main__':
    main()
