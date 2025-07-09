#!/usr/bin/env python3
"""
PDF2JPG Service - Simple & Direct
Recibe PDF, entrega ZIP. Sin complicaciones.
"""

import os
import io
import zipfile
from flask import Flask, request, jsonify, send_file
import fitz  # PyMuPDF
from PIL import Image

app = Flask(__name__)

# Configuración simple
API_KEY = os.environ.get('API_KEY', 'your-api-key')
MAX_SIZE_MB = int(os.environ.get('MAX_SIZE_MB', '20'))
MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024

def require_auth():
    """Verificar API key"""
    provided_key = request.headers.get('X-API-Key') or request.json.get('api_key') if request.is_json else None
    return provided_key == API_KEY

@app.route('/health')
def health():
    """Health check simple"""
    return jsonify({
        'status': 'ok',
        'max_size_mb': MAX_SIZE_MB,
        'api_key_required': bool(API_KEY)
    })

@app.route('/convert', methods=['POST'])
def convert():
    """Convertir PDF a JPG → ZIP"""
    
    # Verificar API key
    if not require_auth():
        return jsonify({'error': 'API key required'}), 401
    
    try:
        # Obtener PDF
        pdf_data = None
        
        if 'file' in request.files:
            # Upload directo
            file = request.files['file']
            pdf_data = file.read()
        elif request.is_json and 'url' in request.json:
            # Desde URL
            import requests
            response = requests.get(request.json['url'], timeout=30)
            response.raise_for_status()
            pdf_data = response.content
        elif request.is_json and 'file_id' in request.json:
            # Desde Supabase
            data = request.json
            import requests
            url = f"{data['supabase_url']}/storage/v1/object/{data['bucket']}/{data['file_id']}"
            headers = {'Authorization': f"Bearer {data['service_key']}"}
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            pdf_data = response.content
        else:
            return jsonify({'error': 'No PDF provided'}), 400
        
        # Verificar tamaño
        if len(pdf_data) > MAX_SIZE_BYTES:
            return jsonify({'error': f'File too large. Max {MAX_SIZE_MB}MB'}), 400
        
        # Convertir PDF → JPG
        doc = fitz.open(stream=pdf_data, filetype="pdf")
        images = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom
            img_data = pix.tobytes("ppm")
            
            # PIL para JPG
            pil_img = Image.open(io.BytesIO(img_data))
            if pil_img.mode != 'RGB':
                pil_img = pil_img.convert('RGB')
            
            jpg_buffer = io.BytesIO()
            pil_img.save(jpg_buffer, format='JPEG', quality=90)
            images.append((f'page_{page_num+1:03d}.jpg', jpg_buffer.getvalue()))
        
        doc.close()
        
        # Crear ZIP
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for filename, img_data in images:
                zip_file.writestr(filename, img_data)
        
        zip_buffer.seek(0)
        
        # Retornar ZIP
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name='converted.zip'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
