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
import uuid # Aunque no se use para el file_id, sí se usa para session_id

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="PDF2JPG-Supabase Service", version="1.0.0")

# Configuración
TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

class ConvertRequest(BaseModel):
    # Ya no necesitamos file_id aquí si no se va a usar
    # file_id: str  # UUID del archivo en Supabase (ej: "2d319500-12ca-4ddf-993c-fdac13ad48ab")
    pdf_file_name: str # nombre del documento PDF en el bucket
    supabase_url: str  # URL del proyecto Supabase
    service_key: str  # Service role key
    bucket: str = "baseconocimiento.arca"  # Bucket name

# Hemos eliminado la función get_file_name_from_uuid ya que no se usará.
# def get_file_name_from_uuid(...):
#    ...

def download_from_supabase(file_name: str, supabase_url: str, service_key: str, bucket: str, output_path: str) -> bool:
    """Descarga un archivo desde Supabase Storage usando el nombre del archivo"""
    try:
        # Construir URL de descarga
        # La URL de descarga para objetos públicos es /storage/v1/object/public/{bucket}/{file_name}
        # Para objetos privados con service_key, es /storage/v1/object/{bucket}/{file_name}
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
        response.raise_for_status() # Lanza excepción para códigos de estado de error (4xx o 5xx)
        
        # Verificar que es un PDF (opcional, pero buena práctica)
        content_type = response.headers.get('content-type', '').lower()
        if 'application/pdf' not in content_type:
             logger.warning(f"El Content-Type no es PDF: {content_type}")
             # Podrías decidir lanzar una excepción aquí si el archivo no es un PDF
        
        # Guardar archivo
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # Verificar que se descargó y no está vacío
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            logger.error("Archivo descargado está vacío o no se guardó")
            return False
            
        logger.info(f"Archivo descargado: {os.path.getsize(output_path)} bytes")
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error de red o HTTP al descargar de Supabase: {e}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return False
    except Exception as e:
        logger.error(f"Error inesperado al descargar de Supabase: {str(e)}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return False

def convert_pdf_to_images(pdf_path: str, output_dir: str) -> list:
    """Convierte PDF a imágenes JPG"""
    try:
        logger.info(f"Convirtiendo PDF: {pdf_path}")
        
        # Convertir de PDF a imágenes utilizando pdf2image
        # La calidad y optimización se aplicarán al guardar cada imagen
        images = convert_from_path(
            pdf_path,
            dpi=200,
            output_folder=output_dir, # Asegura que las imágenes temporales se creen aquí
            fmt='jpeg',
            thread_count=2,
            # grayscale=True # Opcional: para convertir a blanco y negro
        )
        
        image_paths = []
        for i, image in enumerate(images):
            image_path = os.path.join(output_dir, f'page_{i+1:03d}.jpg')
            image.save(image_path, 'JPEG', quality=85, optimize=True)
            image_paths.append(image_path)
            logger.info(f"Página {i+1} convertida: {image_path}")
        
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
                    arcname = f'page_{i+1:03d}.jpg' # Nombre de la imagen dentro del ZIP
                    zipf.write(image_path, arcname)
                    logger.info(f"Añadido al ZIP: {arcname}")
                else:
                    logger.warning(f"Archivo de imagen no encontrado para ZIP: {image_path}")
        
        if os.path.exists(zip_path) and os.path.getsize(zip_path) > 0:
            logger.info(f"ZIP creado: {os.path.getsize(zip_path)} bytes")
            return True
        else:
            logger.error("ZIP está vacío o no se creó correctamente")
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
        logger.warning(f"Error limpiando directorio {directory}: {str(e)}")

@app.get("/")
async def root():
    return {
        "service": "PDF2JPG-Supabase Service",
        "version": "1.0.0",
        "description": "Convierte PDFs desde Supabase Storage a imágenes JPG",
        "endpoints": {
            "/convert": "POST - Convert PDF from Supabase to JPG ZIP using file name",
            "/health": "GET - Health check"
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "pdf2jpg-supabase"}

@app.post("/convert")
async def convert_pdf_from_supabase(request: ConvertRequest):
    """
    Convierte un PDF desde Supabase Storage a imágenes JPG
    
    Body:
    {
        "pdf_file_name": "mi_documento.pdf",
        "supabase_url": "https://xxx.supabase.co",
        "service_key": "eyJhbGci...",
        "bucket": "baseconocimiento.arca"
    }
    """
    
    logger.info(f"Procesando archivo: {request.pdf_file_name}")
    
    # Crear directorio temporal para esta sesión de procesamiento
    session_id = str(uuid.uuid4())
    temp_dir = os.path.join(TEMP_DIR, session_id)
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        # Usar el nombre del archivo PDF directamente para la descarga
        file_name_to_download = request.pdf_file_name
        
        logger.info(f"Nombre del archivo para descargar: {file_name_to_download}")
        
        # 1. Descargar PDF desde Supabase
        pdf_path = os.path.join(temp_dir, file_name_to_download) # Guardar con su nombre original
        
        if not download_from_supabase(
            file_name_to_download, 
            request.supabase_url, 
            request.service_key, 
            request.bucket, 
            pdf_path
        ):
            raise HTTPException(
                status_code=400,
                detail=f"No se pudo descargar {file_name_to_download} desde Supabase. Verifique el nombre del archivo y los permisos."
            )
            
        # 2. Convertir PDF a imágenes
        image_paths = convert_pdf_to_images(pdf_path, temp_dir)
        
        if not image_paths:
            raise HTTPException(
                status_code=500,
                detail="No se pudieron generar imágenes del PDF. Verifique que el archivo sea un PDF válido."
            )
            
        # 3. Crear ZIP con todas las imágenes
        zip_path = os.path.join(temp_dir, "images.zip")
        if not create_zip_file(image_paths, zip_path):
            raise HTTPException(
                status_code=500,
                detail="No se pudo crear el archivo ZIP."
            )
            
        # 4. Devolver ZIP como respuesta
        logger.info(f"Conversión exitosa: {len(image_paths)} imágenes")
        
        # Nombre del ZIP basado en el nombre del archivo original
        zip_filename = f'{os.path.splitext(file_name_to_download)[0]}_images.zip'
        
        return FileResponse(
            path=zip_path,
            media_type='application/zip',
            filename=zip_filename,
            background=lambda: cleanup_directory(temp_dir) # Limpia el directorio temporal después de enviar la respuesta
        )
            
    except HTTPException:
        # Si ya es una HTTPException, simplemente la relanzamos
        cleanup_directory(temp_dir)
        raise
            
    except Exception as e:
        cleanup_directory(temp_dir)
        logger.error(f"Error inesperado al procesar PDF: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servicio: {str(e)}. Verifique los logs para más detalles."
        )

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
