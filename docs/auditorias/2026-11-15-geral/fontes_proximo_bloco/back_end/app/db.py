"""Mantem o import usado pelas rotas, sem duplicar configuracao de banco."""
from services.database import get_db_connection

__all__ = ["get_db_connection"]