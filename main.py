from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
import zipfile
import tempfile
import requests
from pdf2image import convert_from_path
import shutil
import logging
import uuid

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="PDF2JPG-Supabase Service", version="1.0.0")

# Configuración
TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

class ConvertRequest(BaseModel):
    file_id: str  # UUID del archivo en Supabase (ej: "2d319500-12ca-4ddf-993c-fdac13ad48ab")
    pdf_file_name: str #n nombre del documento
    supabase_url: str  # URL del proyecto Supabase
    service_key: str  # Service role key
    bucket: str = "baseconocimiento.arca"  # Bucket name

def get_file_name_from_uuid(file_uuid: str, supabase_url: str, service_key: str, bucket: str) -> str:
    """Obtiene el nombre del archivo desde su UUID usando la API de Supabase Storage"""
    try:
        # Listar todos los archivos del bucket
        list_url = f"{supabase_url}/storage/v1/object/list/{bucket}"
        
        headers = {
            'Authorization': f'Bearer {service_key}',
            'apikey': service_key,
            'Content-Type': 'application/json'
        }
        
        body = {
            "prefix": "",
            "limit": 1000,
            "offset": 0
        }
        
        logger.info(f"Buscando archivo con UUID: {file_uuid}")
        
        response = requests.post(list_url, headers=headers, json=body, timeout=30)
        response.raise_for_status()
        
        files = response.json()
        
        # Buscar el archivo por ID
        for file in files:
            if file.get('id') == file_uuid:
                file_name = file.get('name')
                logger.info(f"Archivo encontrado: {file_name}")
                return file_name
        
        raise Exception(f"No se encontró archivo con UUID: {file_uuid}")
        
    except Exception as e:
        logger.error(f"Error obteniendo nombre del archivo: {str(e)}")
        raise

