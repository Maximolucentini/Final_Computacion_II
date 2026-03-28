# src/core/db.py
"""
Capa de acceso a la base de datos SQLite
"""

import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

from .config import config
from .redis_client import get_redis_client


def init_db(db_path: Optional[str] = None):
    """
    Inicializar base de datos SQLite: crear directorio, tablas e índices.
    """
    path = Path(db_path) if db_path else config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    cursor = conn.cursor()

    # Tabla principal de logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL,
            source      TEXT    NOT NULL,
            level       TEXT    NOT NULL,
            message     TEXT    NOT NULL,
            metadata    TEXT,
            ingested_at TEXT    NOT NULL,
            client_ip   TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Índices para búsquedas rápidas
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_timestamp  ON logs(timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_source     ON logs(source)",
        "CREATE INDEX IF NOT EXISTS idx_level      ON logs(level)",
        "CREATE INDEX IF NOT EXISTS idx_created_at ON logs(created_at DESC)",
    ]:
        cursor.execute(idx_sql)

    # Tabla de estadísticas agregadas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            date       TEXT    NOT NULL,
            source     TEXT    NOT NULL,
            level      TEXT    NOT NULL,
            count      INTEGER DEFAULT 0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, source, level)
        )
    """)

    conn.commit()
    conn.close()

    print(f"   Base de datos inicializada: {path}")
    print(f"   Modo: WAL (Write-Ahead Logging)")
    print(f"   Tablas: logs, stats")


@contextmanager
def get_db_read():
    """Context manager para conexiones de solo lectura."""
    conn = None
    try:
        conn = sqlite3.connect(config.DB_PATH, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        if conn:
            conn.close()


@contextmanager
def get_db_write():
    """
    Context manager para escrituras en SQLite.
    Adquiere un lock distribuido en Redis antes de escribir
    para evitar conflictos entre workers Celery.
    """
    redis_client = get_redis_client()
    lock = None
    conn = None

    try:
        lock = redis_client.lock(
            'db_write_lock',
            timeout=config.DB_LOCK_TIMEOUT,
            blocking=True,
            blocking_timeout=config.DB_LOCK_BLOCKING_TIMEOUT
        )

        acquired = lock.acquire()
        if not acquired:
            raise TimeoutError(
                f"No se pudo adquirir lock de escritura "
                f"en {config.DB_LOCK_BLOCKING_TIMEOUT}s"
            )

        conn = sqlite3.connect(config.DB_PATH, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")

        yield conn

        conn.commit()

    except Exception:
        if conn:
            conn.rollback()
        raise

    finally:
        if conn:
            conn.close()
        if lock and lock.owned():
            lock.release()


def insert_log(log: Dict[str, Any]) -> int:
    """
    Insertar un log procesado en la base de datos.
    """
    with get_db_write() as conn:
        cursor = conn.cursor()

        metadata_json = None
        if log.get('metadata'):
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

        return cursor.lastrowid


def query_logs(
    source: Optional[str] = None,
    level: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Consultar logs con filtros opcionales.

    Args:
        source (str, optional): Filtrar por fuente (webapp, database, api).
        level (str, optional): Filtrar por nivel (INFO, WARNING, ERROR, CRITICAL).
        start_date (str, optional): Timestamp ISO mínimo.
        end_date (str, optional): Timestamp ISO máximo.
        limit (int): Máximo de resultados (default 100).
        offset (int): Desplazamiento para paginación (default 0).

    Returns:
        List[dict]: Lista de logs como diccionarios.
    """
    with get_db_read() as conn:
        cursor = conn.cursor()

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

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()

        logs = []
        for row in rows:
            log = dict(row)
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
    """
    Obtener estadísticas agregadas de logs.

    Returns:
        dict: total, by_level, by_source, by_level_and_source
    """
    with get_db_read() as conn:
        cursor = conn.cursor()

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

        cursor.execute(
            f"SELECT COUNT(*) FROM logs {where_clause}", params
        )
        total = cursor.fetchone()[0]

        cursor.execute(
            f"SELECT level, COUNT(*) FROM logs {where_clause} GROUP BY level",
            params
        )
        by_level = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute(
            f"SELECT source, COUNT(*) FROM logs {where_clause} GROUP BY source",
            params
        )
        by_source = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute(
            f"""SELECT source, level, COUNT(*)
                FROM logs {where_clause}
                GROUP BY source, level""",
            params
        )
        by_level_and_source: Dict[str, Dict[str, int]] = {}
        for source, level, count in cursor.fetchall():
            by_level_and_source.setdefault(source, {})[level] = count

        return {
            'total': total,
            'by_level': by_level,
            'by_source': by_source,
            'by_level_and_source': by_level_and_source
        }


def get_db_info() -> Dict[str, Any]:
    """
    Información de diagnóstico sobre la base de datos.

    Returns:
        dict: path, exists, size_mb, total_logs, wal_mode
    """
    path = config.DB_PATH
    info: Dict[str, Any] = {
        'path': str(path),
        'exists': path.exists(),
        'size_mb': 0,
        'total_logs': 0,
        'wal_mode': False
    }

    if path.exists():
        info['size_mb'] = round(path.stat().st_size / (1024 * 1024), 2)

        with get_db_read() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM logs")
            info['total_logs'] = cursor.fetchone()[0]

            cursor.execute("PRAGMA journal_mode")
            info['wal_mode'] = (cursor.fetchone()[0].upper() == 'WAL')

    return info
