from backend.parser_service import DeterministicParser
from backend.monthly_summary_parser import MonthlySummaryParser
from backend.caixa_summary_parser import CaixaSummaryParser
from backend.conta_corrente_parser import ContaCorrenteParser
from backend.groq_parser import GroqParser
from backend.ocr_service import GoogleVisionOCR
from backend.models import DocumentResponse
from backend.database import ExtractionDatabase
from backend.progress_manager import ProgressManager
import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)

def sanitize_filename(filename: str) -> str:
    """Remove caracteres inválidos para nomes de arquivos no Windows"""
    import re
    # Remove tudo que não é letra, número, ponto, hífen ou underline
    return re.sub(r'[^\w\.-]', '_', filename)

class ExtractionCoordinator:
    def __init__(self):
        self.parser = DeterministicParser()
        self.summary_parser = MonthlySummaryParser()
        self.caixa_parser = CaixaSummaryParser()
        self.cc_parser = ContaCorrenteParser()
        self.groq_parser = GroqParser()  # USA GROQ (grátis e rápido)
        self.ocr = GoogleVisionOCR()
        self.db = ExtractionDatabase()
        logger.info("Sistema com Groq: 100% grátis, ultra-rápido, 95-98% precisão")

    def fuzzy_value_exists(self, value: float, text: str) -> bool:
        """Verifica se um valor numérico existe no texto em algum formato (BRL ou decimal)"""
        if abs(value) < 0.01:
            return True # Zeros são comuns e difíceis de validar
            
        # Formatos possíveis: 60.820,83 -> "60.820,83", "60820,83", "60820.83"
        val_str = f"{value:.2f}"
        int_part, dec_part = val_str.split('.')
        
        # Formato BRL: 60.820,83
        if len(int_part) > 3:
            # Tenta com pontos de milhar
            reversed_int = int_part[::-1]
            brl_int = ".".join([reversed_int[i:i+3] for i in range(0, len(reversed_int), 3)])[::-1]
            brl_val = f"{brl_int},{dec_part}"
            if brl_val in text: return True
            
        # Formato simples: 60820,83 ou 60820.83
        if f"{int_part},{dec_part}" in text: return True
        if f"{int_part}.{dec_part}" in text: return True
        
        # OCR pode comer o ponto/vírgula: 6082083
        if int_part + dec_part in text: return True
        
        return False

    async def process_document_staged(
        self, 
        file_content: bytes, 
        arquivo_nome: str = "documento.pdf",
        progress_callback: Optional[Callable] = None
    ) -> DocumentResponse:
        """
        Fluxo INCREMENTAL com Gravação Imediata + PROGRESSO EM TEMPO REAL:
        1. Executa OCR em todas as paginas (com notificação de progresso)
        2. Para cada página:
           a) Extrai resumo mensal (se existir)
           b) GRAVA IMEDIATAMENTE no banco
           c) Log detalhado da extração
           d) Notifica progresso via WebSocket
        3. No final: LÊ DO BANCO e retorna
        
        VANTAGENS:
        - Não perde dados na memória
        - Cada página é gravada independentemente
        - Fonte única de verdade: o banco
        - Usuário acompanha o progresso em tempo real
        """
        # Inicializa gerenciador de progresso
        progress = ProgressManager(callback=progress_callback)
        
        # Sanitiza nome do arquivo para evitar Erro 22 no Windows
        arquivo_nome = sanitize_filename(arquivo_nome)
        
        try:
            # Etapa 1: OCR por página
            logger.info("=" * 60)
            logger.info("INICIANDO PROCESSAMENTO COM GRAVACAO INCREMENTAL")
            logger.info("=" * 60)
            
            page_texts = await self.ocr.extract_text_pages(file_content, progress_callback=progress_callback)
            
            if not page_texts:
                await progress.error("Falha na leitura OCR")
                return DocumentResponse(resultados_por_pagina={}, resumos_mensais={}, ocr_bruto="Falha na leitura OCR")

            consolidated_text = "\n[NOVA PAGINA]\n".join(page_texts)

            # Log para depuração (Proteção contra Errno 22 se o arquivo estiver em uso)
            try:
                with open("raw_ocr_debug.txt", "w", encoding="utf-8") as f:
                    f.write(consolidated_text)
                logger.info("OCR debug gravado em raw_ocr_debug.txt")
            except Exception as e:
                logger.warning(f"Não foi possível gravar raw_ocr_debug.txt: {e}")
            
            logger.info(f"OCR concluido: {len(page_texts)} paginas extraidas")
            
            # LIMPA DADOS ANTIGOS DESTE ARQUIVO ANTES DE COMEÇAR
            self.db.limpar_arquivo(arquivo_nome)
            self.db.limpar_cc_arquivo(arquivo_nome)
            logger.info(f"Dados antigos de '{arquivo_nome}' removidos")
            
            # IMPORTANTE: Data única para toda a extração (evita páginas em datas diferentes)
            from datetime import datetime
            data_processamento_unica = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Inicia rastreamento de progresso
            await progress.start(len(page_texts))
            
            # Etapa 2: PROCESSA E GRAVA PÁGINA POR PÁGINA
            total_resumos_salvos = 0
            consecutive_empty_pages = 0
            
            # Lista de palavras-chave que indicam o FIM do extrato útil (Rodapés/Legais)
            # Ao encontrar estas palavras em uma página SEM resumos, interrompemos a busca.
            STOP_KEYWORDS = [
                "INFORMACOES COMPLEMENTARES",
                "ESTE DOCUMENTO E PARTE INTEGRANTE",
                "ESTADO DE MINAS GERAIS",
                "MEDIÇÃO Nº", "MEDIÇÃO N", "MEDIÃ‡ÃƒO",
                "CONTRATO Nº",
                "RODOVIA PAPA JOÃO PAULO", "PAPA JOÃƒO PAULO"
            ]

            for idx, page_text in enumerate(page_texts):
                page_num = idx + 1
                logger.info(f"\n--- PROCESSANDO PAGINA {page_num} ---")
                
                # Notifica progresso do parser
                await progress.update_parser(page_num, len(page_texts), False)
                
                resumo = None
                cc_result = None
                # ──────────────────────────────────────────────────────────────
                # ROTA : EXTRATO DE CONTA CORRENTE (BB)
                # ──────────────────────────────────────────────────────────────
                try:
                    cc_result = self.cc_parser.parse_conta_corrente(page_text, page_num)
                    if cc_result and cc_result.get("transacoes"):
                        logger.info(f"Página {page_num}: ✓ Detectado Extrato de Conta Corrente.")
                        header = cc_result.get("header", {})
                        for tx in cc_result["transacoes"]:
                            self.db.salvar_movimentacao_cc(
                                arquivo_nome=arquivo_nome,
                                data_processamento=data_processamento_unica,
                                pagina=page_num,
                                header=header,
                                transacao=tx
                            )
                        logger.info(f"✓ Pagina {page_num}: {len(cc_result['transacoes'])} lançamentos de CC GRAVADOS")
                except Exception as cc_err:
                    logger.error(f"Página {page_num}: Erro ao processar CC: {cc_err}")

                # ──────────────────────────────────────────────────────────────
                # ROTA : EXTRATO DE INVESTIMENTO (BB ou CAIXA)
                # ──────────────────────────────────────────────────────────────
                page_upper = page_text.upper().replace('ÃŠ', 'E').replace('Ã', 'A')
                
                is_caixa = any(k in page_upper for k in ["CAIXA", "GOVCONTA", "EXTRATO FUNDO", "INFORMATIVO MENSUAL"])
                is_bb = any(k in page_upper for k in ["BANCO DO BRASIL", "CBI", "RESUMO DO MES", "DEMONSTRATIVO DE RENTABILIDADE"])

                # 1) TENTATIVA DETERMINÍSTICA (Rápida e Grátis)
                try:
                    if is_caixa:
                        logger.info(f"Página {page_num}: Detectado modelo CAIXA (GovConta).")
                        resumo_det = self.caixa_parser.parse_resumo(page_text, page_num)
                    elif is_bb or "RESUMO DO" in page_upper:
                        logger.info(f"Página {page_num}: Detectado modelo BANCO DO BRASIL (ou layout compatível).")
                        resumo_det = self.summary_parser.parse_resumo(page_text, page_num)
                    else:
                        logger.info(f"Página {page_num}: Layout de investimento não reconhecido. Tentando BB como fallback...")
                        resumo_det = self.summary_parser.parse_resumo(page_text, page_num)
                except Exception as e:
                    logger.error(f"Página {page_num}: Erro no parser determinístico: {e}")
                    resumo_det = None

                # 2) ESTRATÉGIA AGRESSIVA: Se o determinístico falhou (None ou Erro), tenta Groq
                # Apenas se a página parecer ser um extrato (Contexto mais forte para evitar assinaturas)
                page_upper = page_text.upper().replace('ÃŠ', 'E').replace('Ã', 'A')
                
                # Requisito: Título de resumo ou par Saldo/Rendimento
                has_resumo_header = "RESUMO DO" in page_upper
                has_bank_context = "SALDO ANTERIO" in page_upper and ("RENDIMENTO" in page_upper or "RESUMO" in page_upper)
                
                is_caixa_context = "EXTRATO FUNDO" in page_upper or "SALDO BRUTO" in page_upper
                
                parece_extrato = has_resumo_header or has_bank_context or is_caixa_context
                
                # Rejeita comprovantes de transação avulsa que não são resumos
                if "COMPROVANTE DE" in page_upper and not has_resumo_header:
                    # Se for CC, não é resumo mensal
                    parece_extrato = False

                resumo = None
                if resumo_det and not resumo_det.get("math_error"):
                    resumo = resumo_det
                    logger.info(f"Página {page_num}: ✓ GOL! Janela Matemática perfeita encontrada.")
                elif parece_extrato:
                    # Se falhou o determinístico mas parece extrato, PLANO B (Groq)
                    logger.info(f"Página {page_num}: ⚠ Determinístico falhou/incompleto. Chamando Groq como Plano B...")
                    try:
                        resumo_groq = self.groq_parser.parse_resumo(page_text, page_num)
                        if resumo_groq:
                            # Validação Crítica 1: Evita salvar resumos "vazios" (tudo zero)
                            campos = resumo_groq.get("campos", {})
                            sa = abs(campos.get("saldo_anterior", 0) or 0)
                            st = abs(campos.get("saldo_atual", 0) or 0)
                            
                            if sa < 0.01 and st < 0.01:
                                logger.warning(f"Página {page_num}: Groq retornou resumo ZERADO (provável falso positivo). Ignorando.")
                                resumo = None
                            else:
                                # Validação Crítica 2: FUZZY CHECK (Os valores existem no texto?)
                                # Se pelo menos 50% dos valores não-zero não existirem no OCR, rejeitamos
                                total_check = 0
                                passed_check = 0
                                for c_nome, c_val in campos.items():
                                    if abs(c_val) > 0.01:
                                        total_check += 1
                                        if self.fuzzy_value_exists(c_val, page_text):
                                            passed_check += 1
                                
                                # Se temos valores mas nenhum bate com o OCR, é alucinação
                                if total_check > 0 and (passed_check / total_check) < 0.5:
                                    logger.warning(f"Página {page_num}: Rejeitado por baixa confiança (Fuzzy: {passed_check}/{total_check}). Provável alucinação.")
                                    resumo = None
                                else:
                                    resumo = resumo_groq
                                    if not resumo.get("math_error"):
                                        logger.info(f"Página {page_num}: ✓ Groq recuperou o resumo com perfeição matemática.")
                                    else:
                                        logger.warning(f"Página {page_num}: ⚠ Groq retornou dados, mas a conta não fecha. Salvando mesmo assim.")
                    except Exception as e:
                        logger.error(f"Página {page_num}: Erro ao chamar Groq: {e}")
                
                # VERIFICAÇÃO FINAL E SALVAMENTO
                if resumo:
                    # Zera o contador se encontrar algo
                    consecutive_empty_pages = 0
                    
                    try:
                        campos = resumo["campos"]
                        self.db.salvar_resumo_individual(
                            arquivo_nome=arquivo_nome,
                            pagina=page_num,
                            campos=campos,
                            data_processamento=data_processamento_unica
                        )
                        total_resumos_salvos += 1
                        await progress.update_parser(page_num, len(page_texts), True)
                        logger.info(f"✓ Pagina {page_num}: Resumo mensal GRAVADO no banco")
                    except Exception as db_err:
                        logger.error(f"Erro ao salvar no banco (Pagina {page_num}): {db_err}")
                else:
                    # Se não for resumo mensal, talvez seja CC que já salvamos acima
                    # Não incrementamos consecutive_empty_pages se for CC
                    if not cc_result:
                        consecutive_empty_pages += 1
                        logger.debug(f"  Pagina {page_num}: Sem resumo ou CC (Vazias: {consecutive_empty_pages})")
                    else:
                        consecutive_empty_pages = 0 # CC conta como página útil
                    
                    # VERIFICAÇÃO DE INTERRUPÇÃO (STOP CONDITION)
                    found_stop = any(stop_k in page_upper for stop_k in STOP_KEYWORDS)
                    
                    if found_stop and total_resumos_salvos > 0:
                        logger.info(f"Página {page_num}: Sinal de parada detectado em página vazia. Interrompendo busca.")
                        break
            
            # Notifica salvamento no banco
            await progress.update_saving(total_resumos_salvos)
            
            logger.info("\n" + "=" * 60)
            logger.info(f"PROCESSAMENTO CONCLUIDO: {total_resumos_salvos} resumos gravados")
            logger.info("=" * 60)
            
            # Etapa 3: LÊ DO BANCO (fonte única de verdade)
            logger.info("\nLENDO DADOS DO BANCO...")
            resumos_db = self.db.listar_resumos_mensais(arquivo_nome)
            movimentacoes_cc = self.db.listar_movimentacoes_cc(arquivo_nome)

            logger.info(f"✓ Lidos {len(resumos_db)} resumos + {len(movimentacoes_cc)} transações CC do banco")

            # Log de auditoria: compara gravado vs lido
            if len(resumos_db) != total_resumos_salvos:
                logger.warning(f"ALERTA: Gravados {total_resumos_salvos} mas lidos {len(resumos_db)} do banco!")

            # Notifica conclusão
            await progress.complete(total_resumos_salvos)

            return DocumentResponse(
                resultados_por_pagina={},  # Não usamos mais tabela principal
                resumos_mensais=resumos_db,
                movimentacoes_cc=movimentacoes_cc,
                ocr_bruto=consolidated_text[:30000]
            )
        
        except Exception as e:
            logger.error(f"Erro no processamento: {e}", exc_info=True)
            await progress.error(str(e))
            raise

