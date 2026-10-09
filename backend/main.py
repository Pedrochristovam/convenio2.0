from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from backend import auth
from backend.extraction_service import ExtractionCoordinator, sanitize_filename
from backend.models import DocumentResponse
from backend.database import ExtractionDatabase
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from backend.calculation_service import calculator
from backend.export_service import export_service
from backend.analise_documental.pipeline import executar_analise, precisa_recalcular, recalcular_analise
from backend.analise_documental.minuta_ad import gerar_minuta_ad, sugerir_modelo
from backend.analise_documental.conciliacao_xlsx import gerar_conciliacao
from backend.analise_documental.diligencia import gerar_oficio, gerar_solicitacao
from backend.llm_client import get_llm
from backend.conversao_pdf import ConversaoPdfIndisponivel, docx_para_pdf

import logging
import asyncio
import contextlib
import json
import os
import tempfile

import httpx
from datetime import datetime
from urllib.parse import quote

app = FastAPI(title="Convenio Extração API")

if auth.em_producao() and not auth.ativo():
    raise RuntimeError("APP_USERS não definido: em produção o sistema não sobe sem login.")

ROTAS_ABERTAS = {"/", "/auth/login", "/auth/status"}


# Declarado antes do CORS para que as respostas 401 também levem os cabeçalhos de CORS
@app.middleware("http")
async def exigir_login(request: Request, call_next):
    if auth.ativo() and request.method != "OPTIONS" and request.url.path not in ROTAS_ABERTAS:
        token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not auth.validar(token):
            return JSONResponse({"detail": "Login necessário."}, status_code=401)
    return await call_next(request)


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
db.marcar_interrompidos()

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))
# OCR é a etapa pesada: volumes enviados juntos entram em fila em vez de disputar CPU/memória
fila_ocr = asyncio.Semaphore(int(os.getenv("OCR_SIMULTANEOS", "1")))

# O plano gratuito do Render desliga o servidor após 15 min sem requisições externas.
# Enquanto houver OCR ou análise rodando, o próprio servidor chama a sua URL pública.
URL_PUBLICA = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
tarefas_ativas = 0


@contextlib.asynccontextmanager
async def manter_acordado():
    global tarefas_ativas
    tarefas_ativas += 1
    try:
        yield
    finally:
        tarefas_ativas -= 1


async def _despertador():
    async with httpx.AsyncClient(timeout=30) as cliente:
        while True:
            await asyncio.sleep(300)
            if tarefas_ativas:
                try:
                    await cliente.get(URL_PUBLICA + "/")
                except Exception as exc:
                    logger.warning("Despertador: falha ao chamar %s: %s", URL_PUBLICA, exc)


@app.on_event("startup")
async def iniciar_despertador():
    if URL_PUBLICA:
        app.state.despertador = asyncio.create_task(_despertador())

# Gerenciador de conexões WebSocket ativas
active_websockets = set()

# Configuração de log para auditoria
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.get("/")
async def health_check():
    return {"status": "ok", "service": "convenio-extração"}


class Login(BaseModel):
    usuario: str
    senha: str


@app.get("/auth/status")
async def status_login():
    return {"login": auth.ativo(), "limpar_banco": auth.pode_limpar_banco()}


@app.post("/auth/login")
async def fazer_login(dados: Login):
    token = auth.autenticar(dados.usuario, dados.senha)
    if not token:
        await asyncio.sleep(1)
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos.")
    return {"token": token, "usuario": dados.usuario.strip().lower()}

@app.get("/test")
async def test_endpoint():
    """Endpoint de teste para verificar conectividade"""
    return {"message": "Backend está funcionando!", "timestamp": "2026-02-13"}

@app.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket):
    """
    WebSocket para enviar progresso em tempo real
    """
    if auth.ativo() and not auth.validar(websocket.query_params.get("token")):
        await websocket.close(code=4401)
        return
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
    # Se a mensagem for o resultado final, embrulha no tipo correspondente
    if "resumos_mensais" in message or "movimentacoes_cc" in message:
        payload = {
            "type": "FINAL_RESULT",
            "data": message,
            "message": "✓ Processamento concluído!",
            "progress": 100
        }
    else:
        payload = message
        if "type" not in payload:
            payload["type"] = "PROGRESS"

    disconnected = set()
    for websocket in active_websockets:
        try:
            await websocket.send_json(payload)
        except Exception as e:
            logger.warning(f"Erro ao enviar para WebSocket: {e}")
            disconnected.add(websocket)
    
    # Remove conexões desconectadas
    for ws in disconnected:
        active_websockets.discard(ws)

