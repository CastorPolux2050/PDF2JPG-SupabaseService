#!/usr/bin/env python3
"""
🚀 PDF2JPG Service v2.0 - Servicio de conversión PDF a JPG
Convierte PDFs a imágenes JPG y retorna ZIP, con seguridad integrada
Autor: Tu Equipo de Desarrollo
"""

import os
import io
import zipfile
import tempfile
import logging
import uuid
import time
from datetime import datetime
from typing import Optional, List
from pathlib import Path
from collections import defaultdict
from functools import wraps

import fitz  # PyMuPDF
import requests
from PIL import Image
from flask import Flask, request, jsonify, send_file
from werkzeug.exceptions import BadRequest, InternalServerError

# 📋 CONFIGURACIÓN DE LA APLICACIÓN
app = Flask(__name__)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 🔧 CONFIGURACIONES PRINCIPALES
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_PAGES = 100  # Máximo páginas a procesar
SUPPORTED_FORMATS = ['application/pdf', 'pdf']
TEMP_DIR = os.environ.get('TEMP_DIR', '/tmp')
IMAGE_QUALITY = int(os.environ.get('IMAGE_QUALITY', '95'))
IMAGE_DPI = int(os.environ.get('IMAGE_DPI', '300'))

# 🔐 CONFIGURACIONES DE SEGURIDAD
API_KEY = os.environ.get('API_KEY')
ALLOWED_IPS = os.environ.get('ALLOWED_IPS', '').split(',') if os.environ.get('ALLOWED_IPS') else []
RATE_LIMIT_PER_MINUTE = int(os.environ.get('RATE_LIMIT_PER_MINUTE', '10'))

# Cache para rate limiting
request_cache = defaultdict(list)


