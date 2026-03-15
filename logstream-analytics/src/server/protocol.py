"""
Protocolo de comunicación TCP para LogStream.

Protocolo: [4 bytes longitud (big-endian)][JSON payload UTF-8]
"""

import struct
import json
import asyncio


async def read_message(reader):
    """
    Leer un mensaje usando el protocolo [longitud][payload].
    
    Args:
        reader: asyncio.StreamReader
        
    Returns:
        dict: Mensaje parseado como JSON, o None si conexión cerrada
        
    Raises:
        ValueError: Si el mensaje es inválido
        json.JSONDecodeError: Si el JSON es inválido
    """
    try:
        # Leer 4 bytes de longitud
        length_bytes = await reader.readexactly(4)
        
        # Convertir a entero (big-endian)
        length = struct.unpack('>I', length_bytes)[0]
        
        # Validar longitud razonable (máx 10MB)
        if length > 10 * 1024 * 1024:
            raise ValueError(f"Mensaje demasiado grande: {length} bytes")
        
        if length == 0:
            raise ValueError("Longitud de mensaje es 0")
        
        # Leer payload
        payload_bytes = await reader.readexactly(length)
        
        # Decodificar UTF-8
        payload_str = payload_bytes.decode('utf-8')
        
        # Parsear JSON
        message = json.loads(payload_str)
        
        return message
        
    except asyncio.IncompleteReadError:
        # Cliente cerró conexión
        return None
    except Exception as e:
        raise


async def send_message(writer, message):
    """
    Enviar un mensaje usando el protocolo [longitud][payload].
    
    Args:
        writer: asyncio.StreamWriter
        message: dict o string a enviar
    """
    # Convertir a JSON si es dict
    if isinstance(message, dict):
        payload_str = json.dumps(message)
    else:
        payload_str = str(message)
    
    # Convertir a bytes
    payload_bytes = payload_str.encode('utf-8')
    
    # Calcular longitud
    length = len(payload_bytes)
    length_bytes = struct.pack('>I', length)
    
    # Enviar [longitud][payload]
    writer.write(length_bytes + payload_bytes)
    await writer.drain()


def validate_log_entry(log):
    """
    Validar que el log tenga el formato correcto.
    
    Args:
        log (dict): Log a validar
        
    Returns:
        tuple: (bool, str) - (es_válido, mensaje_error)
    """
    # Verificar que sea un dict
    if not isinstance(log, dict):
        return False, "Log debe ser un objeto JSON"
    
    # Campos obligatorios
    required_fields = ['timestamp', 'source', 'level', 'message']
    
    for field in required_fields:
        if field not in log:
            return False, f"Falta campo obligatorio: {field}"
    
    # Validar nivel
    valid_levels = ['INFO', 'WARNING', 'ERROR', 'CRITICAL']
    if log['level'] not in valid_levels:
        return False, f"Nivel inválido: {log['level']}. Válidos: {valid_levels}"
    
    # Validar source
    valid_sources = ['webapp', 'database', 'api']
    if log['source'] not in valid_sources:
        return False, f"Source inválido: {log['source']}. Válidos: {valid_sources}"
    
    return True, "OK"