@app.post("/extract")
async def extract_data(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    pasta_id: int | None = Form(None),
):
    """
    Recebe PDF/imagem, executa OCR híbrido (PDF nativo + Tesseract) e parsers.
    Persiste tudo no MySQL. Progresso via WebSocket; resultado também em GET /resultados/{arquivo}.
    Com pasta_id, o arquivo entra no fim da pasta do convênio antes mesmo do OCR começar.
    """
    try:
        if pasta_id is not None and not db.obter_pasta(pasta_id):
            raise HTTPException(status_code=404, detail="Pasta não encontrada")
        arquivo = sanitize_filename(file.filename or "documento.pdf")
        job = db.obter_ultimo_job(arquivo)
        if job and job.get("status") in ("fila", "processando"):
            raise HTTPException(status_code=409, detail=f"{file.filename} já está sendo processado.")

        # Volumes na fila esperam em disco: na memória, vários de 50 MB estourariam os 512 MB do plano gratuito
        tamanho = 0
        with tempfile.NamedTemporaryFile(prefix="fila_ocr_", suffix=".bin", delete=False) as tmp:
            caminho_fila = tmp.name
            while bloco := await file.read(1024 * 1024):
                tamanho += len(bloco)
                if tamanho > MAX_UPLOAD_MB * 1024 * 1024:
                    break
                tmp.write(bloco)
        if tamanho > MAX_UPLOAD_MB * 1024 * 1024:
            os.remove(caminho_fila)
            logger.warning(f"Arquivo muito grande: {tamanho} bytes")
            raise HTTPException(status_code=413, detail=f"Arquivo muito grande. Limite de {MAX_UPLOAD_MB} MB.")

        logger.info(f"Arquivo validado: {file.filename} ({tamanho} bytes). Iniciando Background Task...")

        if pasta_id is not None:
            db.vincular_arquivo(pasta_id, arquivo)
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.registrar_job(arquivo, agora, "fila", mensagem="Aguardando OCR")

        async def progresso_do_arquivo(msg: dict):
            if isinstance(msg, dict) and "resumos_mensais" not in msg and "movimentacoes_cc" not in msg:
                msg.setdefault("arquivo", arquivo)
            await broadcast_progress(msg)

        async def process_task():
            try:
                if fila_ocr.locked():
                    await progresso_do_arquivo({
                        "message": f"{file.filename}: na fila, aguardando o término do arquivo em processamento...",
                        "progress": 0,
                    })
                async with manter_acordado(), fila_ocr:
                    with open(caminho_fila, "rb") as f:
                        file_content = f.read()
                    os.remove(caminho_fila)
                    res = await coordinator.process_document_staged(
                        file_content,
                        arquivo_nome=file.filename,
                        progress_callback=progresso_do_arquivo
                    )
                    del file_content
                await broadcast_progress(res.model_dump() if hasattr(res, "model_dump") else res)
            except Exception as task_err:
                if os.path.exists(caminho_fila):
                    os.remove(caminho_fila)
                logger.error(f"Erro na tarefa background: {task_err}", exc_info=True)
                db.atualizar_job(arquivo, agora, "erro", mensagem=str(task_err))
                await broadcast_progress({
                    "type": "ERROR",
                    "arquivo": arquivo,
                    "message": f"ERRO CRÍTICO: {str(task_err)}",
                    "progress": -1
                })

        background_tasks.add_task(process_task)

        return {
            "status": "processing",
            "message": "Auditoria iniciada em background. Acompanhe pelo progresso.",
            "filename": file.filename,
            "arquivo": arquivo,
            "pasta_id": pasta_id,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao iniciar processamento: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao iniciar: {str(e)}")
    

@app.get("/historico")
async def listar_historico(limite: int = 100):
    """Lista arquivos processados (jobs reais: resumos + CC)."""
    try:
        registros = db.listar_historico_arquivos(limite=limite)
        return {
            "total": len(registros),
            "registros": registros
        }
    except Exception as e:
        logger.error(f"Erro ao listar historico: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao listar histórico: {str(e)}")


@app.get("/historico/{arquivo_nome}")
async def listar_por_arquivo(arquivo_nome: str):
    """Retorna o último resultado completo de um arquivo (MySQL)."""
    try:
        return db.obter_resultados_arquivo(arquivo_nome)
    except Exception as e:
        logger.error(f"Erro ao listar arquivo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao listar arquivo: {str(e)}")


@app.get("/resultados/{arquivo_nome}")
async def obter_resultados(arquivo_nome: str):
    """Recupera resultados do MySQL sem depender do WebSocket."""
    try:
        data = db.obter_resultados_arquivo(arquivo_nome)
        job = data.get("job") or {}
        # Enquanto processa, não devolve resultado parcial como "final"
        if job.get("status") == "processando":
            return {
                "arquivo": arquivo_nome,
                "status": "processando",
                "total_resumos": data["total_resumos"],
                "total_cc": data["total_cc"],
                "job": job,
            }
        # Volume sem extratos (ex.: celebração) termina sem resumos/CC, mas com OCR gravado
        if data["total_resumos"] == 0 and data["total_cc"] == 0 and job.get("status") not in ("concluido", "erro"):
            raise HTTPException(status_code=404, detail="Nenhum resultado encontrado para este arquivo.")
        data["status"] = job.get("status") or "concluido"
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter resultados: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/job/{arquivo_nome}")
async def obter_job(arquivo_nome: str):
    job = db.obter_ultimo_job(arquivo_nome)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return job


# ─────────────────────────────────────────────────────────────────────────────
# ANÁLISE DOCUMENTAL (dossiê de um convênio = vários arquivos já processados)
# ─────────────────────────────────────────────────────────────────────────────

async def _processar_dossie(dossie_id: int, arquivos: list):
    async def progresso(msg: str, pct: int):
        db.atualizar_dossie(dossie_id, progresso=pct, mensagem=msg)
        await broadcast_progress({"type": "DOSSIE_PROGRESS", "dossie_id": dossie_id, "message": msg, "progress": pct})

    try:
        async with manter_acordado():
            resultado = await executar_analise(db, arquivos, llm=get_llm(), progress=progresso)
        db.atualizar_dossie(dossie_id, status="concluido", progresso=100, mensagem="Concluído", resultado=resultado)
        await broadcast_progress({"type": "DOSSIE_DONE", "dossie_id": dossie_id, "progress": 100})
    except Exception as exc:
        logger.error("Dossiê %s falhou: %s", dossie_id, exc, exc_info=True)
        db.atualizar_dossie(dossie_id, status="erro", mensagem=str(exc))
        await broadcast_progress({"type": "DOSSIE_ERROR", "dossie_id": dossie_id, "message": str(exc), "progress": -1})


@app.post("/dossies")
async def criar_dossie(payload: dict, background_tasks: BackgroundTasks):
    """Cria o dossiê e roda inventário + extração + Relatório de Validação em background."""
    nome = (payload.get("nome") or "").strip()
    arquivos = [a for a in (payload.get("arquivos") or []) if isinstance(a, str) and a.strip()]
    if not nome or not arquivos:
        raise HTTPException(status_code=400, detail="Informe 'nome' e ao menos um arquivo em 'arquivos'.")
    sem_ocr = [a for a in arquivos if not db.obter_ultimo_job(a)]
    if sem_ocr:
        raise HTTPException(status_code=400, detail=f"Arquivo(s) ainda não processado(s): {', '.join(sem_ocr)}")
    dossie_id = db.criar_dossie(nome, arquivos)
    background_tasks.add_task(_processar_dossie, dossie_id, arquivos)
    return {"id": dossie_id, "status": "processando"}


@app.get("/dossies")
async def listar_dossies(limite: int = 100):
    return {"dossies": db.listar_dossies(limite)}


@app.get("/dossies/{dossie_id}")
async def obter_dossie(dossie_id: int):
    dossie = db.obter_dossie(dossie_id)
    if not dossie:
        raise HTTPException(status_code=404, detail="Dossiê não encontrado")
    if dossie["status"] == "concluido" and precisa_recalcular(dossie.get("resultado")):
        try:
            await asyncio.to_thread(_recalcular, dossie)
        except Exception as exc:
            logger.warning("Recálculo automático do dossiê %s falhou: %s", dossie_id, exc, exc_info=True)
    return dossie


@app.post("/dossies/{dossie_id}/reprocessar")
async def reprocessar_dossie(dossie_id: int, background_tasks: BackgroundTasks):
    dossie = db.obter_dossie(dossie_id)
    if not dossie:
        raise HTTPException(status_code=404, detail="Dossiê não encontrado")
    if dossie["status"] == "processando":
        raise HTTPException(status_code=409, detail="Dossiê já está em processamento")
    db.atualizar_dossie(dossie_id, status="processando", progresso=0, mensagem="Na fila")
    background_tasks.add_task(_processar_dossie, dossie_id, dossie["arquivos"])
    return {"id": dossie_id, "status": "processando"}


def _recalcular(dossie: dict) -> dict:
    resultado = recalcular_analise(db, dossie["resultado"])
    db.atualizar_dossie(dossie["id"], resultado=resultado)
    dossie["resultado"] = resultado
    return dossie


def _dossie_concluido(dossie_id: int) -> dict:
    dossie = db.obter_dossie(dossie_id)
    if not dossie:
        raise HTTPException(status_code=404, detail="Dossiê não encontrado")
    if dossie["status"] != "concluido" or not dossie.get("resultado"):
        raise HTTPException(status_code=409, detail="Dossiê ainda não concluído")
    # Análises gravadas antes do formato GECOV são atualizadas sem nova chamada à IA
    if precisa_recalcular(dossie["resultado"]):
        try:
            _recalcular(dossie)
        except Exception as exc:
            logger.warning("Recálculo automático do dossiê %s falhou: %s", dossie_id, exc, exc_info=True)
    return dossie


@app.post("/dossies/{dossie_id}/recalcular")
async def recalcular_dossie(dossie_id: int):
    """Refaz varredura, cruzamentos, relatório e parecer sobre a classificação já gravada (sem IA)."""
    dossie = db.obter_dossie(dossie_id)
    if not dossie:
        raise HTTPException(status_code=404, detail="Dossiê não encontrado")
    if dossie["status"] != "concluido" or not dossie.get("resultado"):
        raise HTTPException(status_code=409, detail="Dossiê ainda não concluído")
    try:
        await asyncio.to_thread(_recalcular, dossie)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return dossie


def _arquivo(conteudo: bytes, nome: str, media_type: str) -> Response:
    return Response(
        content=conteudo,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nome)}"},
    )