class PDFProcessor:
    """Procesador optimizado de PDFs a imágenes JPG"""
    
    def __init__(self, quality: int = IMAGE_QUALITY, dpi: int = IMAGE_DPI):
        self.quality = quality
        self.dpi = dpi
        self.temp_files = []
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
    
    def cleanup(self):
        """Limpia archivos temporales creados durante el procesamiento"""
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as e:
                logger.warning(f"No se pudo eliminar archivo temporal {temp_file}: {e}")
        self.temp_files.clear()
    
    def download_pdf_from_url(self, url: str) -> bytes:
        """Descarga PDF desde URL con validaciones de seguridad"""
        try:
            logger.info(f"Descargando PDF desde URL: {url[:100]}...")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; PDF2JPG-Service/2.0)',
                'Accept': 'application/pdf,*/*'
            }
            
            response = requests.get(
                url, 
                headers=headers, 
                timeout=30,
                stream=True
            )
            response.raise_for_status()
            
            # Verificar Content-Type
            content_type = response.headers.get('content-type', '').lower()
            if 'pdf' not in content_type and not any(fmt in content_type for fmt in SUPPORTED_FORMATS):
                logger.warning(f"Content-Type sospechoso: {content_type}")
            
            # Verificar tamaño antes de descargar
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > MAX_FILE_SIZE:
                raise ValueError(f"Archivo demasiado grande: {content_length} bytes")
            
            # Descargar con límite de tamaño
            pdf_data = b''
            for chunk in response.iter_content(chunk_size=8192):
                pdf_data += chunk
                if len(pdf_data) > MAX_FILE_SIZE:
                    raise ValueError(f"Archivo excede {MAX_FILE_SIZE} bytes")
            
            logger.info(f"PDF descargado exitosamente: {len(pdf_data)} bytes")
            return pdf_data
            
        except requests.RequestException as e:
            logger.error(f"Error descargando PDF desde URL: {e}")
            raise ValueError(f"No se pudo descargar el PDF: {e}")
    
    def download_pdf_from_supabase(self, file_id: str, supabase_url: str, 
                                  service_key: str, bucket: str) -> bytes:
        """Descarga PDF desde Supabase Storage"""
        try:
            storage_url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{file_id}"
            
            headers = {
                'Authorization': f'Bearer {service_key}',
                'apikey': service_key
            }
            
            logger.info(f"Descargando PDF desde Supabase: {bucket}/{file_id}")
            
            response = requests.get(storage_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            pdf_data = response.content
            if len(pdf_data) > MAX_FILE_SIZE:
                raise ValueError(f"Archivo excede {MAX_FILE_SIZE} bytes")
            
            logger.info(f"PDF descargado desde Supabase: {len(pdf_data)} bytes")
            return pdf_data
            
        except requests.RequestException as e:
            logger.error(f"Error descargando desde Supabase: {e}")
            raise ValueError(f"No se pudo descargar desde Supabase: {e}")
    
    def validate_pdf(self, pdf_data: bytes) -> bool:
        """Valida que los datos sean un PDF válido y dentro de límites"""
        try:
            # Verificar magic number de PDF
            if not pdf_data.startswith(b'%PDF-'):
                logger.error("Archivo no es un PDF válido (magic number incorrecto)")
                return False
            
            # Intentar abrir con PyMuPDF
            doc = fitz.open(stream=pdf_data, filetype="pdf")
            page_count = len(doc)
            doc.close()
            
            if page_count == 0:
                logger.error("PDF no contiene páginas")
                return False
            
            if page_count > MAX_PAGES:
                logger.error(f"PDF excede el límite de páginas: {page_count} > {MAX_PAGES}")
                return False
            
            logger.info(f"PDF válido con {page_count} páginas")
            return True
            
        except Exception as e:
            logger.error(f"Error validando PDF: {e}")
            return False
    
    def convert_pdf_to_images(self, pdf_data: bytes) -> List[bytes]:
        """Convierte PDF a lista de imágenes JPG"""
        images = []
        doc = None
        
        try:
            logger.info("Iniciando conversión PDF → JPG")
            
            # Abrir PDF en memoria
            doc = fitz.open(stream=pdf_data, filetype="pdf")
            page_count = len(doc)
            
            # Matriz de transformación para el DPI especificado
            matrix = fitz.Matrix(self.dpi/72, self.dpi/72)
            
            for page_num in range(page_count):
                try:
                    # Renderizar página como imagen
                    page = doc[page_num]
                    pix = page.get_pixmap(matrix=matrix)
                    
                    # Convertir a PIL Image
                    img_data = pix.tobytes("ppm")
                    pil_image = Image.open(io.BytesIO(img_data))
                    
                    # Asegurar modo RGB
                    if pil_image.mode != 'RGB':
                        pil_image = pil_image.convert('RGB')
                    
                    # Comprimir como JPG en memoria
                    jpg_buffer = io.BytesIO()
                    pil_image.save(
                        jpg_buffer, 
                        format='JPEG', 
                        quality=self.quality,
                        optimize=True
                    )
                    
                    images.append(jpg_buffer.getvalue())
                    logger.info(f"Página {page_num + 1}/{page_count} convertida exitosamente")
                    
                except Exception as e:
                    logger.error(f"Error procesando página {page_num + 1}: {e}")
                    # Continuar con las demás páginas en lugar de fallar completamente
                    continue
            
            if not images:
                raise ValueError("No se pudo convertir ninguna página del PDF")
            
            logger.info(f"Conversión completada: {len(images)} imágenes generadas")
            return images
            
        except Exception as e:
            logger.error(f"Error en conversión PDF → JPG: {e}")
            raise ValueError(f"Error convirtiendo PDF: {e}")
        
        finally:
            if doc:
                doc.close()
    
    def create_zip_file(self, images: List[bytes], base_name: str = "page") -> bytes:
        """Crea archivo ZIP con las imágenes numeradas"""
        try:
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zip_file:
                for i, img_data in enumerate(images, 1):
                    filename = f"{base_name}_{i:03d}.jpg"
                    zip_file.writestr(filename, img_data)
                    logger.debug(f"Agregado al ZIP: {filename} ({len(img_data)} bytes)")
            
            zip_data = zip_buffer.getvalue()
            logger.info(f"ZIP creado exitosamente: {len(zip_data)} bytes, {len(images)} archivos")
            return zip_data
            
        except Exception as e:
            logger.error(f"Error creando archivo ZIP: {e}")
            raise ValueError(f"Error creando archivo ZIP: {e}")


# 🔐 DECORADORES DE SEGURIDAD

def require_api_key(f):
    """Decorador para requerir API key en requests"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not API_KEY:
            logger.warning("⚠️ Servicio ejecutándose SIN API KEY - No recomendado para producción")
            return f(*args, **kwargs)
        
        # Buscar API key en headers
        provided_key = request.headers.get('X-API-Key') or request.headers.get('Authorization', '').replace('Bearer ', '')
        
        # También buscar en JSON body
        if not provided_key and request.is_json:
            try:
                data = request.get_json()
                provided_key = data.get('api_key') if data else None
            except:
                pass
        
        if not provided_key:
            logger.warning(f"🚫 Acceso denegado - API key no proporcionada. IP: {request.remote_addr}")
            return jsonify({'error': 'Unauthorized', 'message': 'API key requerida'}), 401
        
        if provided_key != API_KEY:
            logger.warning(f"🚫 Acceso denegado - API key inválida. IP: {request.remote_addr}")
            return jsonify({'error': 'Unauthorized', 'message': 'API key inválida'}), 401
        
        logger.info(f"✅ Acceso autorizado. IP: {request.remote_addr}")
        return f(*args, **kwargs)
    
    return decorated_function


def check_ip_whitelist(f):
    """Decorador para verificar whitelist de IPs"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not ALLOWED_IPS or not ALLOWED_IPS[0]:
            return f(*args, **kwargs)
        
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if client_ip and ',' in client_ip:
            client_ip = client_ip.split(',')[0].strip()
        
        if client_ip not in ALLOWED_IPS:
            logger.warning(f"🚫 IP no autorizada: {client_ip}")
            return jsonify({'error': 'Forbidden', 'message': 'IP no autorizada'}), 403
        
        return f(*args, **kwargs)
    
    return decorated_function


def rate_limit(f):
    """Decorador para rate limiting por IP"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if client_ip and ',' in client_ip:
            client_ip = client_ip.split(',')[0].strip()
        
        current_time = time.time()
        minute_ago = current_time - 60
        
        # Limpiar requests antiguos
        request_cache[client_ip] = [req_time for req_time in request_cache[client_ip] if req_time > minute_ago]
        
        # Verificar límite
        if len(request_cache[client_ip]) >= RATE_LIMIT_PER_MINUTE:
            logger.warning(f"🚫 Rate limit excedido para IP: {client_ip} ({len(request_cache[client_ip])} requests)")
            return jsonify({
                'error': 'Too Many Requests',
                'message': f'Límite de {RATE_LIMIT_PER_MINUTE} requests por minuto excedido'
            }), 429
        
        # Registrar request actual
        request_cache[client_ip].append(current_time)
        return f(*args, **kwargs)
    
    return decorated_function


# 🌐 ENDPOINTS DE LA API

@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint de verificación de salud del servicio"""
    return jsonify({
        'status': 'healthy',
        'service': 'PDF2JPG Converter',
        'version': '2.0.0',
        'timestamp': datetime.now().isoformat(),
        'security': {
            'api_key_enabled': bool(API_KEY),
            'ip_whitelist_enabled': bool(ALLOWED_IPS and ALLOWED_IPS[0]),
            'rate_limit_per_minute': RATE_LIMIT_PER_MINUTE
        },
        'limits': {
            'max_file_size_mb': MAX_FILE_SIZE // (1024*1024),
            'max_pages': MAX_PAGES,
            'image_quality': IMAGE_QUALITY,
            'image_dpi': IMAGE_DPI
        }
    })


@app.route('/convert', methods=['POST'])
@rate_limit
@check_ip_whitelist  
@require_api_key
def convert_pdf():
    """
    Endpoint principal de conversión PDF → JPG → ZIP
    
    Acepta múltiples formatos:
    1. Form-data con archivo 'file'
    2. JSON con URL del PDF
    3. JSON con configuración de Supabase
    4. Raw PDF data
    """
    
    conversion_id = str(uuid.uuid4())[:8]
    logger.info(f"[{conversion_id}] Iniciando nueva conversión")
    
    try:
        with PDFProcessor() as processor:
            pdf_data = None
            source_info = "unknown"
            
            # MÉTODO 1: PDF subido como form-data
            if 'file' in request.files:
                file = request.files['file']
                if file and file.filename:
                    pdf_data = file.read()
                    source_info = f"upload:{file.filename}"
                    logger.info(f"[{conversion_id}] PDF recibido vía upload: {file.filename}")
            
            # MÉTODO 2: Configuración JSON
            elif request.is_json:
                data = request.get_json()
                
                # Opción A: URL directa
                if 'url' in data:
                    pdf_data = processor.download_pdf_from_url(data['url'])
                    source_info = f"url:{data['url']}"
                
                # Opción B: Supabase Storage
                elif all(key in data for key in ['file_id', 'supabase_url', 'service_key', 'bucket']):
                    pdf_data = processor.download_pdf_from_supabase(
                        data['file_id'],
                        data['supabase_url'], 
                        data['service_key'],
                        data['bucket']
                    )
                    source_info = f"supabase:{data['bucket']}/{data['file_id']}"
                
                else:
                    raise BadRequest("JSON debe contener 'url' o parámetros completos de Supabase")
            
            # MÉTODO 3: Raw PDF data
            elif request.content_type == 'application/pdf':
                pdf_data = request.get_data()
                source_info = "raw_pdf"
                logger.info(f"[{conversion_id}] PDF recibido como raw data")
            
            else:
                raise BadRequest("Formato no soportado. Use form-data, JSON con URL/Supabase, o raw PDF")
            
            # Validaciones
            if not pdf_data:
                raise BadRequest("No se recibieron datos de PDF")
            
            if not processor.validate_pdf(pdf_data):
                raise BadRequest("Archivo no es un PDF válido o excede los límites permitidos")
            
            # Procesamiento
            images = processor.convert_pdf_to_images(pdf_data)
            
            if not images:
                raise InternalServerError("No se pudieron generar imágenes del PDF")
            
            # Crear nombre base para archivos
            base_name = "page"
            if ':' in source_info:
                source_part = source_info.split(':', 1)[1]
                if '/' in source_part:
                    base_name = Path(source_part.split('/')[-1]).stem
                else:
                    base_name = Path(source_part).stem
                # Limpiar caracteres especiales
                base_name = "".join(c for c in base_name if c.isalnum() or c in ('-', '_'))[:20]
            
            # Crear ZIP
            zip_data = processor.create_zip_file(images, base_name or "page")
            
            # Estadísticas del procesamiento
            stats = {
                'conversion_id': conversion_id,
                'source': source_info,
                'pdf_size_bytes': len(pdf_data),
                'pages_converted': len(images),
                'zip_size_bytes': len(zip_data),
                'processing_time': datetime.now().isoformat()
            }
            
            logger.info(f"[{conversion_id}] ✅ Conversión exitosa: {stats}")
            
            # Retornar archivo ZIP
            zip_filename = f"{base_name or 'converted'}_{conversion_id}.zip"
            
            return send_file(
                io.BytesIO(zip_data),
                mimetype='application/zip',
                as_attachment=True,
                download_name=zip_filename
            )
    
    except BadRequest as e:
        logger.error(f"[{conversion_id}] ❌ Bad Request: {e}")
        return jsonify({'error': 'Bad Request', 'message': str(e)}), 400
    
    except ValueError as e:
        logger.error(f"[{conversion_id}] ❌ Value Error: {e}")
        return jsonify({'error': 'Invalid Input', 'message': str(e)}), 400
    
    except Exception as e:
        logger.error(f"[{conversion_id}] ❌ Internal Error: {e}")
        return jsonify({'error': 'Internal Server Error', 'message': 'Error interno del servicio'}), 500


@app.route('/convert/url', methods=['POST'])
@rate_limit
@check_ip_whitelist
@require_api_key
def convert_from_url():
    """Endpoint específico para conversión desde URL"""
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            raise BadRequest("Se requiere campo 'url' en JSON")
        return convert_pdf()
    except Exception as e:
        logger.error(f"Error en convert_from_url: {e}")
        return jsonify({'error': 'Bad Request', 'message': str(e)}), 400


@app.route('/convert/supabase', methods=['POST'])
@rate_limit
@check_ip_whitelist
@require_api_key
def convert_from_supabase():
    """Endpoint específico para conversión desde Supabase"""
    try:
        data = request.get_json()
        required_fields = ['file_id', 'supabase_url', 'service_key', 'bucket']
        
        if not data or not all(field in data for field in required_fields):
            raise BadRequest(f"Se requieren campos: {required_fields}")
        return convert_pdf()
    except Exception as e:
        logger.error(f"Error en convert_from_supabase: {e}")
        return jsonify({'error': 'Bad Request', 'message': str(e)}), 400


# 🚫 MANEJADORES DE ERRORES

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'error': 'Not Found',
        'message': 'Endpoint no encontrado',
        'available_endpoints': [
            'GET /health - Verificación de salud',
            'POST /convert - Conversión principal',
            'POST /convert/url - Conversión desde URL',
            'POST /convert/supabase - Conversión desde Supabase'
        ]
    }), 404


