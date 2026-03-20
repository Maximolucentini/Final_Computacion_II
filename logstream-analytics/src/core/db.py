# src/core/db.py
import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

from .redis_client import get_redis_client


# Configuración
DB_PATH = Path(__file__).parent.parent.parent / 'data' / 'logstream.db'
LOCK_TIMEOUT = 10  
LOCK_BLOCKING_TIMEOUT = 15  


def init_db(db_path: Optional[str] = None):
    """
    Inicializar base de datos SQLite.
    """
    global DB_PATH
    
    if db_path:
        DB_PATH = Path(db_path)
    
    # Crear directorio si no existe
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # Conectar y crear tablas
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")  
    conn.execute("PRAGMA synchronous=NORMAL")  
    
    cursor = conn.cursor()
    
    # Tabla principal de logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            source TEXT NOT NULL,
            level TEXT NOT NULL,
            message TEXT NOT NULL,
            metadata TEXT,
            ingested_at TEXT NOT NULL,
            client_ip TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Índices para búsquedas rápidas
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_timestamp 
        ON logs(timestamp)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_source 
        ON logs(source)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_level 
        ON logs(level)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_created_at 
        ON logs(created_at DESC)
    """)
    
    # Tabla de estadísticas (para queries rápidas)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            source TEXT NOT NULL,
            level TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, source, level)
        )
    """)
    
    conn.commit()
    conn.close()
    
    print(f"   Base de datos inicializada: {DB_PATH}")
    print(f"   Modo: WAL (Write-Ahead Logging)")
    print(f"   Tablas: logs, stats")


@contextmanager
def get_db_read():
    
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row  
        yield conn
    finally:
        if conn:
            conn.close()


@contextmanager
def get_db_write():
    
    redis_client = get_redis_client()
    lock = None
    conn = None
    
    try:
        # Adquirir lock de Redis
        lock = redis_client.lock(
            'db_write_lock',
            timeout=LOCK_TIMEOUT,
            blocking=True,
            blocking_timeout=LOCK_BLOCKING_TIMEOUT
        )
        
        acquired = lock.acquire()
        
        if not acquired:
            raise TimeoutError(
                f"No se pudo adquirir lock de escritura en {LOCK_BLOCKING_TIMEOUT}s"
            )
        
        # Conectar a DB
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        
        yield conn
        
        # Commit automático si no hubo excepciones
        conn.commit()
        
    except Exception as e:
        if conn:
            conn.rollback()
        raise
    finally:
        # Cerrar conexión
        if conn:
            conn.close()
        
        # Liberar lock
        if lock and lock.owned():
            lock.release()


def insert_log(log: Dict[str, Any]) -> int:
    
    with get_db_write() as conn:
        cursor = conn.cursor()
        
        # Convertir metadata a JSON si existe
        metadata_json = None
        if 'metadata' in log and log['metadata']:
            metadata_json = json.dumps(log['metadata'])
        
        cursor.execute("""
            INSERT INTO logs (
                timestamp, source, level, message, 
                metadata, ingested_at, client_ip
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            log.get('timestamp'),
            log.get('source'),
            log.get('level'),
            log.get('message'),
            metadata_json,
            log.get('ingested_at'),
            log.get('client_ip')
        ))
        
        log_id = cursor.lastrowid
        return log_id


def query_logs(
    source: Optional[str] = None,
    level: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]:
    
    with get_db_read() as conn:
        cursor = conn.cursor()
        
        # Construir query dinámicamente
        query = "SELECT * FROM logs WHERE 1=1"
        params = []
        
        if source:
            query += " AND source = ?"
            params.append(source)
        
        if level:
            query += " AND level = ?"
            params.append(level)
        
        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date)
        
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date)
        
        # Ordenar por más reciente primero
        query += " ORDER BY created_at DESC"
        
        # Paginación
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        # Convertir a lista de diccionarios
        logs = []
        for row in rows:
            log = dict(row)
            
            # Parsear metadata JSON
            if log.get('metadata'):
                try:
                    log['metadata'] = json.loads(log['metadata'])
                except json.JSONDecodeError:
                    log['metadata'] = None
            
            logs.append(log)
        
        return logs


def get_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    
    with get_db_read() as conn:
        cursor = conn.cursor()
        
        # Query base
        where_clause = ""
        params = []
        
        if start_date or end_date:
            conditions = []
            if start_date:
                conditions.append("timestamp >= ?")
                params.append(start_date)
            if end_date:
                conditions.append("timestamp <= ?")
                params.append(end_date)
            where_clause = "WHERE " + " AND ".join(conditions)
        
        # Total de logs
        cursor.execute(f"SELECT COUNT(*) as total FROM logs {where_clause}", params)
        total = cursor.fetchone()[0]
        
        # Por nivel
        cursor.execute(f"""
            SELECT level, COUNT(*) as count 
            FROM logs {where_clause}
            GROUP BY level
        """, params)
        by_level = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Por source
        cursor.execute(f"""
            SELECT source, COUNT(*) as count 
            FROM logs {where_clause}
            GROUP BY source
        """, params)
        by_source = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Por source y nivel
        cursor.execute(f"""
            SELECT source, level, COUNT(*) as count 
            FROM logs {where_clause}
            GROUP BY source, level
        """, params)
        
        by_level_and_source = {}
        for row in cursor.fetchall():
            source, level, count = row
            if source not in by_level_and_source:
                by_level_and_source[source] = {}
            by_level_and_source[source][level] = count
        
        return {
            'total': total,
            'by_level': by_level,
            'by_source': by_source,
            'by_level_and_source': by_level_and_source
        }


def get_db_info() -> Dict[str, Any]:
    
    info = {
        'path': str(DB_PATH),
        'exists': DB_PATH.exists(),
        'size_mb': 0,
        'total_logs': 0,
        'wal_mode': False
    }
    
    if DB_PATH.exists():
        # Tamaño del archivo
        info['size_mb'] = round(DB_PATH.stat().st_size / (1024 * 1024), 2)
        
        # Total de logs
        with get_db_read() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM logs")
            info['total_logs'] = cursor.fetchone()[0]
            
            # Verificar WAL mode
            cursor.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            info['wal_mode'] = (mode.upper() == 'WAL')
    
    return info