@app.get("/dossies/{dossie_id}/saida-tct")
async def saida_tct_dossie(dossie_id: int):
    """Modelo de AD sugerido (pelo regime jurídico) e indícios de inexecução."""
    return sugerir_modelo(_dossie_concluido(dossie_id)["resultado"])


@app.get("/dossies/{dossie_id}/minuta-ad")
async def minuta_ad_dossie(dossie_id: int, modelo: str | None = None, formato: str = "pdf"):
    """Minuta da Análise Documental no modelo do Novo TCT (DEC_43635, DEC_46319 ou INEXECUCAO), em PDF ou DOCX."""
    dossie = _dossie_concluido(dossie_id)
    try:
        conteudo, nome = gerar_minuta_ad(dossie["resultado"], dossie["nome"], modelo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if formato == "docx":
        return _arquivo(conteudo, nome, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    try:
        pdf = await asyncio.to_thread(docx_para_pdf, conteudo)
    except ConversaoPdfIndisponivel as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return _arquivo(pdf, os.path.splitext(nome)[0] + ".pdf", "application/pdf")


@app.get("/dossies/{dossie_id}/conciliacao")
async def conciliacao_dossie(dossie_id: int, inexecucao: bool = False):
    """Planilha de Conciliação Financeira (GECOV/GECON) pré-preenchida."""
    dossie = _dossie_concluido(dossie_id)
    conteudo, nome = gerar_conciliacao(dossie["resultado"], inexecucao)
    return _arquivo(conteudo, nome, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


async def _docx_ou_pdf(conteudo: bytes, nome: str, formato: str) -> Response:
    if formato == "docx":
        return _arquivo(conteudo, nome, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    try:
        pdf = await asyncio.to_thread(docx_para_pdf, conteudo)
    except ConversaoPdfIndisponivel as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return _arquivo(pdf, os.path.splitext(nome)[0] + ".pdf", "application/pdf")


@app.get("/dossies/{dossie_id}/solicitacao")
async def solicitacao_dossie(dossie_id: int, formato: str = "pdf"):
    """Anexo – Solicitação de Documentos (diligência ao convenente), no modelo da GECOV."""
    dossie = _dossie_concluido(dossie_id)
    try:
        conteudo, nome = gerar_solicitacao(dossie["resultado"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return await _docx_ou_pdf(conteudo, nome, formato)


@app.get("/dossies/{dossie_id}/oficio")
async def oficio_dossie(dossie_id: int, formato: str = "docx"):
    """Minuta do Ofício de solicitação de documentos complementares (campos do SEI destacados em amarelo)."""
    dossie = _dossie_concluido(dossie_id)
    try:
        conteudo, nome = gerar_oficio(dossie["resultado"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return await _docx_ou_pdf(conteudo, nome, formato)


@app.delete("/dossies/{dossie_id}")
async def excluir_dossie(dossie_id: int):
    if not db.excluir_dossie(dossie_id):
        raise HTTPException(status_code=404, detail="Dossiê não encontrado")
    return {"success": True}


# ─────────────────────────────────────────────────────────────────────────────
# PASTAS DE CONVÊNIO (destino obrigatório dos volumes enviados)
# ─────────────────────────────────────────────────────────────────────────────

def _pasta_ou_404(pasta_id: int) -> dict:
    pasta = db.obter_pasta(pasta_id)
    if not pasta:
        raise HTTPException(status_code=404, detail="Pasta não encontrada")
    return pasta


@app.get("/pastas")
async def listar_pastas():
    return {"pastas": db.listar_pastas(), "sem_pasta": db.arquivos_sem_pasta()}


@app.post("/pastas")
async def criar_pasta(payload: dict):
    nome = (payload.get("nome") or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Informe o nome da pasta.")
    pasta_id = db.criar_pasta(
        nome,
        (payload.get("numero_convenio") or "").strip(),
        (payload.get("convenente") or "").strip(),
        (payload.get("observacao") or "").strip(),
    )
    return db.obter_pasta(pasta_id)


@app.get("/pastas/{pasta_id}")
async def obter_pasta(pasta_id: int):
    return _pasta_ou_404(pasta_id)


@app.patch("/pastas/{pasta_id}")
async def atualizar_pasta(pasta_id: int, payload: dict):
    _pasta_ou_404(pasta_id)
    campos = {k: (v.strip() if isinstance(v, str) else v) for k, v in payload.items()}
    if "nome" in campos and not campos["nome"]:
        raise HTTPException(status_code=400, detail="O nome da pasta não pode ficar vazio.")
    db.atualizar_pasta(pasta_id, campos)
    return db.obter_pasta(pasta_id)


@app.delete("/pastas/{pasta_id}")
async def excluir_pasta(pasta_id: int, apagar_dados: bool = True):
    pasta = _pasta_ou_404(pasta_id)
    if any(a["status"] in ("fila", "processando") for a in pasta["arquivos"]):
        raise HTTPException(status_code=409, detail="Há volumes sendo processados nesta pasta. Aguarde terminar.")
    db.excluir_pasta(pasta_id, apagar_dados=apagar_dados)
    return {"success": True}


@app.put("/pastas/{pasta_id}/ordem")
async def reordenar_pasta(pasta_id: int, payload: dict):
    pasta = _pasta_ou_404(pasta_id)
    arquivos = payload.get("arquivos") or []
    if sorted(arquivos) != sorted(a["arquivo_nome"] for a in pasta["arquivos"]):
        raise HTTPException(status_code=400, detail="A nova ordem deve conter exatamente os arquivos da pasta.")
    db.reordenar_pasta(pasta_id, arquivos)
    return db.obter_pasta(pasta_id)


@app.post("/pastas/{pasta_id}/arquivos")
async def mover_arquivo_para_pasta(pasta_id: int, payload: dict):
    """Coloca na pasta um arquivo já processado (ex.: enviado antes de existirem pastas)."""
    _pasta_ou_404(pasta_id)
    arquivo = (payload.get("arquivo_nome") or "").strip()
    if not arquivo or not db.obter_ultimo_job(arquivo):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    db.vincular_arquivo(pasta_id, arquivo)
    return db.obter_pasta(pasta_id)


@app.delete("/pastas/{pasta_id}/arquivos/{arquivo_nome}")
async def remover_arquivo_da_pasta(pasta_id: int, arquivo_nome: str, apagar_dados: bool = False):
    pasta = _pasta_ou_404(pasta_id)
    item = next((a for a in pasta["arquivos"] if a["arquivo_nome"] == arquivo_nome), None)
    if not item:
        raise HTTPException(status_code=404, detail="Arquivo não está nesta pasta")
    if item["status"] in ("fila", "processando"):
        raise HTTPException(status_code=409, detail="O arquivo ainda está sendo processado.")
    db.remover_arquivo_pasta(pasta_id, arquivo_nome, apagar_dados=apagar_dados)
    return db.obter_pasta(pasta_id)


@app.post("/pastas/{pasta_id}/analise")
async def analisar_pasta(pasta_id: int, background_tasks: BackgroundTasks):
    """Gera a Análise Documental com todos os volumes da pasta, na ordem do processo."""
    pasta = _pasta_ou_404(pasta_id)
    if any(a["status"] in ("fila", "processando") for a in pasta["arquivos"]):
        raise HTTPException(status_code=409, detail="Aguarde o término do processamento de todos os volumes.")
    if any(a["status"] == "processando" for a in pasta["analises"]):
        raise HTTPException(status_code=409, detail="Já existe uma análise em andamento para esta pasta.")
    arquivos = [a["arquivo_nome"] for a in pasta["arquivos"] if a["status"] == "concluido"]
    if not arquivos:
        raise HTTPException(status_code=400, detail="A pasta não tem volumes processados com sucesso.")
    dossie_id = db.criar_dossie(pasta["nome"], arquivos, pasta_id=pasta_id)
    background_tasks.add_task(_processar_dossie, dossie_id, arquivos)
    return {"id": dossie_id, "status": "processando"}


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
    """
    if not auth.pode_limpar_banco():
        raise HTTPException(status_code=403, detail="Limpeza do banco desativada em produção.")
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


@app.get("/movimentacoes-cc/{arquivo_nome}")
async def listar_movimentacoes_cc(arquivo_nome: str):
    """Retorna todas as movimentações de conta corrente de um arquivo."""
    try:
        registros = db.listar_movimentacoes_cc(arquivo_nome)
        return {"arquivo": arquivo_nome, "total": len(registros), "movimentacoes": registros}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/movimentacao-cc/{row_id}")
async def atualizar_movimentacao_cc(row_id: int, payload: dict):
    """
    Atualiza um campo de uma movimentação CC.
    """
    campo = payload.get("campo")
    valor = payload.get("valor")
    if not campo or valor is None:
        raise HTTPException(status_code=400, detail="Informe 'campo' e 'valor' no body.")
    ok = db.atualizar_campo_cc(row_id, campo, valor)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Linha {row_id} não encontrada ou campo inválido.")
    return {"success": True, "id": row_id, "campo": campo, "novo_valor": valor}


@app.patch("/resumo-mensal/{arquivo_nome}/{pagina}")
async def atualizar_resumo_mensal(arquivo_nome: str, pagina: int, payload: dict):
    """
    Atualiza um campo numérico de um resumo mensal.
    """
    campo = payload.get("campo")
    valor = payload.get("valor")
    if not campo or valor is None:
        raise HTTPException(status_code=400, detail="Informe 'campo' e 'valor' no body.")
    try:
        valor_float = float(valor)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="O campo 'valor' deve ser numérico.")
    ok = db.atualizar_campo_resumo(arquivo_nome, pagina, campo, valor_float)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Resumo (pág. {pagina}) não encontrado ou campo inválido.")
    return {"success": True, "arquivo": arquivo_nome, "pagina": pagina, "campo": campo, "novo_valor": valor_float}


@app.post("/calculate")
async def calculate_indices(payload: dict):
    """
    Calculates index correction using BCB API.
    """
    value = payload.get("value", 0.0)
    start_date = payload.get("start_date")
    end_date = payload.get("end_date") or datetime.now().strftime("%d/%m/%Y")
    method = payload.get("method", "cdi")
    
    if not start_date:
        return {"original_value": value, "corrected_value": value, "factor": 1.0, "method": method}
        
    result = calculator.calculate_correction(value, start_date, end_date, method)
    return result

@app.post("/export/pdf")
async def export_pdf(payload: dict):
    """
    Generates and returns a PDF report.
    """
    try:
        pdf_buffer = export_service.generate_pdf(payload)
        return StreamingResponse(
            pdf_buffer, 
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=Parecer_Auditoria_{datetime.now().strftime('%Y%m%d')}.pdf"}
        )
    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/export/excel")
async def export_excel(payload: dict):
    """
    Generates and returns an Excel report.
    """
    try:
        excel_buffer = export_service.generate_excel(payload)
        return StreamingResponse(
            excel_buffer, 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=Dados_Auditoria_{datetime.now().strftime('%Y%m%d')}.xlsx"}
        )
    except Exception as e:
        logger.error(f"Error generating Excel: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    logger.info("Iniciando Convenio 2.0 Backend na porta 5053...")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=5053, reload=True)
