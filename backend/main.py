from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from backend.extraction_service import ExtractionCoordinator
from backend.models import DocumentResponse
from backend.database import ExtractionDatabase
from fastapi.middleware.cors import CORSMiddleware

import logging
import asyncio
import json

app = FastAPI(title="Convenio Extração API")

# Configuração de CORS completa
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


coordinator = ExtractionCoordinator()
db = ExtractionDatabase()

# Gerenciador de conexões WebSocket ativas
active_websockets = set()


# Configuração de log para auditoria
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.get("/")
async def health_check():
    return {"status": "ok", "service": "convenio-extração"}

@app.get("/test")
async def test_endpoint():
    """Endpoint de teste para verificar conectividade"""
    return {"message": "Backend está funcionando!", "timestamp": "2026-02-13"}

@app.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket):
    """
    WebSocket para enviar progresso em tempo real
    """
    await websocket.accept()
    active_websockets.add(websocket)
    logger.info("Cliente WebSocket conectado")
    
    try:
        # Mantém conexão aberta
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        logger.info("Cliente WebSocket desconectado")
        active_websockets.discard(websocket)
    except Exception as e:
        logger.error(f"Erro no WebSocket: {e}")
        active_websockets.discard(websocket)

async def broadcast_progress(message: dict):
    """Envia mensagem de progresso para todos os clientes conectados"""
    disconnected = set()
    for websocket in active_websockets:
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Erro ao enviar para WebSocket: {e}")
            disconnected.add(websocket)
    
    # Remove conexões desconectadas
    for ws in disconnected:
        active_websockets.discard(ws)

@app.post("/extract", response_model=DocumentResponse)
async def extract_data(file: UploadFile = File(...)):
    """
    Recebe um PDF ou imagem, executa OCR via Google Vision e retorna dados estruturados.
    AGORA: Salva tudo no banco de dados para eliminar alucinações
    COM PROGRESSO EM TEMPO REAL via WebSocket
    """
    logger.info(f"Nova requisicao recebida - Arquivo: {file.filename}")
    
    # Aceitando PDF, PNG, JPG para OCR
    valid_extensions = (".pdf", ".png", ".jpg", ".jpeg", ".txt")
    if not file.filename.lower().endswith(valid_extensions):
         logger.warning(f"Extensao invalida: {file.filename}")
         raise HTTPException(status_code=400, detail="Arquivo não suportado. Use PDF, PNG, JPG ou TXT.")

    try:
        # Verifica tamanho do arquivo (Máximo 20MB pedido pelo usuário)
        MAX_SIZE = 20 * 1024 * 1024  # 20MB
        file_content = await file.read()
        
        if len(file_content) > MAX_SIZE:
             logger.warning(f"Arquivo muito grande: {len(file_content)} bytes")
             raise HTTPException(status_code=413, detail="Arquivo muito grande. Limite de 20MB.")

        logger.info(f"Arquivo validado: {file.filename} ({len(file_content)} bytes)")
        logger.info(f"Iniciando processamento OCR...")

        
        # Coordena extração e parsing (AGORA COM BANCO DE DADOS E PROGRESSO)
        response = await coordinator.process_document_staged(
            file_content, 
            arquivo_nome=file.filename,
            progress_callback=broadcast_progress
        )

        logger.info(f"Processamento concluido com sucesso!")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro no processamento: {str(e)}", exc_info=True)
        await broadcast_progress({
            "message": f"✗ Erro: {str(e)}",
            "progress": -1,
            "error": True
        })
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@app.get("/historico")
async def listar_historico(limite: int = 100):
    """Lista todas as extrações gravadas no banco"""
    try:
        registros = db.listar_todas_extracoes(limite=limite)
        return {
            "total": len(registros),
            "registros": registros
        }
    except Exception as e:
        logger.error(f"Erro ao listar historico: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao listar histórico: {str(e)}")


@app.get("/historico/{arquivo_nome}")
async def listar_por_arquivo(arquivo_nome: str):
    """Lista a última extração de um arquivo específico"""
    try:
        registros = db.listar_ultima_extracao(arquivo_nome)
        return {
            "arquivo": arquivo_nome,
            "total": len(registros),
            "registros": registros
        }
    except Exception as e:
        logger.error(f"Erro ao listar arquivo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao listar arquivo: {str(e)}")


@app.get("/estatisticas")
async def estatisticas():
    """Retorna estatísticas do banco de dados"""
    try:
        stats = db.estatisticas()
        return stats
    except Exception as e:
        logger.error(f"Erro ao buscar estatisticas: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao buscar estatísticas: {str(e)}")


@app.delete("/limpar-banco")
async def limpar_banco():
    """
    CUIDADO: Remove TODOS os dados do banco
    Use apenas para testes ou reset completo
    """
    try:
        resultado = db.limpar_banco()
        logger.warning(f"Banco de dados limpo: {resultado}")
        return {
            "success": True,
            "message": "Banco de dados limpo com sucesso",
            "removidos": resultado
        }
    except Exception as e:
        logger.error(f"Erro ao limpar banco: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao limpar banco: {str(e)}")


@app.get("/debug/ocr-page/{page_num}")
async def debug_ocr_page(page_num: int):
    """
    DEBUG: Retorna o OCR bruto de uma página específica
    """
    try:
        with open("raw_ocr_debug.txt", "r", encoding="utf-8") as f:
            content = f.read()
        
        pages = content.split("[NOVA PAGINA]")
        
        if page_num < 1 or page_num > len(pages):
            return {"error": f"Página {page_num} não existe. Total: {len(pages)} páginas"}
        
        page_content = pages[page_num - 1]
        
        return {
            "page_num": page_num,
            "total_pages": len(pages),
            "ocr_text": page_content,
            "lines": page_content.split('\n'),
            "line_count": len(page_content.split('\n'))
        }
    except FileNotFoundError:
        return {"error": "Arquivo raw_ocr_debug.txt não encontrado. Faça um upload primeiro."}
    except Exception as e:
        logger.error(f"Erro ao buscar OCR da página: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5050, log_level="debug")





