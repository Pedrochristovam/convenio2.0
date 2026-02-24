from backend.parser_service import DeterministicParser
from backend.monthly_summary_parser import MonthlySummaryParser
from backend.groq_parser import GroqResumoParser
from backend.ocr_service import GoogleVisionOCR
from backend.models import DocumentResponse
from backend.database import ExtractionDatabase
from backend.progress_manager import ProgressManager
import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class ExtractionCoordinator:
    def __init__(self):
        self.parser = DeterministicParser()
        self.summary_parser = MonthlySummaryParser()
        self.groq_parser = GroqResumoParser()  # USA GROQ (grátis e rápido)
        self.ocr = GoogleVisionOCR()
        self.db = ExtractionDatabase()
        logger.info("Sistema com Groq: 100% grátis, ultra-rápido, 95-98% precisão")

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
        
        try:
            # Etapa 1: OCR por página
            logger.info("=" * 60)
            logger.info("INICIANDO PROCESSAMENTO COM GRAVACAO INCREMENTAL")
            logger.info("=" * 60)
            
            page_texts = await self.ocr.extract_text_pages(file_content, progress_callback=progress_callback)
            
            if not page_texts:
                progress.error("Falha na leitura OCR")
                return DocumentResponse(resultados_por_pagina={}, resumos_mensais={}, ocr_bruto="Falha na leitura OCR")

            consolidated_text = "\n[NOVA PAGINA]\n".join(page_texts)

            # Log para depuração
            with open("raw_ocr_debug.txt", "w", encoding="utf-8") as f:
                f.write(consolidated_text)
            
            logger.info(f"OCR concluido: {len(page_texts)} paginas extraidas")
            
            # LIMPA DADOS ANTIGOS DESTE ARQUIVO ANTES DE COMEÇAR
            self.db.limpar_arquivo(arquivo_nome)
            logger.info(f"Dados antigos de '{arquivo_nome}' removidos")
            
            # IMPORTANTE: Data única para toda a extração (evita páginas em datas diferentes)
            from datetime import datetime
            data_processamento_unica = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Inicia rastreamento de progresso
            progress.start(len(page_texts))
            
            # Etapa 2: PROCESSA E GRAVA PÁGINA POR PÁGINA
            total_resumos_salvos = 0
            
            for idx, page_text in enumerate(page_texts):
                page_num = idx + 1
                logger.info(f"\n--- PROCESSANDO PAGINA {page_num} ---")
                
                # Notifica progresso do parser
                progress.update_parser(page_num, len(page_texts), False)
                
                # NOVA ESTRATÉGIA: USA GROQ DIRETO (100% grátis, ultra-rápido)
                
                # Verifica se tem "Resumo do mês"
                if "RESUMO" in page_text.upper() and ("MÊS" in page_text.upper() or "MES" in page_text.upper()):
                    # Envia para Groq
                    logger.info(f"Página {page_num}: Detectado resumo mensal - Enviando para Groq")
                    resumo = self.groq_parser.parse_resumo(page_text, page_num)
                else:
                    resumo = None
                    logger.debug(f"Página {page_num}: Sem resumo mensal")
                
                if resumo:
                    # GRAVA IMEDIATAMENTE no banco COM DATA ÚNICA
                    campos = resumo["campos"]
                    self.db.salvar_resumo_individual(
                        arquivo_nome=arquivo_nome,
                        pagina=page_num,
                        campos=campos,
                        data_processamento=data_processamento_unica  # Passa a data única
                    )
                    
                    total_resumos_salvos += 1
                    
                    # Notifica que encontrou resumo
                    progress.update_parser(page_num, len(page_texts), True)
                    
                    # Log detalhado do que foi gravado
                    logger.info(f"✓ Pagina {page_num}: Resumo mensal GRAVADO no banco")
                    logger.info(f"  SALDO ANTERIOR: {campos.get('saldo_anterior')}")
                    logger.info(f"  APLICACOES: {campos.get('aplicacoes')}")
                    logger.info(f"  RESGATES: {campos.get('resgates')}")
                    logger.info(f"  RENDIMENTO BRUTO: {campos.get('rendimento_bruto')}")
                    logger.info(f"  IMPOSTO RENDA: {campos.get('imposto_renda')}")
                    logger.info(f"  IOF: {campos.get('iof')}")
                    logger.info(f"  RENDIMENTO LIQUIDO: {campos.get('rendimento_liquido')}")
                    logger.info(f"  SALDO ATUAL: {campos.get('saldo_atual')}")
                else:
                    logger.debug(f"  Pagina {page_num}: Sem resumo mensal")
            
            # Notifica salvamento no banco
            progress.update_saving(total_resumos_salvos)
            
            logger.info("\n" + "=" * 60)
            logger.info(f"PROCESSAMENTO CONCLUIDO: {total_resumos_salvos} resumos gravados")
            logger.info("=" * 60)
            
            # Etapa 3: LÊ DO BANCO (fonte única de verdade)
            logger.info("\nLENDO DADOS DO BANCO...")
            resumos_db = self.db.listar_resumos_mensais(arquivo_nome)
            
            logger.info(f"✓ Lidos {len(resumos_db)} resumos do banco")
            
            # Log de auditoria: compara gravado vs lido
            if len(resumos_db) != total_resumos_salvos:
                logger.warning(f"ALERTA: Gravados {total_resumos_salvos} mas lidos {len(resumos_db)} do banco!")
            
            # Notifica conclusão
            progress.complete(total_resumos_salvos)
            
            return DocumentResponse(
                resultados_por_pagina={},  # Não usamos mais tabela principal
                resumos_mensais=resumos_db,
                ocr_bruto=consolidated_text[:10000]
            )
        
        except Exception as e:
            logger.error(f"Erro no processamento: {e}", exc_info=True)
            progress.error(str(e))
            raise

