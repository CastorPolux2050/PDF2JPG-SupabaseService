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
import uuid # Todavía se usa para generar session_id para directorios temporales

# Configurar logging para ver la actividad del servicio
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="PDF2JPG-Supabase Service", version="1.0.0")

# Configuración del directorio temporal
TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

class ConvertRequest(BaseModel):
    # Ya no se usa 'file_id' en este modelo
    pdf_file_name: str  # Nombre del documento PDF en el bucket (ej: "mi_documento.pdf")
    supabase_url: str   # URL base de tu proyecto Supabase
    service_key: str    # Clave de "service_role" para acceder a Storage
    bucket: str = "baseconocimiento.arca"  # Nombre del bucket de Supabase por defecto

def download_from_supabase(file_name: str, supabase_url: str, service_key: str, bucket: str, output_path: str) -> bool:
    """Descarga un archivo desde Supabase Storage usando el nombre del archivo."""
    try:
        # Construye la URL de descarga para el objeto en Supabase Storage
        # Se asume que el bucket no es 'public' y requiere la service_key
        download_url = f"{supabase_url}/storage/v1/object/download/{bucket}/{file_name}"
        
        logger.info(f"Iniciando descarga de: {file_name} desde {bucket}")
        logger.info(f"URL de descarga: {download_url}")
        
        # Headers para la autenticación con la service_key
        headers = {
            'Authorization': f'Bearer {service_key}',
            'apikey': service_key,
            'User-Agent': 'PDF2JPG-Supabase-Service/1.0' # Identifica tu servicio
        }
        
        # Realiza la petición GET para descargar el archivo
        response = requests.get(download_url, headers=headers, stream=True, timeout=120) # Aumentado timeout por PDFs grandes
        response.raise_for_status() # Lanza un HTTPException si la respuesta es un error (4xx o 5xx)
        
        # Verifica el Content-Type (opcional pero buena práctica)
        content_type = response.headers.get('content-type', '').lower()
        if 'application/pdf' not in content_type:
             logger.warning(f"Content-Type inesperado para {file_name}: {content_type}. Se esperaba 'application/pdf'.")
             # Podrías optar por lanzar una excepción aquí si el archivo no es un PDF
        
        # Guarda el contenido del archivo en el output_path
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk: # filtra chunks vacíos 'keep-alive'
                    f.write(chunk)
        
        # Verifica que el archivo se haya descargado y no esté vacío
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            logger.error(f"El archivo {file_name} descargado está vacío o no se guardó correctamente.")
            return False
            
        logger.info(f"Archivo {file_name} descargado exitosamente: {os.path.getsize(output_path)} bytes.")
        return True
        
    except requests.exceptions.Timeout:
        logger.error(f"Tiempo de espera agotado ({response.request.timeout}s) al descargar {file_name}.")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Error de red o HTTP al descargar {file_name}: {e}. Estado: {response.status_code if 'response' in locals() else 'N/A'}.")
        if os.path.exists(output_path):
            os.remove(output_path) # Limpia el archivo parcial
        return False
    except Exception as e:
        logger.error(f"Error inesperado al descargar {file_name}: {str(e)}.")
        if os.path.exists(output_path):
            os.remove(output_path)
        return False

def convert_pdf_to_images(pdf_path: str, output_dir: str) -> list:
    """Convierte un PDF a una lista de imágenes JPG."""
    try:
        logger.info(f"Iniciando conversión de PDF: {pdf_path}")
        
        # Convertir cada página del PDF a una imagen JPG
        images = convert_from_path(
            pdf_path,
            dpi=200,          # Resolución de las imágenes (DPI)
            output_folder=output_dir, # Carpeta donde se guardarán temporalmente las imágenes
            fmt='jpeg',       # Formato de salida de las imágenes
            thread_count=2    # Número de hilos para la conversión
        )
        
        image_paths = []
        for i, image in enumerate(images):
            image_path = os.path.join(output_dir, f'page_{i+1:03d}.jpg')
            image.save(image_path, 'JPEG', quality=85, optimize=True) # Guardar con compresión y optimización
            image_paths.append(image_path)
            logger.info(f"Página {i+1} de {pdf_path} convertida y guardada como {image_path}.")
        
        logger.info(f"Conversión completada. Total de imágenes generadas: {len(image_paths)}.")
        return image_paths
        
    except Exception as e:
        logger.error(f"Error durante la conversión del PDF '{pdf_path}' a imágenes: {str(e)}.")
        return []

