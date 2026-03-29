"""
Configurações centralizadas do sistema.
Carrega variáveis de ambiente do arquivo .env
"""

from pydantic_settings import BaseSettings
from functools import lru_cache