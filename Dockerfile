# 🐳 PDF2JPG Service v2.0 - Dockerfile Optimizado para Producción
# Multi-stage build para menor tamaño final

# =====================================================================
# STAGE 1: Build dependencies
# =====================================================================
FROM python:3.11-slim as builder

# Variables de entorno para build
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Instalar dependencias de build
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    libjpeg-dev \
    libpng-dev \
    libwebp-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Crear directorio temporal para build
WORKDIR /build

# Copiar requirements y pre-instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --user -r requirements.txt

# =====================================================================
# STAGE 2: Production runtime
# =====================================================================
FROM python:3.11-slim

# Metadata del contenedor
LABEL maintainer="Tu Equipo <email@ejemplo.com>"
LABEL description="PDF2JPG Conversion Service v2.0"
LABEL version="2.0.0"

# Variables de entorno para runtime
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080
ENV IMAGE_QUALITY=95
ENV IMAGE_DPI=300
ENV TEMP_DIR=/tmp
ENV RATE_LIMIT_PER_MINUTE=10

# Instalar solo las librerías runtime necesarias
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    libjpeg62-turbo \
    libpng16-16 \
    libwebp7 \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

# Crear usuario no-root para seguridad
RUN useradd --create-home --shell /bin/bash --uid 1000 appuser

# Crear directorio de aplicación
WORKDIR /app

# Copiar dependencias desde build stage
COPY --from=builder /root/.local /home/appuser/.local

# Copiar código de aplicación
COPY app.py .

# Configurar permisos y ownership
RUN chown -R appuser:appuser /app && \
    mkdir -p /tmp/pdf2jpg && \
    chown -R appuser:appuser /tmp/pdf2jpg

# Cambiar a usuario no-root
USER appuser

# Agregar binarios locales al PATH
ENV PATH=/home/appuser/.local/bin:$PATH

# Health check para monitoreo
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:$PORT/health', timeout=5)"

# Exponer puerto
EXPOSE $PORT

# Comando de inicio con gunicorn optimizado para producción
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 300 --worker-class sync --worker-connections 1000 --max-requests 1000 --max-requests-jitter 100 --access-logfile - --error-logfile - app:app"]
