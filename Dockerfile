# ============================================================
# Dockerfile — Webhook Dashboard SASI
# Imagem base leve com Python 3.12
# ============================================================

FROM python:3.12-slim

# Variáveis de ambiente para Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Instalar dependências do sistema (necessárias para psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código da aplicação
COPY . .

# Porta padrão da API
EXPOSE 8000

# Comando padrão (API)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
