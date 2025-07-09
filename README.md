# 🚀 PDF2JPG Service v2.0

**Servicio de conversión de PDF a imágenes JPG** optimizado para producción, con seguridad integrada y múltiples métodos de entrada.

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new)

## 📋 Características

- ✅ **Conversión rápida** PDF → JPG → ZIP
- 🔐 **Seguridad integrada** con API Keys y rate limiting  
- 📥 **Múltiples métodos de entrada**: Form-data, URL, Supabase Storage, Raw data
- 🛡️ **Validaciones robustas** de archivos y límites de seguridad
- 🐳 **Docker optimizado** para Railway y otros providers
- 📊 **Logging detallado** con IDs de conversión únicos
- ⚡ **Alto rendimiento** con PyMuPDF y Pillow optimized

## 🚀 Deploy Rápido

### 1. **Railway (Recomendado)**
1. Haz fork de este repositorio
2. Conecta tu repo a Railway
3. Configura las variables de entorno (ver abajo)
4. ¡Deploy automático!

### 2. **Docker Local**
```bash
# Construir imagen
docker build -t pdf2jpg-service .

# Ejecutar con variables básicas
docker run -p 8080:8080 \
  -e API_KEY=mi-clave-secreta-2024 \
  pdf2jpg-service
```

### 3. **Python Local**
```bash
# Instalar dependencias
pip install -r requirements.txt

# Configurar variables
export API_KEY=mi-clave-secreta-2024
export PORT=8080

# Ejecutar
python app.py
```

## ⚙️ Variables de Entorno

### 🔐 **Seguridad (Recomendadas)**
```bash
# API Key para autenticación (OBLIGATORIO para producción)
API_KEY=tu-clave-super-secreta-aqui-2024

# IPs autorizadas (opcional, separadas por coma)
ALLOWED_IPS=192.168.1.100,203.0.113.45

# Rate limiting por IP (opcional)
RATE_LIMIT_PER_MINUTE=10
```

### 🔧 **Configuración Técnica (Opcionales)**
```bash
# Puerto del servicio
PORT=8080

# Calidad de imágenes JPG (1-100)
IMAGE_QUALITY=95

# DPI de las imágenes generadas
IMAGE_DPI=300

# Directorio temporal
TEMP_DIR=/tmp

# Modo debug
DEBUG=false
```

## 📡 API Endpoints

### 🩺 **Health Check**
```bash
GET /health
```
**Respuesta:**
```json
{
  "status": "healthy",
  "service": "PDF2JPG Converter",
  "version": "2.0.0",
  "security": {
    "api_key_enabled": true,
    "rate_limit_per_minute": 10
  },
  "limits": {
    "max_file_size_mb": 50,
    "max_pages": 100
  }
}
```

### 🔄 **Conversión Principal**
```bash
POST /convert
```

#### **Método 1: Form-data (Upload directo)**
```bash
curl -X POST \
  -H "X-API-Key: tu-api-key" \
  -F "file=@documento.pdf" \
  https://tu-servicio.railway.app/convert
```

#### **Método 2: JSON con URL**
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: tu-api-key" \
  -d '{
    "url": "https://ejemplo.com/documento.pdf"
  }' \
  https://tu-servicio.railway.app/convert
```

#### **Método 3: JSON con Supabase**
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: tu-api-key" \
  -d '{
    "file_id": "uuid-del-archivo",
    "supabase_url": "https://proyecto.supabase.co",
    "service_key": "eyJhbGci...",
    "bucket": "mi-bucket"
  }' \
  https://tu-servicio.railway.app/convert
```

#### **Método 4: API Key en Body (alternativo)**
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "tu-api-key",
    "url": "https://ejemplo.com/documento.pdf"
  }' \
  https://tu-servicio.railway.app/convert
```

### 🎯 **Endpoints Específicos**

#### **Conversión desde URL**
```bash
POST /convert/url
Content-Type: application/json

{
  "url": "https://ejemplo.com/archivo.pdf"
}
```

#### **Conversión desde Supabase**
```bash
POST /convert/supabase
Content-Type: application/json

{
  "file_id": "archivo.pdf",
  "supabase_url": "https://proyecto.supabase.co",
  "service_key": "eyJhbGci...",
  "bucket": "documentos"
}
```

## 🔗 Integración con n8n

### **Configuración en HTTP Request Node:**

**URL:** `https://tu-servicio.railway.app/convert`  
**Method:** `POST`  
**Headers:**
```json
{
  "X-API-Key": "tu-api-key",
  "Content-Type": "application/json"
}
```

**Body:**
```json
{
  "file_id": "{{$json.file_id}}",
  "supabase_url": "https://proyecto.supabase.co",
  "service_key": "eyJhbGci...",
  "bucket": "documentos"
}
```

### **Configuración de Timeout:**
- **Timeout:** 300000 (5 minutos)
- **Response:** Binary data (ZIP file)

## 🛡️ Seguridad

### **Niveles de Protección:**

1. **🟢 Básico:** Solo API Key
   ```bash
   API_KEY=mi-clave-secreta-2024
   ```