def download_from_supabase(file_name: str, supabase_url: str, service_key: str, bucket: str, output_path: str) -> bool:
    """Descarga un archivo desde Supabase Storage usando el nombre del archivo"""
    try:
        # Construir URL de descarga
        download_url = f"{supabase_url}/storage/v1/object/{bucket}/{file_name}"
        
        logger.info(f"Descargando desde Supabase: {file_name}")
        logger.info(f"URL: {download_url}")
        
        # Headers con autenticación de Supabase
        headers = {
            'Authorization': f'Bearer {service_key}',
            'apikey': service_key,
            'User-Agent': 'PDF2JPG-Supabase-Service/1.0'
        }
        
        # Descargar archivo
        response = requests.get(download_url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()
        
        # Verificar que es un PDF
        content_type = response.headers.get('content-type', '').lower()
        logger.info(f"Content-Type: {content_type}")
        
        # Guardar archivo
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # Verificar que se descargó
        if os.path.getsize(output_path) == 0:
            logger.error("Archivo descargado está vacío")
            return False
            
        logger.info(f"Archivo descargado: {os.path.getsize(output_path)} bytes")
        return True
        
    except Exception as e:
        logger.error(f"Error descargando de Supabase: {str(e)}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return False

def convert_pdf_to_images(pdf_path: str, output_dir: str) -> list:
    """Convierte PDF a imágenes JPG"""
    try:
        logger.info(f"Convirtiendo PDF: {pdf_path}")
        
        images = convert_from_path(
            pdf_path,
            dpi=200,
            output_folder=output_dir,
            fmt='jpeg',
            thread_count=2
        )
        
        image_paths = []
        for i, image in enumerate(images):
            image_path = os.path.join(output_dir, f'page_{i+1:03d}.jpg')
            image.save(image_path, 'JPEG', quality=85, optimize=True)
            image_paths.append(image_path)
            logger.info(f"Página {i+1} convertida")
        
        logger.info(f"Conversión completada: {len(image_paths)} imágenes")
        return image_paths
        
    except Exception as e:
        logger.error(f"Error convirtiendo PDF: {str(e)}")
        return []

def create_zip_file(image_paths: list, zip_path: str) -> bool:
    """Crea un ZIP con las imágenes"""
    try:
        logger.info(f"Creando ZIP: {zip_path}")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for i, image_path in enumerate(image_paths):
                if os.path.exists(image_path):
                    arcname = f'page_{i+1:03d}.jpg'
                    zipf.write(image_path, arcname)
        
        if os.path.exists(zip_path) and os.path.getsize(zip_path) > 0:
            logger.info(f"ZIP creado: {os.path.getsize(zip_path)} bytes")
            return True
        else:
            logger.error("ZIP está vacío")
            return False
            
    except Exception as e:
        logger.error(f"Error creando ZIP: {str(e)}")
        return False

def cleanup_directory(directory: str):
    """Limpia directorio temporal"""
    try:
        if os.path.exists(directory):
            shutil.rmtree(directory)
            logger.info(f"Directorio limpiado: {directory}")
    except Exception as e:
        logger.warning(f"Error limpiando: {str(e)}")

@app.get("/")
async def root():
    return {
        "service": "PDF2JPG-Supabase Service",
        "version": "1.0.0",
        "description": "Convierte PDFs desde Supabase Storage a imágenes JPG usando UUID",
        "endpoints": {
            "/convert": "POST - Convert PDF from Supabase to JPG ZIP using UUID",
            "/health": "GET - Health check"
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "pdf2jpg-supabase"}

@app.post("/convert")
async def convert_pdf_from_supabase(request: ConvertRequest):
    """
    Convierte un PDF desde Supabase Storage a imágenes JPG usando UUID
    
    Body:
    {
        "file_id": "2d319500-12ca-4ddf-993c-fdac13ad48ab",
        "supabase_url": "https://xxx.supabase.co",
        "service_key": "eyJhbGci...",
        "bucket": "baseconocimiento.arca"
    }
    """
    
    logger.info(f"Procesando archivo con UUID: {request.file_id}")
    
    # Crear directorio temporal
    session_id = str(uuid.uuid4())
    temp_dir = os.path.join(TEMP_DIR, session_id)
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        # 1. Obtener nombre del archivo desde UUID
        file_name = get_file_name_from_uuid(
            request.file_id,
            request.supabase_url,
            request.service_key,
            request.bucket
        )
        
        logger.info(f"Nombre del archivo: {file_name}")
        
        # 2. Descargar PDF desde Supabase
        pdf_path = os.path.join(temp_dir, "input.pdf")
        
        if not download_from_supabase(
            file_name, 
            request.supabase_url, 
            request.service_key, 
            request.bucket, 
            pdf_path
        ):
            raise HTTPException(
                status_code=400,
                detail=f"No se pudo descargar {file_name} desde Supabase"
            )
        
        # 3. Convertir PDF a imágenes
        image_paths = convert_pdf_to_images(pdf_path, temp_dir)
        
        if not image_paths:
            raise HTTPException(
                status_code=500,
                detail="No se pudieron generar imágenes del PDF"
            )
        
        # 4. Crear ZIP con todas las imágenes
        zip_path = os.path.join(temp_dir, "images.zip")
        if not create_zip_file(image_paths, zip_path):
            raise HTTPException(
                status_code=500,
                detail="No se pudo crear el archivo ZIP"
            )
        
        # 5. Devolver ZIP
        logger.info(f"Conversión exitosa: {len(image_paths)} imágenes")
        
        # Nombre del ZIP basado en el nombre del archivo original
        zip_filename = f'{file_name.replace(".pdf", "")}_images.zip'
        
        return FileResponse(
            path=zip_path,
            media_type='application/zip',
            filename=zip_filename,
            background=lambda: cleanup_directory(temp_dir)
        )
        
    except HTTPException:
        cleanup_directory(temp_dir)
        raise
        
    except Exception as e:
        cleanup_directory(temp_dir)
        logger.error(f"Error inesperado: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
