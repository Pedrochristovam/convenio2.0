import re
from typing import Optional, List, Dict, Any
from backend.models import ExtractionResult
import logging

logger = logging.getLogger(__name__)


class DeterministicParser:
    def __init__(self):
        # Filtros de interesse
        self.target_terms = [
            "SALDO ANTERIOR", 
            "SALDO ATUAL", 
            "RESGATE"
        ]
        
        # Termos para EXCLUIR explicitamente
        self.ignore_terms = [
            "COTA", "COTAS", "RENTABILIDADE", "PREJ. COMP.", "IMPOSTO", "IOF", 
            "RENDIMENTO LÍQUIDO", "RENDIMENTO L\u00cdQUIDO", "RENDIMENTO BRUTO",
            "VALOR DA COTA", "APLICA\u00c7\u00d5ES"
        ]
        
        # Regex auxiliares
        self.date_re = re.compile(r"(\d{2}/\d{2}/\d{4})")
        self.value_re = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2})")

    def clean_value(self, value_str: str) -> float:
        try:
            return float(value_str.replace(".", "").replace(" ", "").replace(",", "."))
        except ValueError:
            return 0.0

    def parse_pages(self, pages: List[str]) -> Dict[int, List[ExtractionResult]]:
        paged_results = {}
        
        for p_idx, text in enumerate(pages):
            page_num = p_idx + 1
            results = []
            
            lines = text.split('\n')
            total_lines = len(lines)
            logger.info(f"🔍 Processando página {page_num} com {total_lines} linhas")
            
            # ESTRAT\u00c9GIA DE PASSADA \u00daNICA COM LOOKAHEAD/LOOKBACK INTELIGENTE
            # Objetivo: Encontrar [DATA] + [CAMPO] + [VALOR]
            # Onde Data e Campo est\u00e3o pertos, e Valor est\u00e1 perto do Campo.
            
            for i, line in enumerate(lines):
                line_upper = line.upper().strip()
                
                # 1. Filtro de Exclus\u00e3o
                if any(ignored in line_upper for ignored in self.ignore_terms):
                    continue

                # 2. Identifica Termo (Anterior/Atual/Resgate)
                term_found = None
                for term in self.target_terms:
                    if term in line_upper:
                        term_found = term
                        break
                
                if term_found:
                    logger.info(f"🎯 Termo encontrado na linha {i}: '{term_found}' -> {line[:80]}")
                    # 3. Busca DATA (Raio: -3 a +1 linhas)
                    found_date = None
                    # Tenta na pr\u00f3pria linha
                    dt_match = self.date_re.search(line)
                    if dt_match:
                        found_date = dt_match.group(1)
                    else:
                        # Tenta buscar ATR\u00c1S (Header) ou FRENTE (Invertido)
                        # Busca atr\u00e1s (at\u00e9 3 linhas)
                        for j in range(i - 1, max(-1, i - 4), -1):
                            dt_match = self.date_re.search(lines[j])
                            if dt_match:
                                found_date = dt_match.group(1)
                                break
                        # Se n\u00e3o achou, busca 1 linha a frente (caso raro de quebra)
                        if not found_date and i + 1 < total_lines:
                             dt_match = self.date_re.search(lines[i+1])
                             if dt_match:
                                found_date = dt_match.group(1)

                    # Se n\u00e3o tem Data associada, SKIPA (Evita Resumo do M\u00eas)
                    if not found_date:
                        logger.warning(f"⚠️ Data não encontrada para '{term_found}' na linha {i}")
                        continue
                    
                    logger.info(f"📅 Data encontrada: {found_date}")

                    # 4. Busca VALOR (Raio: 0 a +5 linhas)
                    found_value = None
                    val_match = self.value_re.search(line)
                    if val_match:
                        found_value = val_match.group(1)
                    else:
                        # Varredura para frente
                        for k in range(i + 1, min(total_lines, i + 6)):
                             # Ignora linha se tiver "Cot/Rent" nela
                             if any(ignored in lines[k].upper() for ignored in self.ignore_terms):
                                continue
                             
                             val_match = self.value_re.search(lines[k])
                             if val_match:
                                found_value = val_match.group(1)
                                break
                    
                    if found_value:
                        val_float = self.clean_value(found_value)
                        logger.info(f"💰 Valor encontrado: {found_value} -> {val_float}")
                        
                        # Filtro Zero (apenas para Resgate)
                        if term_found == "RESGATE" and val_float == 0.0:
                            logger.info(f"⏭️ Resgate com valor zero ignorado")
                            continue
                    else:
                        logger.warning(f"⚠️ Valor não encontrado para '{term_found}' com data {found_date}")
                            
                        # DEDUPLICA\u00c7\u00c3O INTELIGENTE
                        # Se j\u00e1 existe este [Campo + Data + Valor] nesta p\u00e1gina, ignora.
                        # Mas PERMITE [Campo + Data + ValorIgual] se for OUTRA linha de data (mas aqui a data \u00e9 a chave)
                        # Se a Data \u00e9 a mesma, e o Campo \u00e9 o mesmo, ent\u00e3o \u00e9 duplicata.
                        is_dupe = False
                        for r in results:
                            if r.campo == term_found and r.data_extracao == found_date and r.valor == val_float:
                                is_dupe = True # J\u00e1 li isso
                                break
                            # E se tivermos duas entradas iguais no extrato? (Ex: 2 resgates mesmo dia valor igual?)
                            # Dif\u00edcil... mas vamos assumir deduplica\u00e7\u00e3o para limpar sujeira OCR.
                        
                        if is_dupe:
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

            # Ordena\u00e7\u00e3o CRONOL\u00d3GICA dentro da p\u00e1gina
            # Converte data DD/MM/YYYY para sort e depois para string de novo?
            # Melhor manter a ordem de leitura do OCR (Top-Down) que j\u00e1 reflete a tabela visual.
            if results:
                paged_results[page_num] = results
                logger.info(f"✅ Página {page_num}: {len(results)} resultados extraídos")
            else:
                logger.warning(f"⚠️ Página {page_num}: Nenhum resultado extraído")
                
        logger.info(f"🏁 Parser concluído: {len(paged_results)} páginas com dados")
        return paged_results
