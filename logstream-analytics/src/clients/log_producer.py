#!/usr/bin/env python3
# src/clients/log_producer.py
"""
LogProducer - Clase que genera y envía logs sintéticos.

Esta clase puede ser importada y usada en otros módulos.
"""

import socket
import json
import time
import random
import struct
from datetime import datetime
import sys

# ============================================
# PLANTILLAS DE MENSAJES
# ============================================

LOG_TEMPLATES = {
    'webapp': {
        'INFO': [
            'Usuario {user_id} inició sesión',
            'Página {page} cargada en {ms}ms',
            'Solicitud GET /api/users exitosa',
            'Cache hit para recurso {resource}',
            'Sesión renovada para usuario {user_id}',
        ],
        'WARNING': [
            'Tiempo de respuesta alto: {ms}ms',
            'Rate limit alcanzado para IP {ip}',
            'Cache miss para recurso {resource}',
            'Solicitud retry #{retry}',
            'Memoria en {pct}% de uso',
        ],
        'ERROR': [
            'Error al conectar a base de datos: timeout',
            'Usuario {user_id} no encontrado',
            'Error 500: Internal server error',
            'Falló autenticación para usuario {user_id}',
            'Endpoint /api/{endpoint} no disponible',
        ],
        'CRITICAL': [
            'Base de datos no responde hace {seconds} segundos',
            'Sistema sin memoria disponible',
            'Servidor web no puede aceptar más conexiones',
            'Disco de logs lleno al {pct}%',
        ]
    },
    
    'database': {
        'INFO': [
            'Query ejecutado en {ms}ms',
            'Conexión establecida desde {ip}',
            'Índice usado: {index}',
            'Transacción completada',
            'Backup iniciado correctamente',
        ],
        'WARNING': [
            'Query lento: {ms}ms',
            'Pool de conexiones al {pct}% de capacidad',
            'Caché de query lleno',
            'Tabla {table} sin índice',
        ],
        'ERROR': [
            'Deadlock detectado en transacción',
            'Connection pool exhausted',
            'Query timeout: {query}',
            'Lock wait timeout exceeded',
            'Fallo en replica de tabla {table}',
        ],
        'CRITICAL': [
            'Disco lleno: {pct}% usado',
            'Réplica fuera de sincronización',
            'Corrupción detectada en tabla {table}',
            'Sistema de backup falló',
        ]
    },
    
    'api': {
        'INFO': [
            'Endpoint /api/{endpoint} llamado',
            'Token validado correctamente',
            'Respuesta 200 OK en {ms}ms',
            'Request procesado exitosamente',
        ],
        'WARNING': [
            'API key {key} cerca del límite',
            'Respuesta lenta: {ms}ms',
            'Retry de request automático',
            'Rate limit warning para IP {ip}',
        ],
        'ERROR': [
            '503 Service Unavailable',
            'Backend service no responde',
            'Error de validación en payload',
            'Token expirado para usuario {user_id}',
            '429 Too Many Requests',
        ],
        'CRITICAL': [
            'Todos los backends caídos',
            'Circuit breaker activado',
            'Sistema en modo de emergencia',
            'Gateway timeout generalizado',
        ]
    }
}

# ============================================
# CLASE LOG PRODUCER
# ============================================