@app.errorhandler(413)
def too_large(error):
    return jsonify({
        'error': 'Payload Too Large',
        'message': f'Archivo excede el límite de {MAX_FILE_SIZE//(1024*1024)}MB'
    }), 413


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Error interno del servidor: {error}")
    return jsonify({
        'error': 'Internal Server Error',
        'message': 'Error interno del servicio'
    }), 500


# 🚀 PUNTO DE ENTRADA PRINCIPAL

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"🚀 Iniciando PDF2JPG Service v2.0 en puerto {port}")
    logger.info(f"📊 Configuración: Quality={IMAGE_QUALITY}, DPI={IMAGE_DPI}, MaxSize={MAX_FILE_SIZE//(1024*1024)}MB")
    
    # Mostrar configuración de seguridad
    if API_KEY:
        logger.info(f"🔐 API Key habilitada (longitud: {len(API_KEY)} caracteres)")
    else:
        logger.warning(f"⚠️ API Key NO configurada - Servicio será público")
    
    if ALLOWED_IPS and ALLOWED_IPS[0]:
        logger.info(f"🛡️ IP Whitelist habilitada: {len(ALLOWED_IPS)} IPs autorizadas")
    else:
        logger.info(f"🌐 Acceso desde cualquier IP permitido")
    
    logger.info(f"⏱️ Rate limit configurado: {RATE_LIMIT_PER_MINUTE} requests/minuto por IP")
    logger.info(f"🔧 Modo debug: {'Habilitado' if debug else 'Deshabilitado'}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)
