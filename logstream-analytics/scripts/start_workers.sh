#!/bin/bash
# scripts/start_workers.sh
# Script para iniciar workers de Celery

echo "============================================================"
echo " INICIANDO CELERY WORKERS"
echo "============================================================"

# Ir a la raíz del proyecto
cd "$(dirname "$0")/.." || exit

# Activar venv si existe
if [ -d "venv" ]; then
    echo " Activando entorno virtual..."
    source venv/bin/activate
fi

# Verificar que Celery esté instalado
if ! command -v celery &> /dev/null; then
    echo " Celery no está instalado"
    echo "   Ejecuta: pip install celery redis"
    exit 1
fi

# Número de workers (default: 4)
WORKERS=${1:-4}

echo "  Workers: $WORKERS"
echo " Broker: Redis (localhost:6379)"
echo " Cola: log_processing"
echo ""
echo " Presiona Ctrl+C para detener"
echo "============================================================"
echo ""

# Iniciar workers
celery -A src.workers.celery_config worker \
    --loglevel=info \
    --concurrency=$WORKERS \
    --pool=prefork \
    --queues=log_processing \
    --hostname=worker@%h

echo ""
echo " Workers detenidos"
