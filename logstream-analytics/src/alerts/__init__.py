# src/alerts/__init__.py
"""
Módulo de alertas.
"""

from .alert_manager import AlertManager
from .mailer import Mailer

__all__ = ['AlertManager', 'Mailer']