2. **🟡 Intermedio:** API Key + Rate Limiting
   ```bash
   API_KEY=mi-clave-secreta-2024
   RATE_LIMIT_PER_MINUTE=5
   ```

3. **🔴 Avanzado:** API Key + Rate Limiting + IP Whitelist
   ```bash
   API_KEY=mi-clave-secreta-2024
   RATE_LIMIT_PER_MINUTE=5
   ALLOWED_IPS=192.168.1.100,203.0.113.45
   ```

### **Mejores Prácticas:**
- ✅ Usar API Keys largas y aleatorias (mínimo 32 caracteres)
- ✅ Rotar API Keys periódicamente
- ✅ Monitorear logs de acceso
- ✅ Configurar rate limiting apropiado para tu uso
- ❌ No commitear API Keys en el código

## 📊 Límites y Especificaciones

| Parámetro | Valor | Configurable |
|-----------|-------|--------------|
| Tamaño máximo de archivo | 50 MB | ❌ |
| Páginas máximas por PDF | 100 | ❌ |
| Calidad JPG | 95 | ✅ |
| DPI de salida | 300 | ✅ |
| Rate limit por defecto | 10/min | ✅ |
| Timeout de descarga | 30s | ❌ |
| Workers Gunicorn | 2 | ❌ |

## 🔧 Desarrollo Local

### **Instalación:**
```bash
# Clonar repositorio
git clone https://github.com/tu-usuario/PDF2JPG-SupabaseService.git
cd PDF2JPG-SupabaseService

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate     # Windows

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables
cp .env.example .env
# Editar .env con tus valores

# Ejecutar en modo desarrollo
python app.py
```

### **Testing:**
```bash
# Test básico de salud
curl http://localhost:8080/health

# Test con archivo local
curl -X POST \
  -H "X-API-Key: test-key" \
  -F "file=@test.pdf" \
  http://localhost:8080/convert \
  --output resultado.zip
```

## 📝 Logs y Monitoreo

### **Formato de Logs:**
```
2024-07-09 17:30:15 - INFO - [abc12345] Iniciando nueva conversión
2024-07-09 17:30:16 - INFO - [abc12345] PDF recibido vía upload: documento.pdf
2024-07-09 17:30:17 - INFO - [abc12345] PDF válido con 5 páginas
2024-07-09 17:30:20 - INFO - [abc12345] ✅ Conversión exitosa: 5 páginas, 2.1MB ZIP
```

### **Métricas Importantes:**
- 🆔 **Conversion ID:** Identificador único por conversión
- 📊 **Source Info:** Origen del PDF (upload/url/supabase)
- 📄 **Page Count:** Número de páginas procesadas
- 💾 **File Sizes:** Tamaños de entrada y salida
- ⏱️ **Processing Time:** Tiempo total de procesamiento

## 🚨 Solución de Problemas

### **Errores Comunes:**

#### `401 Unauthorized`
- ❌ API Key no proporcionada o incorrecta
- ✅ Verificar header `X-API-Key` o campo `api_key` en JSON

#### `413 Payload Too Large`
- ❌ Archivo excede 50MB
- ✅ Comprimir PDF o dividir en archivos más pequeños

#### `400 Bad Request: PDF no válido`
- ❌ Archivo corrupto o no es PDF
- ✅ Verificar que el archivo sea PDF válido

#### `429 Too Many Requests`
- ❌ Rate limit excedido
- ✅ Esperar o ajustar `RATE_LIMIT_PER_MINUTE`

#### `500 Internal Server Error`
- ❌ Error interno del servicio
- ✅ Revisar logs del servidor, reportar issue

### **Debugging:**
```bash
# Habilitar logs detallados
export DEBUG=true

# Ver logs en Railway
railway logs

# Test de conectividad
curl -v https://tu-servicio.railway.app/health
```

## 🤝 Contribuir

1. Fork el repositorio
2. Crear rama para feature (`git checkout -b feature/nueva-funcionalidad`)
3. Commit cambios (`git commit -am 'Agregar nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/nueva-funcionalidad`)
5. Crear Pull Request

### **Estructura del Proyecto:**
```
PDF2JPG-SupabaseService/
├── app.py              # Aplicación principal
├── requirements.txt    # Dependencias Python
├── Dockerfile         # Imagen Docker optimizada
├── README.md          # Esta documentación
├── .env.example       # Variables de entorno ejemplo
└── .gitignore         # Archivos a ignorar
```

## 📄 Licencia

MIT License - Ver [LICENSE](LICENSE) para más detalles.

## 🆘 Soporte

- 📧 **Email:** soporte@tu-dominio.com
- 🐛 **Issues:** [GitHub Issues](https://github.com/tu-usuario/PDF2JPG-SupabaseService/issues)
- 📖 **Documentación:** [Wiki](https://github.com/tu-usuario/PDF2JPG-SupabaseService/wiki)
- 💬 **Discord:** [Servidor de la Comunidad](https://discord.gg/tu-servidor)

---

## 🚀 **¡Hecho con ❤️ para la comunidad n8n!**

⭐ **Si te resulta útil, considera darle una estrella al repositorio**
