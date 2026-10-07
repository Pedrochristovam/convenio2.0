import re
from typing import Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


class MonthlySummaryParser:
    """
    Parser ULTRA-SIMPLES para "Resumo do mês"
    
    ESTRATÉGIA: Lê linha por linha NA ORDEM EXATA do documento
    Sem regex complicado, sem busca em múltiplas linhas
    """
    
    def __init__(self):
        self.campos_ordem = [
            "saldo_anterior", "aplicacoes", "resgates", 
            "rendimento_bruto", "imposto_renda", "iof", 
            "rendimento_liquido", "saldo_atual"
        ]
        # Regex para valores monetários (2 ou 3 casas decimais devido a ruído OCR)
        # Ex: "157,847" ou "157,84"
        self.valor_pattern = re.compile(
            r'(\d{1,3}(?:[ \t\.]+\d{3})*,\d{2,3})(?!\d)|'
            r'(\d{1,3}(?:[ \t\.]+\d{3})*[ \t\.]\d{2,3})(?!\d)'
        )

    def clean_value(self, value_str: str) -> Optional[float]:
        if not value_str: return None
        try:
            # Especial para BB: as vezes o OCR reconhece "1 354 86" (sem vírgula)
            val = value_str.replace('.', '').replace(' ', '')
            
            # Se tiver vírgula, trata como decimal
            if ',' in val:
                parts = val.split(',')
                # Se tiver 3 dígitos após a vírgula (ruído), remove o último
                if len(parts[1]) > 2:
                    parts[1] = parts[1][:2]
                val = parts[0] + "." + parts[1]
            else:
                # Trata os últimos 2 dígitos como decimais se não houver vírgula
                if len(val) >= 3:
                    # Se tiver 3 dígitos de sobra (ex: 157847), o padrão acima já tentou pegar apenas os úteis.
                    # Mas por segurança, se for muito longo, pegamos os 2 últimos.
                    val = val[:-2] + "." + val[-2:]
            
            return float(val)
        except:
            return None

    @staticmethod
    def normalize_ocr_text(text: str) -> str:
        """Corrige milhares com espaço do Tesseract: '61 760,38' -> '61.760,38'."""
        if not text:
            return ""
        text = re.sub(
            r'(\d{1,3}(?:[ \t]\d{3})+),\s*(\d{2})\b',
            lambda m: m.group(0).replace(' ', '.').replace('\t', '.'),
            text,
        )
        text = re.sub(r',\s+(\d{2})\b', r',\1', text)
        return text

    def parse_resumo_by_labels(self, page_text: str, page_num: int) -> Optional[Dict[str, Any]]:
        """Extrai pelos rótulos do bloco Resumo do mês (mais robusto ao OCR ruidoso)."""
        text = self.normalize_ocr_text(page_text)
        upper = text.upper().replace('ÃŠ', 'E').replace('Ã', 'A')

        # Isola bloco a partir de RESUMO DO / SALDO ANTERIOR do resumo
        start = None
        for pat in [r'RESUMO\s+DO', r'SALDO\s+ANTERIOR']:
            m = re.search(pat, upper)
            if m:
                # Prefer the RESUMO DO start if present
                if 'RESUMO' in pat or start is None:
                    start = m.start()
                    if 'RESUMO' in pat:
                        break
        if start is None:
            return None

        bloco = text[start:start + 1200]
        bloco_u = bloco.upper().replace('ÃŠ', 'E').replace('Ã', 'A')

        label_patterns = [
            ("saldo_anterior", r"SALDO\s+ANTERIOR"),
            ("aplicacoes", r"APLICA\w*"),
            ("resgates", r"RESGATE\w*"),
            ("rendimento_bruto", r"RENDIMENTO\s+BRUTO"),
            ("imposto_renda", r"IMPOSTO\s+(DE\s+)?RENDA|IRRF"),
            ("iof", r"\bIOF\b"),
            ("rendimento_liquido", r"RENDIMENTO\s+L[IÍ]QUIDO"),
            ("saldo_atual", r"SALDO\s+ATUAL"),
        ]

        money_re = re.compile(
            r'(-?\d{1,3}(?:\.\d{3})*,\d{2})|(-?\d+,\d{2})'
        )

        campos: Dict[str, float] = {}
        search_from = 0
        for key, lpat in label_patterns:
            lm = re.search(lpat, bloco_u[search_from:], re.IGNORECASE)
            if not lm:
                continue
            abs_pos = search_from + lm.end()
            # valor na mesma região (até ~80 chars após o label)
            window = bloco[abs_pos:abs_pos + 80]
            mm = money_re.search(window)
            if not mm:
                continue
            val = self.clean_value(mm.group(0))
            if val is None:
                continue
            campos[key] = val
            search_from = abs_pos

        if len(campos) < 6:
            return None

        # completa faltantes com 0
        for k in self.campos_ordem:
            campos.setdefault(k, 0.0)

        math_ok, math_debug = self.is_math_valid(campos)
        # Reparo OCR: se a conta não fecha, deriva saldo_anterior pela equação
        # SA + APL - RES + RL = ST  =>  SA = ST - APL + RES - RL
        if not math_ok:
            st = campos.get("saldo_atual") or 0.0
            rl = campos.get("rendimento_liquido") or 0.0
            apl = campos.get("aplicacoes") or 0.0
            res = campos.get("resgates") or 0.0
            if abs(st) > 0.01:
                inferred_sa = round(st - apl + res - rl, 2)
                old_sa = campos.get("saldo_anterior") or 0.0
                if abs(inferred_sa - old_sa) >= 0.5:
                    campos["saldo_anterior"] = inferred_sa
                    math_ok, math_debug = self.is_math_valid(campos)
                    if math_ok:
                        math_debug = f"SA corrigido por equacao OCR ({old_sa} -> {inferred_sa})"
                    else:
                        # ainda aceita near-match
                        calc = inferred_sa + apl - res + rl
                        if abs(calc - st) < 1.0:
                            math_ok = True
                            math_debug = f"Label near-match após correção SA Diff={abs(calc-st):.2f}"

        if not math_ok:
            sa = campos.get("saldo_anterior", 0) or 0
            st = campos.get("saldo_atual", 0) or 0
            rl = campos.get("rendimento_liquido", 0) or 0
            calc = sa + (campos.get("aplicacoes") or 0) - (campos.get("resgates") or 0) + rl
            if abs(calc - st) < 1.0 and abs(sa) > 0.01 and abs(st) > 0.01:
                math_ok = True
                math_debug = f"Label-based near-match Diff={abs(calc-st):.2f}"

        if abs(campos.get("saldo_anterior", 0) or 0) < 0.01 and abs(campos.get("saldo_atual", 0) or 0) < 0.01:
            return None

        logger.info(
            "Pagina %s: extração por rótulos (math_ok=%s)",
            page_num, math_ok,
        )
        return {
            "tipo": "RESUMO_MENSAL",
            "pagina": page_num,
            "campos": {k: campos.get(k, 0.0) for k in self.campos_ordem},
            "math_error": not math_ok,
            "math_debug": math_debug if isinstance(math_debug, str) else str(math_debug),
        }

    def is_math_valid(self, campos: Dict[str, Any]):
        """
        Garante que a conta fecha e que pelo menos um valor é relevante.
        """
        try:
            vals = {k: (campos.get(k) or 0.0) for k in self.campos_ordem}
            
            # Requisito: Não pode ser tudo zero (evita falsos positivos em listas de transação)
            if all(abs(v) < 0.01 for v in vals.values()):
                return False

            # Conferência principal: sa + ap - re + rl = st
            calc_total = vals["saldo_anterior"] + vals["aplicacoes"] - vals["resgates"] + vals["rendimento_liquido"]
            diff_total = abs(calc_total - vals["saldo_atual"])
            
            # Conferência secundária: rl = bruto - ir - iof
            calc_rl = vals["rendimento_bruto"] - vals["imposto_renda"] - vals["iof"]
            diff_rl = abs(calc_rl - vals["rendimento_liquido"])
            
            debug_info = f"CalcTotal: {calc_total:.2f} vs ST: {vals['saldo_atual']:.2f} (Diff: {diff_total:.2f}) | CalcRL: {calc_rl:.2f} vs RL: {vals['rendimento_liquido']:.2f} (Diff: {diff_rl:.2f})"
            
            # Permitimos margem de 0.10
            is_valid = diff_total < 0.10 and diff_rl < 0.10
            return is_valid, debug_info
        except:
            return False, "Erro no cálculo"

    def parse_resumo(self, page_text: str, page_num: int) -> Optional[Dict[str, Any]]:
        """
        Extrai o resumo mensal buscando qualquer sequência de 8 números que feche a conta.
        Ignora labels corrompidas e foca na verificação matemática.
        """
        page_text = self.normalize_ocr_text(page_text)

        # 0) Tentativa por rótulos (melhor com OCR Tesseract)
        by_labels = self.parse_resumo_by_labels(page_text, page_num)
        if by_labels and not by_labels.get("math_error"):
            return by_labels

        # 1. Limpeza agressiva de OCR (Remove caracteres que quebram números)
        # Mantém apenas números, vírgulas, pontos e espaços
        clean_text = page_text.replace('|', ' ').replace(']', ' ').replace('[', ' ')
        
        # 2. Extrai TODOS os valores monetários da página
        all_vals = []
        for m in self.valor_pattern.finditer(clean_text):
            val_str = m.group(0)
            val = self.clean_value(val_str)
            if val is not None:
                # Filtra anos (2010-2030) se não tiverem vírgula
                if 2010 <= val <= 2030 and "," not in val_str:
                    continue
                all_vals.append({"val": val, "pos": m.start(), "raw": val_str})
        
        if len(all_vals) < 8:
            logger.debug(f"Pagina {page_num}: Apenas {len(all_vals)} valores encontrados. Ignorando.")
            return by_labels  # pode ter math_error mas ainda útil para Groq fallback path

        # 3. VERIFICAÇÃO DE CONTEXTO: Deve haver palavras-chave de extrato na página
        # Normalização básica para evitar erros de encoding no OCR (MÃŠS -> MES)
        page_upper = page_text.upper().replace('ÃŠ', 'E').replace('Ã', 'A')
        
        # Requisito 1: "RESUMO DO MÊS" (OU "RESUMO DO")
        has_resumo_header = "RESUMO DO" in page_upper
        
        # Requisito 2: Combinação de Saldo + Rendimento (Partial match para "SALDO ANTERIO")
        has_bank_context = ("SALDO ANTERIO" in page_upper) and (("RENDIMENTO" in page_upper) or ("RESUMO" in page_upper))
        
        if not (has_resumo_header or has_bank_context):
            logger.debug(f"Página {page_num}: Contexto bancário não identificado. Ignorando.")
            return by_labels

        # 4. ESTRATÉGIA: Sliding Window Global
        # Testa TODAS as sequências de 8 números na página
        best_candidate = None
        best_diff = 999999.0

        for i in range(len(all_vals) - 7):
            window = all_vals[i:i+8]
            
            # Verificação de PROXIMIDADE: Os valores devem estar próximos no texto
            # Se a distância entre o primeiro e o último for muito grande, é provavelmente erro.
            distancia = window[-1]["pos"] - window[0]["pos"]
            if distancia > 1500: # 1500 caracteres é uma distância segura para uma tabela
                continue

            test_results = {self.campos_ordem[j]: window[j]["val"] for j in range(8)}
            
            math_ok, math_debug = self.is_math_valid(test_results)
            
            # Se bater perfeito, retornamos imediatamente (GOL!)
            if math_ok:
                logger.info(f"Pagina {page_num}: GOL! Janela Matemática Global encontrada (indices {i}-{i+7}, dist: {distancia}).")
                return {
                    "tipo": "RESUMO_MENSAL", 
                    "pagina": page_num, 
                    "campos": test_results, 
                    "math_error": False,
                    "math_debug": math_debug
                }
            
            # Guarda o "quase-acerto" para logs se nada for encontrado
            try:
                vals = [window[j]["val"] for j in range(8)]
                current_diff = abs((vals[0] + vals[1] - vals[2] + vals[6]) - vals[7])
                if current_diff < best_diff:
                    best_diff = current_diff
                    best_candidate = test_results
            except:
                pass

        # 4. Fallback: Se não achou janela perfeita, procura por proximidade de labels
        # (Legado para segurança, mas a janela global deve resolver 99% dos casos do BB)
        logger.warning(f"Pagina {page_num}: Nenhuma janela matemática perfeita encontrada (Best Diff: {best_diff:.2f}).")
        
        # Se chegamos aqui e o melhor candidato é "quase bom" (erro < 1.00), podemos reportar com erro
        if best_candidate and best_diff < 10.0:
            return {
                "tipo": "RESUMO_MENSAL",
                "pagina": page_num,
                "campos": best_candidate,
                "math_error": True,
                "math_debug": f"Janela imperfeita (Diff: {best_diff:.2f})"
            }

        return by_labels

    def parse_all_pages(self, pages_texts: list) -> Dict[int, Dict[str, Any]]:
        resumos = {}
        for i, text in enumerate(pages_texts):
            res = self.parse_resumo(text, i + 1)
            # Apenas salva se não for tudo zero ou se a matemática bater
            if res and any(v != 0 for v in res["campos"].values()):
                resumos[i + 1] = res
        return resumos
