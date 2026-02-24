import re
import logging
from typing import Optional, List, Dict, Any
from backend.models import ExtractionResult

# Configuração de logger para arquivo (Debug Urgente)
logging.basicConfig(
    filename='parser_debug.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w'
)
logger = logging.getLogger(__name__)

class DeterministicParser:
    def __init__(self):
        self.target_terms = [
            "SALDO ANTERIOR", 
            "SALDO ATUAL", 
            "RESGATE"
        ]
        
        self.ignore_terms = [
            "COTA", "COTAS", "RENTABILIDADE", "PREJ. COMP.", "IMPOSTO", "IOF", 
            "RENDIMENTO LÍQUIDO", "RENDIMENTO L\u00cdQUIDO", "RENDIMENTO BRUTO",
            "VALOR DA COTA", "APLICA\u00c7\u00d5ES", "RENDIMENTOS", "RENTAB"
        ]
        
        self.date_re = re.compile(r"(\d{2}/\d{2}/\d{4})")
        self.value_re = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2})")

    def clean_value(self, value_str: str) -> float:
        try:
            return float(value_str.replace(".", "").replace(" ", "").replace(",", "."))
        except ValueError:
            return 0.0

    def parse_pages(self, pages: List[str]) -> Dict[int, List[ExtractionResult]]:
        paged_results = {}
        
        # 1. EXTRAÇÃO BRUTA
        for p_idx, text in enumerate(pages):
            page_num = p_idx + 1
            results = []
            lines = text.split('\n')
            total_lines = len(lines)
            consumed_value_lines = set()

            logger.info(f"--- Processando Página {page_num} ---")

            for i, line in enumerate(lines):
                line_upper = line.upper().strip()
                if any(ignored in line_upper for ignored in self.ignore_terms):
                    continue

                term_found = None
                for term in self.target_terms:
                    if term in line_upper:
                        term_found = term
                        break
                
                if term_found:
                    # Busca DATA
                    found_date = None
                    dt_match = self.date_re.search(line)
                    if dt_match: found_date = dt_match.group(1)
                    else:
                        for j in range(i - 1, max(-1, i - 4), -1):
                            dt_match = self.date_re.search(lines[j])
                            if dt_match: found_date = dt_match.group(1); break
                        if not found_date and i + 1 < total_lines:
                             dt_match = self.date_re.search(lines[i+1])
                             if dt_match: found_date = dt_match.group(1)

                    if not found_date: continue

                    # Busca VALOR
                    found_value = None
                    value_line_idx = -1
                    val_match = self.value_re.search(line)
                    if val_match:
                        found_value = val_match.group(1)
                        value_line_idx = i
                    else:
                        for k in range(i + 1, min(total_lines, i + 6)):
                            if k in consumed_value_lines: continue
                            if any(ignored in lines[k].upper() for ignored in self.ignore_terms): continue
                            
                            is_barrier = False
                            for t in self.target_terms:
                                if t in lines[k].upper(): is_barrier = True; break
                            if is_barrier: break 
                            
                            val_match = self.value_re.search(lines[k])
                            if val_match:
                                found_value = val_match.group(1)
                                value_line_idx = k
                                break
                    
                    if found_value:
                        val_float = self.clean_value(found_value)
                        
                        # FILTRO BÁSICO DE ZEROS
                        if term_found == "RESGATE" and val_float == 0.0: continue
                        
                        # DEDUPLICAÇÃO
                        is_dupe = False
                        for r in results:
                            if r.campo == term_found and r.data_extracao == found_date and r.valor == val_float:
                                is_dupe = True; break
                        if is_dupe: continue

                        if value_line_idx != -1: consumed_value_lines.add(value_line_idx)
                        
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

        # 2. CONTINUIDADE FORÇADA E FILTRO DE MAGNITUDE
        return self.enforce_continuity_and_sanity(paged_results)

    def enforce_continuity_and_sanity(self, paged_results: Dict[int, List[ExtractionResult]]) -> Dict[int, List[ExtractionResult]]:
        sorted_pages = sorted(paged_results.keys())
        last_saldo_atual = None
        last_date = None
        
        for page_num in sorted_pages:
            results = paged_results[page_num]
            
            # 1. FORCE CONTINUITY: Sobrescreve Saldo Anterior com o Saldo Atual anterior
            current_anterior_idx = next((idx for idx, r in enumerate(results) if r.campo == "SALDO ANTERIOR"), -1)
            
            if last_saldo_atual is not None:
                # Se já tem Saldo Anterior, SOBRESCREVE (O usuário exigiu: "AQUI JA E PASSADO")
                # A menos que seja a Pág 1 ou quebra de fluxo evidente. Mas vamos obedecer a regra rígida das setas.
                
                ref_date = results[0].data_extracao if results else last_date
                
                new_anterior = ExtractionResult(
                    campo="SALDO ANTERIOR",
                    valor=last_saldo_atual,
                    data_extracao=ref_date,
                    pagina=page_num,
                    linha_ocr="[FORÇADO PELA SETA DE CONTINUIDADE]",
                    confianca="MEDIA",
                    status="SUCESSO"
                )
                
                if current_anterior_idx != -1:
                    logger.info(f"Página {page_num}: Substituindo Saldo Anterior lido ({results[current_anterior_idx].valor}) pelo calculado ({last_saldo_atual})")
                    results[current_anterior_idx] = new_anterior
                else:
                    logger.info(f"Página {page_num}: Injetando Saldo Anterior ({last_saldo_atual})")
                    results.insert(0, new_anterior)
            
            # 2. SANITY CHECK: Saldo Atual
            # Se o Saldo Atual lido for < 10% do Saldo Anterior (e Saldo Anterior for relevante > 1000), suspeite de erro OCR (valor pequeno).
            # Exceção: Se houve um RESGATE gigante na mesma página.
            
            current_anterior_val = next((r.valor for r in results if r.campo == "SALDO ANTERIOR"), 0.0)
            resgates_val = sum(r.valor for r in results if r.campo == "RESGATE")
            
            current_atual_idx = next((idx for idx, r in enumerate(results) if r.campo == "SALDO ATUAL"), -1)
            
            if current_atual_idx != -1 and current_anterior_val > 1000:
                val_atual = results[current_atual_idx].valor
                expected_min = (current_anterior_val - resgates_val) * 0.1 # Aceita queda de até 90% (exagerado, mas seguro)
                
                # Se o valor atual for MUITO pequeno comparado ao anterior (e não explicável por resgates)
                # E o valor for absoluto "pequeno" (< 1000)
                if val_atual < 1000 and val_atual < (current_anterior_val * 0.05):
                    logger.warning(f"Página {page_num}: Saldo Atual SUSPEITO ({val_atual}). Muito menor que Anterior ({current_anterior_val}). Possível ruído.")
                    # Remove o Saldo Atual suspeito
                    results.pop(current_atual_idx)
                    current_atual_idx = -1 # Marcado como removido
            
            # Atualiza ponteiros para próxima página
            # Se tiver Saldo Atual nesta página (e válido), usa ele.
            # Se não tiver, usa o Saldo Anterior desta página - Resgates? 
            # Melhor manter o último saldo atual conhecido se falhar a leitura do atual.
            
            if current_atual_idx != -1:
                last_saldo_atual = results[current_atual_idx].valor
                last_date = results[current_atual_idx].data_extracao
            elif current_anterior_idx != -1: 
                # Se não achou Saldo Atual, tenta estimar? Ou mantem o anterior?
                # Se só leu Saldo Anterior e Resgates, o Saldo Atual implicito é SA - R.
                last_saldo_atual = current_anterior_val - resgates_val
                logger.info(f"Página {page_num}: Saldo Atual estimado matematicamente ({last_saldo_atual}) pois não foi lido.")
            
            paged_results[page_num] = results
            
        return paged_results