class LogProducer:
    """
    Generador de logs sintéticos que envía al Log Server.
    Soporta IPv4 e IPv6.
    
    Example:
        producer = LogProducer(
            source='webapp',
            server_host='127.0.0.1',
            server_port=9000,
            rate=5,
            error_rate=0.05,
            anomaly_rate=0.01
        )
        producer.run()
    """
    
    def __init__(self, source, server_host, server_port, rate, error_rate, anomaly_rate):
        """
        Args:
            source (str): Tipo de fuente ('webapp', 'database', 'api')
            server_host (str): IP del Log Server (IPv4 o IPv6)
            server_port (int): Puerto del Log Server
            rate (int): Logs por segundo a generar
            error_rate (float): Probabilidad de generar ERROR (0.0-1.0)
            anomaly_rate (float): Probabilidad de generar CRITICAL (0.0-1.0)
        """
        self.source = source
        self.server_host = server_host
        self.server_port = server_port
        self.rate = rate
        self.error_rate = error_rate
        self.anomaly_rate = anomaly_rate
        
        self.socket = None
        self.running = True
        
        # Validar source
        if source not in LOG_TEMPLATES:
            raise ValueError(
                f"Source inválido: {source}. "
                f"Válidos: {', '.join(LOG_TEMPLATES.keys())}"
            )
    
    def connect(self):
        """
        Conectar al Log Server vía TCP.
        Auto-detecta IPv4 o IPv6.
        
        Returns:
            bool: True si conexión exitosa
        """
        try:
            # Resolver hostname/IP (soporta IPv4 e IPv6)
            addr_info = socket.getaddrinfo(
                self.server_host, 
                self.server_port, 
                socket.AF_UNSPEC,      # IPv4 o IPv6
                socket.SOCK_STREAM     # TCP
            )
            
            # Intentar conectar
            for family, socktype, proto, canonname, sockaddr in addr_info:
                try:
                    self.socket = socket.socket(family, socktype, proto)
                    self.socket.connect(sockaddr)
                    
                    # Conexión exitosa
                    family_name = "IPv6" if family == socket.AF_INET6 else "IPv4"
                    print(f" Conectado a Log Server ({family_name}): {sockaddr[0]}:{sockaddr[1]}")
                    return True
                    
                except Exception:
                    if self.socket:
                        self.socket.close()
                    continue
            
            print(f" No se pudo conectar a {self.server_host}:{self.server_port}")
            return False
            
        except socket.gaierror as e:
            print(f" No se pudo resolver: {self.server_host} ({e})")
            return False
        except Exception as e:
            print(f" Error al conectar: {e}")
            return False
    
    def generate_log(self):
        """
        Generar un log sintético.
        
        Returns:
            dict: Log con timestamp, source, level, message, metadata
        """
        # Decidir nivel
        rand = random.random()
        
        if rand < self.anomaly_rate:
            level = 'CRITICAL'
        elif rand < (self.anomaly_rate + self.error_rate):
            level = 'ERROR'
        elif rand < (self.anomaly_rate + self.error_rate + 0.15):
            level = 'WARNING'
        else:
            level = 'INFO'
        
        # Elegir plantilla
        templates = LOG_TEMPLATES[self.source][level]
        message_template = random.choice(templates)
        
        # Rellenar variables
        message = message_template.format(
            user_id=random.randint(1000, 9999),
            page=random.choice(['home', 'dashboard', 'profile', 'settings', 'reports']),
            ms=random.randint(50, 2000),
            ip=f"192.168.1.{random.randint(1, 255)}",
            resource=random.choice(['user_data', 'config', 'cache_key', 'session']),
            retry=random.randint(1, 5),
            seconds=random.randint(30, 300),
            index=random.choice(['idx_users', 'idx_logs', 'idx_sessions', 'idx_events']),
            pct=random.randint(70, 95),
            query=random.choice(['SELECT * FROM users', 'UPDATE logs SET', 'DELETE FROM sessions']),
            table=random.choice(['users', 'logs', 'sessions', 'events']),
            endpoint=random.choice(['users', 'auth', 'data', 'status', 'metrics']),
            key=f"key_{random.randint(1000, 9999)}"
        )
        
        # Construir log
        return {
            'timestamp': datetime.now().isoformat(),
            'source': self.source,
            'level': level,
            'message': message,
            'metadata': {
                'producer_id': f"{self.source}-{id(self)}",
                'server': f"{self.server_host}:{self.server_port}",
            }
        }
    
    def send_log(self, log):
        """
        Enviar log usando protocolo: [4 bytes length][JSON payload]
        
        Args:
            log (dict): Log a enviar
            
        Returns:
            bool: True si enviado exitosamente
        """
        try:
            # Serializar
            log_json = json.dumps(log)
            log_bytes = log_json.encode('utf-8')
            
            # Protocolo
            length = len(log_bytes)
            length_bytes = struct.pack('>I', length)
            
            # Enviar
            self.socket.sendall(length_bytes + log_bytes)
            return True
            
        except (BrokenPipeError, ConnectionResetError):
            print(" Conexión perdida con el servidor")
            return False
        except Exception as e:
            print(f" Error enviando log: {e}")
            return False
    
    def run(self):
        """Loop principal: generar y enviar logs continuamente."""
        
        if not self.connect():
            return
        
        print(f"\n Generando logs de '{self.source}' a {self.rate} logs/seg")
        print(f"   Error rate: {self.error_rate*100:.1f}%")
        print(f"   Anomaly rate: {self.anomaly_rate*100:.1f}%")
        print(f"   Presiona Ctrl+C para detener\n")
        
        interval = 1.0 / self.rate
        logs_sent = 0
        start_time = time.time()
        
        try:
            while self.running:
                log = self.generate_log()
                
                if self.send_log(log):
                    logs_sent += 1
                    
                    # Mostrar con color
                    color = {
                        'INFO': '\033[94m',
                        'WARNING': '\033[93m',
                        'ERROR': '\033[91m',
                        'CRITICAL': '\033[95m'
                    }.get(log['level'], '')
                    reset = '\033[0m'
                    
                    print(f"{color}[{log['level']:8s}]{reset} {log['message']}")
                    
                    # Stats cada 10 logs
                    if logs_sent % 10 == 0:
                        elapsed = time.time() - start_time
                        actual_rate = logs_sent / elapsed if elapsed > 0 else 0
                        print(f"\n Logs enviados: {logs_sent} | Rate: {actual_rate:.2f}/seg\n")
                else:
                    # Reconectar
                    print(" Intentando reconectar...")
                    time.sleep(2)
                    if not self.connect():
                        print(" No se pudo reconectar. Abortando.")
                        break
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n Detenido por usuario (Ctrl+C)")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cerrar conexión limpiamente."""
        if self.socket:
            try:
                self.socket.close()
                print(" Conexión cerrada")
            except:
                pass