def create_zip_file(image_paths: list, zip_path: str) -> bool:
    """Crea un archivo ZIP conteniendo todas las imágenes generadas."""
    try:
        logger.info(f"Creando archivo ZIP en: {zip_path}")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for i, image_path in enumerate(image_paths):
                if os.path.exists(image_path):
                    # Nombre de la imagen dentro del ZIP
                    arcname = f'page_{i+1:03d}.jpg'
                    zipf.write(image_path, arcname)
                    logger.info(f"Añadido '{arcname}' al ZIP.")
                else:
                    logger.warning(f"Advertencia: La imagen no se encontró para añadir al ZIP: {image_path}.")
        
        if os.path.exists(zip_path) and os.path.getsize(zip_path) > 0:
            logger.info(f"Archivo ZIP creado exitosamente: {os.path.getsize(zip_path)} bytes.")
            return True
        else:
            logger.error("El archivo ZIP resultante está vacío o no se creó correctamente.")
            return False
            
    except Exception as e:
        logger.error(f"Error al crear el archivo ZIP: {str(e)}.")
        return False

def cleanup_directory(directory: str):
    """Elimina el directorio temporal y su contenido."""
    try:
        if os.path.exists(directory):
            shutil.rmtree(directory)
            logger.info(f"Directorio temporal limpiado: {directory}.")
    except Exception as e:
        logger.warning(f"Error al limpiar el directorio temporal '{directory}': {str(e)}. Por favor, elimínelo manualmente si persiste.")

# Endpoints de la API
@app.get("/")
async def root():
    return {
        "service": "PDF2JPG-Supabase Service",
        "version": "1.0.0",
        "description": "Convierte PDFs desde Supabase Storage a imágenes JPG.",
        "endpoints": {
            "/convert": "POST - Convierte un PDF a imágenes JPG y devuelve un ZIP.",
            "/health": "GET - Verifica el estado del servicio."
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "pdf2jpg-supabase"}

@app.post("/convert")
async def convert_pdf_from_supabase(request: ConvertRequest):
    """
    Endpoint principal para convertir un PDF de Supabase Storage a imágenes JPG y devolver un ZIP.
    
    Args (en el cuerpo de la solicitud JSON):
        pdf_file_name (str): El nombre exacto del archivo PDF en el bucket de Supabase (ej: "documento.pdf").
        supabase_url (str): La URL base de tu proyecto Supabase.
        service_key (str): Tu clave de "service_role" de Supabase.
        bucket (str): El nombre del bucket donde se encuentra el PDF (por defecto "baseconocimiento.arca").
    """
    
    logger.info(f"Iniciando procesamiento para el archivo: {request.pdf_file_name}")
    
    # Crea un directorio temporal único para esta solicitud de conversión
    session_id = str(uuid.uuid4())
    temp_dir = os.path.join(TEMP_DIR, session_id)
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        # El nombre del archivo para descargar es el que se proporciona en la solicitud
        file_name_to_download = request.pdf_file_name
        
        logger.info(f"Intentando descargar el PDF: {file_name_to_download}")
        
        # Paso 1: Descargar el PDF desde Supabase Storage
        # Guardamos el PDF con su nombre original en el directorio temporal
        pdf_path = os.path.join(temp_dir, file_name_to_download) 
        
        if not download_from_supabase(
            file_name_to_download, 
            request.supabase_url, 
            request.service_key, 
            request.bucket, 
            pdf_path
        ):
            raise HTTPException(
                status_code=400,
                detail=f"No se pudo descargar '{file_name_to_download}' desde Supabase. Verifique el nombre del archivo y las políticas de acceso (service_role)."
            )
            
        # Paso 2: Convertir el PDF a imágenes JPG
        image_paths = convert_pdf_to_images(pdf_path, temp_dir)
        
        if not image_paths:
            raise HTTPException(
                status_code=500,
                detail="No se pudieron generar imágenes del PDF. Asegúrese de que el archivo PDF sea válido y no esté corrupto."
            )
            
        # Paso 3: Crear un archivo ZIP con todas las imágenes
        zip_path = os.path.join(temp_dir, f"{os.path.splitext(file_name_to_download)[0]}_images.zip")
        if not create_zip_file(image_paths, zip_path):
            raise HTTPException(
                status_code=500,
                detail="No se pudo crear el archivo ZIP con las imágenes."
            )
            
        # Paso 4: Devolver el archivo ZIP como respuesta al cliente
        logger.info(f"Procesamiento exitoso para {file_name_to_download}. Devolviendo ZIP.")
        
        # Define el nombre del archivo ZIP que el cliente descargará
        zip_filename_for_response = os.path.basename(zip_path) # Usa el nombre generado del zip
        
        return FileResponse(
            path=zip_path,
            media_type='application/zip',
            filename=zip_filename_for_response,
            background=lambda: cleanup_directory(temp_dir) # Asegura la limpieza del temporal
        )
            
    except HTTPException as e:
        # Si ya hemos lanzado una HTTPException, la relanzamos tal cual
        cleanup_directory(temp_dir)
        raise e
            
    except Exception as e:
        # Captura cualquier otra excepción inesperada
        cleanup_directory(temp_dir)
        logger.error(f"Error inesperado al procesar '{request.pdf_file_name}': {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servicio: {str(e)}. Verifique los logs del servicio para más detalles."
        )

if __name__ == "__main__":
    import uvicorn
    # Usa la variable de entorno PORT si está definida, de lo contrario, usa 8000
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
