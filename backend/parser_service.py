import re
from typing import List, Dict
from backend.models import ExtractionResult
import logging

logger = logging.getLogger(__name__)


class DeterministicParser:
    """
    Parser SIMPLES e DIRETO:
    Extrai APENAS valores da TABELA PRINCIPAL (Data + Historico + Valor)
    IGNORA completamente "Resumo do Mes" e calculos
    """
    
    def __init__(self):
        # Termos que queremos extrair
        self.target_terms = ["SALDO ANTERIOR", "SALDO ATUAL", "RESGATE"]
        
        # Regex
        self.date_re = re.compile(r"(\d{2}/\d{2}/\d{4})")
        self.value_re = re.compile(r"(\d{1,3}(?:[\.\s]\d{3})*,\d{2})")

    def clean_value(self, value_str: str) -> float:
        """Converte string para float"""
        try:
            return float(value_str.replace(" ", "").replace(".", "").replace(",", "."))
        except ValueError:
            return 0.0

    def is_resumo_section(self, lines: List[str], line_index: int) -> bool:
        """
        Verifica se a linha esta dentro de uma secao "Resumo do Mes"
        Busca "RESUMO" nas 10 linhas anteriores
        """
        start = max(0, line_index - 10)
        for i in range(start, line_index + 1):
            if "RESUMO" in lines[i].upper():
                return True
        return False

    def parse_pages(self, pages: List[str]) -> Dict[int, List[ExtractionResult]]:
        """
        Extrai dados de todas as paginas
        REGRA: Apenas linhas da TABELA (com data proxima)
        IGNORA: Secoes de "Resumo do Mes"
        
        ROBUSTO: Funciona com documentos que tem:
        - Paginas irrelevantes no inicio (capas, indices)
        - Extratos espalhados ao longo do documento
        - Paginas mistas (com e sem dados financeiros)
        """
        paged_results = {}
        paginas_vazias = []
        paginas_com_dados = []
        
        for p_idx, text in enumerate(pages):
            page_num = p_idx + 1
            results = []
            lines = text.split('\n')
            
            # Detecta se a pagina tem conteudo financeiro minimo
            tem_data = bool(self.date_re.search(text))
            tem_valor = bool(self.value_re.search(text))
            tem_termo = any(term in text.upper() for term in self.target_terms)
            
            if not (tem_data or tem_valor or tem_termo):
                paginas_vazias.append(page_num)
                logger.debug(f"Pagina {page_num}: SEM conteudo financeiro relevante (pulando)")
                continue
            
            logger.info(f"Processando pagina {page_num} ({len(lines)} linhas) - Data:{tem_data} Valor:{tem_valor} Termo:{tem_termo}")
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                line_upper = line_clean.upper()
                
                # Procura termo alvo
                term_found = None
                for term in self.target_terms:
                    if term in line_upper:
                        term_found = term
                        break
                
                if not term_found:
                    continue
                
                # REGRA 1: Se esta em "Resumo do Mes", PULA
                if self.is_resumo_section(lines, i):
                    logger.debug(f"  Pagina {page_num}: {term_found} ignorado (dentro de Resumo do Mes)")
                    continue
                
                # REGRA 2: Deve ter DATA proxima (mesma linha ou ate 3 linhas antes)
                found_date = None
                dt_match = self.date_re.search(line_clean)
                if dt_match:
                    found_date = dt_match.group(1)
                else:
                    for j in range(max(0, i-3), i):
                        dt_match = self.date_re.search(lines[j])
                        if dt_match:
                            found_date = dt_match.group(1)
                            break
                
                if not found_date:
                    logger.debug(f"  Pagina {page_num}: {term_found} sem data proxima (pulando)")
                    continue
                
                # REGRA 3: Deve ter VALOR proximo (mesma linha ou ate 5 linhas depois)
                found_value = None
                val_match = self.value_re.search(line_clean)
                if val_match:
                    found_value = val_match.group(1)
                else:
                    for j in range(i+1, min(len(lines), i+6)):
                        val_match = self.value_re.search(lines[j])
                        if val_match:
                            found_value = val_match.group(1)
                            break
                
                if not found_value:
                    logger.debug(f"  Pagina {page_num}: {term_found} sem valor proximo (pulando)")
                    continue
                
                val_float = self.clean_value(found_value)
                
                # REGRA 4: Ignora valores zerados (nao tem utilidade)
                if val_float == 0.0:
                    logger.debug(f"  Pagina {page_num}: {term_found} com valor zero (pulando)")
                    continue
                
                # REGRA 5: Deduplicacao (mesmo campo + data + valor)
                is_duplicate = any(
                    r.campo == term_found and 
                    r.data_extracao == found_date and 
                    r.valor == val_float 
                    for r in results
                )
                
                if is_duplicate:
                    logger.debug(f"  Pagina {page_num}: {term_found} duplicado (pulando)")
                    continue
                
                # ADICIONA RESULTADO
                logger.info(f"  ✓ Pagina {page_num}: {term_found} = R$ {val_float:,.2f} em {found_date}")
                results.append(ExtractionResult(
                    campo=term_found,
                    valor=val_float,
                    data_extracao=found_date,
                    pagina=page_num,
                    linha_ocr=line_clean[:100],
                    confianca="ALTA",
                    status="SUCESSO"
                ))
            
            if results:
                paged_results[page_num] = results
                paginas_com_dados.append(page_num)
        
        total = sum(len(r) for r in paged_results.values())
        
        # RELATORIO FINAL
        logger.info("=" * 60)
        logger.info(f"RELATORIO DE EXTRACAO:")
        logger.info(f"  Total de paginas processadas: {len(pages)}")
        logger.info(f"  Paginas com dados extraidos: {len(paginas_com_dados)} ({paginas_com_dados[:10]}{'...' if len(paginas_com_dados) > 10 else ''})")
        logger.info(f"  Paginas vazias/irrelevantes: {len(paginas_vazias)} ({paginas_vazias[:10]}{'...' if len(paginas_vazias) > 10 else ''})")
        logger.info(f"  Total de registros extraidos: {total}")
        logger.info("=" * 60)
        
        return paged_results
