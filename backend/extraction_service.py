from backend.parser_service import DeterministicParser
from backend.monthly_summary_parser import MonthlySummaryParser
from backend.caixa_summary_parser import CaixaSummaryParser
from backend.conta_corrente_parser import ContaCorrenteParser
from backend.groq_parser import GroqParser
from backend.ocr_service import HybridOCR
from backend.models import DocumentResponse
from backend.database import ExtractionDatabase
from backend.progress_manager import ProgressManager
import asyncio
import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)

def sanitize_filename(filename: str) -> str:
    """Remove caracteres inválidos para nomes de arquivos no Windows"""
    import re
    return re.sub(r'[^\w\.-]', '_', filename)

class ExtractionCoordinator:
    def __init__(self):
        self.parser = DeterministicParser()
        self.summary_parser = MonthlySummaryParser()
        self.caixa_parser = CaixaSummaryParser()
        self.cc_parser = ContaCorrenteParser()
        self.groq_parser = GroqParser()
        self.ocr = HybridOCR()
        self.db = ExtractionDatabase()
        groq_status = "ativo" if self.groq_parser.enabled else "desativado"
        logger.info("Sistema produção: HybridOCR (PDF nativo+Tesseract) + Groq Plan B (%s)", groq_status)

    def fuzzy_value_exists(self, value: float, text: str) -> bool:
        """Verifica se um valor numérico existe no texto em algum formato (BRL ou decimal)"""
        if abs(value) < 0.01:
            return True
            
        val_str = f"{value:.2f}"
        int_part, dec_part = val_str.split('.')
        
        if len(int_part) > 3:
            reversed_int = int_part[::-1]
            brl_int = ".".join([reversed_int[i:i+3] for i in range(0, len(reversed_int), 3)])[::-1]
            brl_val = f"{brl_int},{dec_part}"
            if brl_val in text: return True
            
        if f"{int_part},{dec_part}" in text: return True
        if f"{int_part}.{dec_part}" in text: return True
        if int_part + dec_part in text: return True
        
        return False

    def _validate_groq_resumo(self, resumo_groq: dict, page_text: str, page_num: int) -> Optional[dict]:
        campos = resumo_groq.get("campos", {})
        # Normaliza tipos
        for k, v in list(campos.items()):
            if isinstance(v, str):
                try:
                    campos[k] = float(v.replace('.', '').replace(',', '.')) if ',' in v else float(v)
                except Exception:
                    campos[k] = 0.0
        resumo_groq["campos"] = campos

        sa = abs(campos.get("saldo_anterior", 0) or 0)
        st = abs(campos.get("saldo_atual", 0) or 0)

        if sa < 0.01 and st < 0.01:
            logger.warning("Página %s: Groq retornou resumo ZERADO. Ignorando.", page_num)
            return None

        # OCR Tesseract é ruidoso: fuzzy mais permissivo (30%)
        total_check = 0
        passed_check = 0
        for _, c_val in campos.items():
            if abs(c_val or 0) > 0.01:
                total_check += 1
                if self.fuzzy_value_exists(c_val, page_text):
                    passed_check += 1

        if total_check > 0 and (passed_check / total_check) < 0.3:
            logger.warning(
                "Página %s: Rejeitado por baixa confiança (Fuzzy: %s/%s).",
                page_num, passed_check, total_check,
            )
            return None
        return resumo_groq

    async def process_document_staged(
        self, 
        file_content: bytes, 
        arquivo_nome: str = "documento.pdf",
        progress_callback: Optional[Callable] = None
    ) -> DocumentResponse:
        """
        Fluxo produção:
        1. OCR híbrido (PDF nativo + Tesseract) com persistência por página
        2. Parsers determinísticos BB/Caixa/CC + Groq Plan B
        3. Gravação imediata no MySQL (fonte da verdade)
        4. Leitura final do banco
        """
        progress = ProgressManager(callback=progress_callback)
        arquivo_nome = sanitize_filename(arquivo_nome)
        
        from datetime import datetime
        data_processamento_unica = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            logger.info("=" * 60)
            logger.info("PROCESSAMENTO PRODUÇÃO — %s", arquivo_nome)
            logger.info("=" * 60)

            # Job: iniciado — limpa dados antigos ANTES do OCR
            # (evita o frontend carregar resultado anterior via poll)
            self.db.registrar_job(
                arquivo_nome=arquivo_nome,
                data_processamento=data_processamento_unica,
                status="processando",
                mensagem="OCR iniciado",
            )
            self.db.limpar_arquivo(arquivo_nome)
            logger.info("Dados antigos de '%s' removidos (job novo)", arquivo_nome)
            
            ocr_pages = await self.ocr.extract_pages_detailed(
                file_content, progress_callback=progress_callback
            )
            
            if not ocr_pages:
                await progress.error("Falha na leitura OCR (PDF nativo/Tesseract)")
                self.db.atualizar_job(
                    arquivo_nome, data_processamento_unica, "erro",
                    mensagem="OCR vazio",
                )
                return DocumentResponse(
                    resultados_por_pagina={},
                    resumos_mensais={},
                    ocr_bruto="Falha na leitura OCR",
                )

            page_texts = [p.text for p in ocr_pages]
            consolidated_text = "\n[NOVA PAGINA]\n".join(page_texts)

            try:
                with open("raw_ocr_debug.txt", "w", encoding="utf-8") as f:
                    f.write(consolidated_text)
            except Exception as e:
                logger.warning("Não foi possível gravar raw_ocr_debug.txt: %s", e)
            
            logger.info("OCR concluído: %s páginas", len(page_texts))

            # Persiste OCR página a página
            for idx, page in enumerate(ocr_pages):
                self.db.salvar_ocr_pagina(
                    arquivo_nome=arquivo_nome,
                    data_processamento=data_processamento_unica,
                    pagina=idx + 1,
                    engine=page.engine,
                    texto=page.text,
                )
            logger.info("OCR persistido no MySQL (%s páginas)", len(ocr_pages))
            
            await progress.start(len(page_texts))
            
            total_resumos_salvos = 0
            total_cc_salvos = 0
            consecutive_empty_pages = 0
            mem_resumos = {}
            mem_cc = []
            
            STOP_KEYWORDS = [
                "INFORMACOES COMPLEMENTARES",
                "ESTE DOCUMENTO E PARTE INTEGRANTE",
            ]
            # NÃO parar em "ESTADO DE MINAS GERAIS" / "CONTRATO" / "PAPA JOÃO":
            # PDFs de convênio misturam extratos BB com capas SETOP no meio do arquivo.

            for idx, page_text in enumerate(page_texts):
                page_num = idx + 1
                logger.info("--- PROCESSANDO PAGINA %s ---", page_num)
                await progress.update_parser(page_num, len(page_texts), False)
                
                resumo = None
                cc_result = None
                fonte_parser = None

                # ── Conta corrente (determinístico → Groq fallback) ──
                try:
                    cc_result = self.cc_parser.parse_conta_corrente(page_text, page_num)

                    page_upper_early = page_text.upper()
                    parece_cc = self.cc_parser.is_conta_corrente_page(page_text, page_num) or (
                        "LANÇAMENTOS" in page_upper_early or "LANCAMENTOS" in page_upper_early
                    )
                    if (not cc_result or not cc_result.get("transacoes")) and parece_cc:
                        logger.info("Página %s: CC determinístico vazio → Groq CC", page_num)
                        cc_groq = await asyncio.to_thread(self.groq_parser.parse_conta_corrente, page_text, page_num)
                        if cc_groq and cc_groq.get("transacoes"):
                            cc_result = cc_groq

                    if cc_result and cc_result.get("transacoes"):
                        header = cc_result.get("header", {})
                        for tx in cc_result["transacoes"]:
                            self.db.salvar_movimentacao_cc(
                                arquivo_nome=arquivo_nome,
                                data_processamento=data_processamento_unica,
                                pagina=page_num,
                                header=header,
                                transacao=tx,
                            )
                            mem_cc.append({**header, **tx, "pagina": page_num})
                            total_cc_salvos += 1
                        logger.info(
                            "✓ Página %s: %s lançamentos CC GRAVADOS",
                            page_num, len(cc_result["transacoes"]),
                        )
                except Exception as cc_err:
                    logger.error("Página %s: Erro ao processar CC: %s", page_num, cc_err)

                # ── Resumo investimento (BB / Caixa / Groq) ──
                page_upper = page_text.upper().replace('ÃŠ', 'E').replace('Ã', 'A')
                
                is_caixa = any(k in page_upper for k in ["CAIXA", "GOVCONTA", "EXTRATO FUNDO", "INFORMATIVO MENSUAL"])
                is_bb = any(k in page_upper for k in ["BANCO DO BRASIL", "CBI", "RESUMO DO MES", "DEMONSTRATIVO DE RENTABILIDADE"])

                try:
                    if is_caixa:
                        logger.info("Página %s: modelo CAIXA", page_num)
                        resumo_det = self.caixa_parser.parse_resumo(page_text, page_num)
                        fonte_parser = "caixa"
                    elif is_bb or "RESUMO DO" in page_upper:
                        logger.info("Página %s: modelo BB", page_num)
                        resumo_det = self.summary_parser.parse_resumo(page_text, page_num)
                        fonte_parser = "bb"
                    else:
                        resumo_det = self.summary_parser.parse_resumo(page_text, page_num)
                        fonte_parser = "bb_fallback"
                except Exception as e:
                    logger.error("Página %s: Erro parser determinístico: %s", page_num, e)
                    resumo_det = None
                
                has_resumo_header = "RESUMO DO" in page_upper
                has_bank_context = "SALDO ANTERIO" in page_upper and ("RENDIMENTO" in page_upper or "RESUMO" in page_upper)
                is_caixa_context = "EXTRATO FUNDO" in page_upper or "SALDO BRUTO" in page_upper
                parece_extrato = has_resumo_header or has_bank_context or is_caixa_context
                
                if "COMPROVANTE DE" in page_upper and not has_resumo_header:
                    parece_extrato = False

                if resumo_det and not resumo_det.get("math_error"):
                    resumo = resumo_det
                    logger.info("Página %s: ✓ Janela matemática OK (%s)", page_num, fonte_parser)
                elif parece_extrato:
                    # Se determinístico veio com math_error mas tem campos, ainda tenta Groq;
                    # se Groq falhar, aceita o parcial com math_error.
                    logger.info("Página %s: determinístico falhou → Groq Plan B", page_num)
                    try:
                        resumo_groq = await asyncio.to_thread(self.groq_parser.parse_resumo, page_text, page_num)
                        if resumo_groq:
                            validated = self._validate_groq_resumo(resumo_groq, page_text, page_num)
                            if validated:
                                resumo = validated
                                fonte_parser = "groq"
                                if resumo.get("math_error"):
                                    logger.warning("Página %s: Groq com math_error — salvando mesmo assim", page_num)
                                else:
                                    logger.info("Página %s: ✓ Groq recuperou o resumo", page_num)
                        if not resumo and resumo_det and resumo_det.get("campos"):
                            # Fallback: salva tentativa por rótulos/janela imperfeita
                            resumo = resumo_det
                            logger.warning("Página %s: salvando resumo determinístico com math_error", page_num)
                    except Exception as e:
                        logger.error("Página %s: Erro Groq: %s", page_num, e)
                        if resumo_det and resumo_det.get("campos"):
                            resumo = resumo_det
                
                if resumo:
                    consecutive_empty_pages = 0
                    try:
                        campos = resumo["campos"]
                        math_ok = not bool(resumo.get("math_error"))
                        self.db.salvar_resumo_individual(
                            arquivo_nome=arquivo_nome,
                            pagina=page_num,
                            campos=campos,
                            data_processamento=data_processamento_unica,
                            fonte_parser=fonte_parser,
                            math_ok=math_ok,
                        )
                        mem_resumos[page_num] = {
                            "tipo": "RESUMO_MENSAL",
                            "pagina": page_num,
                            "campos": campos,
                            "fonte_parser": fonte_parser,
                            "math_ok": math_ok,
                        }
                        total_resumos_salvos += 1
                        await progress.update_parser(page_num, len(page_texts), True)
                        logger.info("✓ Página %s: Resumo GRAVADO (%s)", page_num, fonte_parser)
                    except Exception as db_err:
                        logger.error("Erro ao salvar resumo (Página %s): %s", page_num, db_err)
                        raise
                else:
                    if not cc_result:
                        consecutive_empty_pages += 1
                    else:
                        consecutive_empty_pages = 0
                    
                    found_stop = any(stop_k in page_upper for stop_k in STOP_KEYWORDS)
                    if found_stop and total_resumos_salvos > 0:
                        logger.info("Página %s: sinal de parada. Interrompendo.", page_num)
                        break
            
            await progress.update_saving(total_resumos_salvos)
            
            logger.info(
                "PROCESSAMENTO CONCLUÍDO: %s resumos + %s CC",
                total_resumos_salvos, total_cc_salvos,
            )
            
            resumos_db = self.db.listar_resumos_mensais(arquivo_nome)
            movimentacoes_cc = self.db.listar_movimentacoes_cc(arquivo_nome)
            
            if not resumos_db and total_resumos_salvos > 0:
                logger.warning("Usando resumos em memória (leitura DB vazia)")
                resumos_db = mem_resumos
                
            if not movimentacoes_cc and mem_cc:
                logger.warning("Usando CC em memória (leitura DB vazia)")
                movimentacoes_cc = mem_cc

            if len(resumos_db) != total_resumos_salvos:
                logger.warning(
                    "ALERTA persistência: gravados %s resumos, lidos %s",
                    total_resumos_salvos, len(resumos_db),
                )

            self.db.atualizar_job(
                arquivo_nome=arquivo_nome,
                data_processamento=data_processamento_unica,
                status="concluido",
                total_paginas=len(page_texts),
                total_resumos=len(resumos_db),
                total_cc=len(movimentacoes_cc),
                mensagem="OK",
            )

            await progress.complete(total_resumos_salvos)

            return DocumentResponse(
                resultados_por_pagina={},
                resumos_mensais=resumos_db,
                movimentacoes_cc=movimentacoes_cc,
                ocr_bruto=consolidated_text[:5000],
            )
        
        except Exception as e:
            logger.error("Erro no processamento: %s", e, exc_info=True)
            try:
                self.db.atualizar_job(
                    arquivo_nome=arquivo_nome,
                    data_processamento=data_processamento_unica,
                    status="erro",
                    mensagem=str(e)[:500],
                )
            except Exception:
                pass
            await progress.error(str(e))
            raise
