import re
from typing import Optional, List, Dict
from backend.models import ExtractionResult
import logging

logger = logging.getLogger(__name__)


class DeterministicParser:
    def __init__(self):
        # Termos alvo
        self.target_terms = ["SALDO ANTERIOR", "SALDO ATUAL", "RESGATE"]
        
        # Termos para EXCLUIR
        self.ignore_terms = [
            "COTA", "COTAS", "RENTABILIDADE", "PREJ. COMP.", "IMPOSTO", "IOF",
            "RENDIMENTO LIQUIDO", "RENDIMENTO BRUTO", "VALOR DA COTA", "APLICACOES"
        ]
        
        # Regex para data e valor
        self.date_re = re.compile(r"(\d{2}/\d{2}/\d{4})")
        # Aceita valores com ponto OU espaço como separador de milhares
        self.value_re = re.compile(r"(\d{1,3}(?:[\.\s]\d{3})*,\d{2})")

    def clean_value(self, value_str: str) -> float:
        """Converte string de valor para float, aceitando espaço ou ponto"""
        try:
            # Remove espaços e pontos, substitui vírgula por ponto
            cleaned = value_str.replace(" ", "").replace(".", "").replace(",", ".")
            return float(cleaned)
        except ValueError:
            return 0.0

    def parse_pages(self, pages: List[str]) -> Dict[int, List[ExtractionResult]]:
        paged_results = {}
        
        for p_idx, text in enumerate(pages):
            page_num = p_idx + 1
            results = []
            lines = text.split('\n')
            total_lines = len(lines)
            
            logger.info(f"Processando pagina {page_num} com {total_lines} linhas")
            
            # Detecta se está em "Resumo do Mês"
            resumo_lines = set()
            for i, line in enumerate(lines):
                if "RESUMO" in line.upper():
                    # Marca as próximas 15 linhas como resumo
                    for j in range(i, min(i + 15, total_lines)):
                        resumo_lines.add(j)
            
            # Processa cada linha
            for i, line in enumerate(lines):
                line_upper = line.upper().strip()
                
                # Ignora linhas com termos proibidos
                if any(ignored in line_upper for ignored in self.ignore_terms):
                    continue
                
                # Procura termos alvo
                term_found = None
                for term in self.target_terms:
                    if term in line_upper:
                        term_found = term
                        break
                
                if not term_found:
                    continue
                
                # Se está no resumo, pula (evita duplicatas)
                if i in resumo_lines:
                    logger.debug(f"Pulando linha {i} (resumo): {line[:50]}")
                    continue
                
                logger.info(f"Termo '{term_found}' encontrado na linha {i}: {line[:80]}")
                
                # BUSCA DATA (raio: -15 a +5 linhas)
                found_date = None
                # Tenta na própria linha
                dt_match = self.date_re.search(line)
                if dt_match:
                    found_date = dt_match.group(1)
                else:
                    # Busca para trás (até 15 linhas)
                    for j in range(i - 1, max(-1, i - 16), -1):
                        dt_match = self.date_re.search(lines[j])
                        if dt_match:
                            found_date = dt_match.group(1)
                            break
                    # Busca para frente (até 5 linhas)
                    if not found_date:
                        for j in range(i + 1, min(total_lines, i + 6)):
                            dt_match = self.date_re.search(lines[j])
                            if dt_match:
                                found_date = dt_match.group(1)
                                break
                
                if not found_date:
                    logger.warning(f"Data nao encontrada para '{term_found}' na linha {i}")
                    continue
                
                logger.info(f"Data encontrada: {found_date}")
                
                # BUSCA VALOR (raio: 0 a +10 linhas)
                found_value = None
                # Tenta na própria linha
                val_match = self.value_re.search(line)
                if val_match:
                    found_value = val_match.group(1)
                else:
                    # Busca para frente (até 10 linhas)
                    for k in range(i + 1, min(total_lines, i + 11)):
                        # Ignora linhas com termos proibidos
                        if any(ignored in lines[k].upper() for ignored in self.ignore_terms):
                            continue
                        
                        val_match = self.value_re.search(lines[k])
                        if val_match:
                            found_value = val_match.group(1)
                            break
                
                if not found_value:
                    logger.warning(f"Valor nao encontrado para '{term_found}' com data {found_date}")
                    continue
                
                val_float = self.clean_value(found_value)
                logger.info(f"Valor encontrado: {found_value} -> {val_float}")
                
                # Filtro Zero (apenas para Resgate)
                if term_found == "RESGATE" and val_float == 0.0:
                    logger.info(f"Resgate com valor zero ignorado")
                    continue
                
                # DEDUPLICACAO
                is_dupe = False
                for r in results:
                    if r.campo == term_found and r.data_extracao == found_date and r.valor == val_float:
                        is_dupe = True
                        break
                
                if is_dupe:
                    logger.debug(f"Duplicata ignorada: {term_found} {found_date} {val_float}")
                    continue
                
                results.append(ExtractionResult(
                    campo=term_found,
                    valor=val_float,
                    data_extracao=found_date,
                    pagina=page_num,
                    linha_ocr=line[:100],
                    confianca="ALTA",
                    status="SUCESSO"
                ))
            
            if results:
                paged_results[page_num] = results
                logger.info(f"Pagina {page_num}: {len(results)} resultados extraidos")
            else:
                logger.warning(f"Pagina {page_num}: Nenhum resultado extraido")
        
        logger.info(f"Parser concluido: {len(paged_results)} paginas com dados")
        return paged_results
