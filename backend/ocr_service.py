import os
import base64
from typing import List
import httpx

from dotenv import load_dotenv
import logging
import fitz  # PyMuPDF
import io
from PIL import Image

from backend.adaptive_preprocessing import AdaptiveImagePreprocessor


load_dotenv()

logger = logging.getLogger(__name__)

class GoogleVisionOCR:
    def __init__(self):
        self.api_key = os.getenv("GOOGLE_VISION_API_KEY")
        self.url = f"https://vision.googleapis.com/v1/images:annotate?key={self.api_key}"
        self.preprocessor = AdaptiveImagePreprocessor()
        logger.info("OCR Adaptativo: melhora imagens APENAS quando necessario")

    async def extract_text_pages(self, file_content: bytes, progress_callback=None) -> List[str]:
        """
        Envia o conteúdo do arquivo para o Google Vision API e retorna uma lista de textos por página.
        Memória-eficiente: Processa em lotes sem carregar todas as imagens simultaneamente.
        COM PROGRESSO EM TEMPO REAL
        """
        if not self.api_key:
            logger.error("ERRO: GOOGLE_VISION_API_KEY nao configurada em .env")
            return []

        logger.info(f"API Key configurada: {self.api_key[:10]}...")
        is_pdf = file_content.startswith(b"%PDF-")
        logger.info(f"Tipo de arquivo: {'PDF' if is_pdf else 'Imagem'}")
        page_texts = []
        
        try:
            async with httpx.AsyncClient() as client:
                if is_pdf:
                    logger.info("Processando PDF multi-pagina...")
                    doc = fitz.open(stream=file_content, filetype="pdf")
                    num_pages = len(doc)
                    logger.info(f"Total de paginas: {num_pages}")
                    
                    # Notifica início
                    if progress_callback:
                        await progress_callback({
                            "message": f"Iniciando OCR de {num_pages} páginas...",
                            "progress": 0,
                            "step": 0,
                            "total_steps": num_pages * 2
                        })
                    
                    BATCH_SIZE = 3 # Lote MUITO menor para documentos grandes (82 páginas)
                    
                    for i in range(0, num_pages, BATCH_SIZE):
                        batch_images = []
                        end_page = min(i + BATCH_SIZE, num_pages)
                        
                        logger.info(f"Convertendo lote de páginas {i+1} até {end_page}...")
                        
                        for page_num in range(i, end_page):
                            # Notifica pré-processamento
                            if progress_callback:
                                await progress_callback({
                                    "message": f"Convertendo página {page_num+1}/{num_pages} para imagem",
                                    "progress": int((page_num / num_pages) * 50),  # Primeiros 50%
                                    "step": page_num,
                                    "total_steps": num_pages * 2
                                })
                            
                            page = doc.load_page(page_num)
                            pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
                            img_bytes = pix.tobytes("png")
                            
                            # SEM PRÉ-PROCESSAMENTO (Google Vision funciona melhor com imagem original)
                            
                            batch_images.append(img_bytes)
                        
                        # Notifica envio para API
                        if progress_callback:
                            await progress_callback({
                                "message": f"Lendo texto das páginas {i+1} até {end_page} (OCR)...",
                                "progress": int((i / num_pages) * 50) + 50,  # Últimos 50%
                                "step": i + BATCH_SIZE,
                                "total_steps": num_pages * 2
                            })
                        
                        # Processa o lote na API
                        requests = []
                        for img_bytes in batch_images:
                            base64_image = base64.b64encode(img_bytes).decode("utf-8")
                            requests.append({
                                "image": {"content": base64_image},
                                "features": [{"type": "TEXT_DETECTION"}]
                            })
                        
                        logger.info(f"Enviando lote {i//BATCH_SIZE + 1} para Google Vision...")
                        response = await client.post(self.url, json={"requests": requests}, timeout=300.0)
                        logger.info(f"Status da resposta: {response.status_code}")
                        response.raise_for_status()
                        
                        data = response.json()
                        logger.info(f"Resposta recebida: {len(data.get('responses', []))} paginas processadas")
                        
                        for idx, res in enumerate(data.get("responses", [])):
                            page_index = i + idx
                            if "error" in res:
                                logger.error(f"ERRO na pagina {page_index+1}: {res['error']}")
                                page_texts.append("")
                            else:
                                text = res.get("fullTextAnnotation", {}).get("text", "")
                                logger.info(f"Pagina {page_index+1}: {len(text)} caracteres extraidos")
                                
                                # ADAPTATIVO: Se resultado ruim, tenta melhorar imagem
                                if self.preprocessor.should_enhance(text) and page_index < len(batch_images):
                                    logger.warning(f"Pagina {page_index+1}: Qualidade baixa, aplicando melhorias...")
                                    
                                    # Melhora a imagem
                                    enhanced_img = self.preprocessor.enhance_image(batch_images[idx])
                                    
                                    # Tenta OCR novamente com imagem melhorada
                                    base64_enhanced = base64.b64encode(enhanced_img).decode("utf-8")
                                    retry_payload = {
                                        "requests": [{
                                            "image": {"content": base64_enhanced},
                                            "features": [{"type": "TEXT_DETECTION"}]
                                        }]
                                    }
                                    
                                    retry_response = await client.post(self.url, json=retry_payload, timeout=300.0)
                                    retry_response.raise_for_status()
                                    retry_data = retry_response.json()
                                    retry_text = retry_data.get("responses", [{}])[0].get("fullTextAnnotation", {}).get("text", "")
                                    
                                    # Compara resultados e usa o melhor
                                    if len(retry_text) > len(text):
                                        logger.info(f"Pagina {page_index+1}: Imagem melhorada deu resultado MELHOR ({len(retry_text)} vs {len(text)} caracteres)")
                                        text = retry_text
                                    else:
                                        logger.info(f"Pagina {page_index+1}: Imagem original era MELHOR")
                                
                                page_texts.append(text)
                        
                        # Limpa referências para o GC
                        del batch_images
                        del requests
                        
                    doc.close()
                else:
                    # Imagem única
                    logger.info("Processando imagem unica...")
                    
                    if progress_callback:
                        await progress_callback({
                            "message": "Convertendo imagem...",
                            "progress": 25
                        })
                    
                    # SEM PRÉ-PROCESSAMENTO (Google Vision funciona melhor com imagem original)
                    
                    if progress_callback:
                        await progress_callback({
                            "message": "Lendo texto da imagem (OCR)...",
                            "progress": 50
                        })
                    
                    base64_image = base64.b64encode(file_content).decode("utf-8")
                    payload = {
                        "requests": [{"image": {"content": base64_image}, "features": [{"type": "TEXT_DETECTION"}]}]
                    }
                    response = await client.post(self.url, json=payload, timeout=60.0)
                    response.raise_for_status()
                    data = response.json()
                    text = data.get("responses", [{}])[0].get("fullTextAnnotation", {}).get("text", "")
                    page_texts.append(text)

            logger.info(f"OCR concluido: {len(page_texts)} paginas processadas")
            return page_texts

        except Exception as e:
            print(f"ERRO CRITICO NO OCR: {str(e)}")
            import traceback
            traceback.print_exc()
            logger.error(f"Erro critico no OCR: {str(e)}", exc_info=True)
            return page_texts



