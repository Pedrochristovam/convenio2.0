import re
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

class CaixaSummaryParser:
    """
    Parser para Extratos de Fundo de Investimento da CAIXA ECONÔMICA FEDERAL.
    
    Utiliza a estratégia "Global Math Window" para localizar a sequência exata de valores.
    Fórmula da CAIXA:
    Saldo Anterior + Aplicações - Resgates + Rendimento Bruto - IRRF - IOF - Taxa de Saída = Saldo Bruto
    """
    
    def __init__(self):
        # Campos exatos lidos do extrato da Caixa na ordem correta
        self.campos_caixa = [
            "saldo_anterior", 
            "aplicacoes", 
            "resgates", 
            "rendimento_bruto", 
            "imposto_renda", # IRRF
            "iof", 
            "taxa_saida", 
            "saldo_bruto"    # Funciona como saldo atual
        ]
        
        # Regex para valores monetários da Caixa, que frequentemente têm 'C' ou 'D' no final
        # Exemplo: 141.001,26D ou 128.392,09C ou apenas 0,00
        # IMPORTANTE: Toleramos a ausência do C/D, mas se houver, nós o capturamos para limpar depois
        self.valor_pattern = re.compile(
            r'(\d{1,3}(?:[ \t\.]+\d{3})*,\d{2})[CDcd]?(?!\d)|'
            r'(\d{1,3}(?:[ \t\.]+\d{3})*[ \t\.]\d{2})[CDcd]?(?!\d)'
        )

    def clean_value(self, value_str: str) -> Optional[float]:
        if not value_str: return None
        try:
            # Remove Letras C e D (Crédito/Débito)
            val = re.sub(r'[CDcd]$', '', value_str.strip())
            
            # Formatação numérica padrão
            val = val.replace('.', '').replace(' ', '')
            if ',' in val:
                val = val.replace(',', '.')
            else:
                if len(val) >= 3:
                    val = val[:-2] + "." + val[-2:]
            return float(val)
        except:
            return None

    def is_math_valid(self, vals: Dict[str, float]) -> tuple[bool, str]:
        """
        Verifica a equação da CAIXA:
        SA + APL - RES + REND_BRUTO - IRRF - IOF - TAXA = SALDO_BRUTO
        """
        try:
            # Requisito: Não pode ser tudo zero
            if all(v < 0.01 for v in vals.values()):
                return False, "Tudo zero"

            calc_total = (vals["saldo_anterior"] 
                          + vals["aplicacoes"] 
                          - vals["resgates"] 
                          + vals["rendimento_bruto"] 
                          - vals["imposto_renda"] 
                          - vals["iof"] 
                          - vals["taxa_saida"])
            
            diff_total = abs(calc_total - vals["saldo_bruto"])
            
            debug_info = f"CalcTotal: {calc_total:.2f} vs SaldoBruto: {vals['saldo_bruto']:.2f} (Diff: {diff_total:.2f})"
            
            # Margem de 0.10 centavos para eventuais arredondamentos muito discretos
            is_valid = diff_total <= 0.10
            return is_valid, debug_info
        except Exception as e:
            return False, f"Erro no cálculo: {e}"

    def parse_govconta_summary(self, page_text: str, page_num: int) -> Optional[Dict[str, Any]]:
        """
        Extração específica para o modelo 'GovConta :: Informativo Mensal' da Caixa.
        Como o OCR separa a coluna de rótulos da coluna de números, 
        usamos uma janela deslizante de 6 valores para o bloco central (Aplicações, Resgates, Bruto, IR, IOF, Líquido)
        e buscamos os saldos de forma independente.
        """
        page_upper = page_text.upper()
        
        # 1. VERIFICAÇÃO DE CONTEXTO ESPECÍFICO
        is_govconta = "GOVCONTA" in page_upper or "INFORMATIVO MENSUAL" in page_upper or "INFORMATIVO MENSAL" in page_upper
        if not is_govconta:
            return None

        logger.info(f"CAIXA Página {page_num}: Detectado layout especializado GovConta.")

        # 2. LIMPEZA E EXTRAÇÃO DE NÚMEROS
        clean_text = page_text.replace('|', ' ').replace(']', ' ').replace('[', ' ')
        all_vals = []
        for m in self.valor_pattern.finditer(clean_text):
            val_str = m.group(0)
            val = self.clean_value(val_str)
            if val is not None:
                if 2010 <= val <= 2030 and "," not in val_str:
                    continue
                all_vals.append({"val": val, "pos": m.start(), "raw": val_str})

        if len(all_vals) < 6:
            return None

        # 3. BUSCA O BLOCO DOS 6 ELEMENTOS DE RESUMO
        # Sabemos que a ordem é: Aplicaçães, Resgates, Bruto, IR, IOF, Liquido
        best_candidate = None
        
        for i in range(len(all_vals) - 5):
            w = all_vals[i:i+6]
            
            # Não podem estar super espalhados
            if w[-1]["pos"] - w[0]["pos"] > 1500:
                continue
                
            aplicacoes = w[0]["val"]
            resgates = w[1]["val"]
            bruto = w[2]["val"]
            ir = w[3]["val"]
            iof = w[4]["val"]
            liquido = w[5]["val"]

            # Evitar falsos positivos com todos zerados
            if abs(aplicacoes) < 0.01 and abs(resgates) < 0.01 and abs(bruto) < 0.01 and abs(liquido) < 0.01:
                continue

            # VALIDAÇÃO CRÍTICA DO BLOCO: RL = Bruto - IR - IOF
            calc_rl = bruto - ir - iof
            if abs(calc_rl - liquido) < 0.10:
                logger.info(f"CAIXA Pagina {page_num}: Encontrado bloco de 6 valores matematicos validos.")
                best_candidate = {
                    "aplicacoes": aplicacoes,
                    "resgates": resgates,
                    "rendimento_bruto": bruto,
                    "imposto_renda": ir,
                    "iof": iof,
                    "rendimento_liquido": liquido
                }
                break
                
        if not best_candidate:
            return None

        # 4. CAPTURAS INDEPENDENTES PARA OS SALDOS
        # Como o OCR separa números, usamos Matemática Dedutiva para encontrar os Saldos!
        # Saldo Anterior + Aplicações - Resgates + Rendimento Líquido == Saldo Atual
        saldo_anterior = 0.0
        saldo_atual = 0.0
        
        fluxo_liquido = best_candidate["aplicacoes"] - best_candidate["resgates"] + best_candidate["rendimento_liquido"]
        
        # Se fluxo for zero, tentamos pegar o maior número da tela (provável saldo repetido)
        # Se não for zero, a equação SA + Fluxo = ST será quase única!
        saldos_found = False
        sa_candidates = [val["val"] for val in all_vals]
        st_candidates = sa_candidates
        
        # Filtramos para não fazer loop O(N^2) gigantesco desnecessariamente
        sa_candidates = list(set(sa_candidates)) 
        st_candidates = list(set(st_candidates))

        for sa in sa_candidates:
            calc_st = sa + fluxo_liquido
            # Verifica se algum ST candidato bate com a conta
            for st in st_candidates:
                if abs(calc_st - st) < 0.10:
                    # Garantia contra falsos positivos de "Tudo Zero" quando existe saldo real
                    # Preferimos pegar valores não-zerados se houver empate
                    if not saldos_found or (sa > saldo_anterior):
                        saldo_anterior = sa
                        saldo_atual = st
                        saldos_found = True
                        logger.info(f"CAIXA Pagina {page_num}: Saldos encontrados por deducao: SA={sa:.2f}, ST={st:.2f}")

        # Se a matemática dedutiva não achou (ex: OCR comeu um dígito do Saldo), 
        # tentamos o fallback por Regex apenas para nnao ir zerado
        if not saldos_found:
            sa_match = re.search(r"SALDO\s+ANTERIOR[\sA-Z-]+([\d\.\s]+,\d{2})", page_upper, re.MULTILINE)
            if sa_match:
                saldo_anterior = self.clean_value(sa_match.group(1)) or 0.0
    
            st_match = re.search(r"SALDO\s+FINAL[\sA-Z-]+([\d\.\s]+,\d{2})", page_upper, re.MULTILINE)
            if st_match:
                saldo_atual = self.clean_value(st_match.group(1)) or 0.0

        best_candidate["saldo_anterior"] = saldo_anterior
        best_candidate["saldo_atual"] = saldo_atual

        return {
            "tipo": "RESUMO_MENSAL",
            "pagina": page_num,
            "campos": best_candidate,
            "math_error": False,
            "math_debug": "Blocos matematicos validados c/ sucesso."
        }

    def parse_resumo(self, page_text: str, page_num: int) -> Optional[Dict[str, Any]]:
        # TENTA PRIMEIRO O MODELO GOVCONTA (MAIS PRECISO E SOBREVIVE À SEPARAÇÃO DE COLUNAS OCR)
        gov_resumo = self.parse_govconta_summary(page_text, page_num)
        if gov_resumo:
            return gov_resumo

        # FALLBACK PARA JANELA MATEMÁTICA GLOBAL (MODELOS ANTIGOS/GENÉRICOS)
        # 1. Limpeza agressiva
        clean_text = page_text.replace('|', ' ').replace(']', ' ').replace('[', ' ')
        
        # ... continuaçao no original
        all_vals = []
        for m in self.valor_pattern.finditer(clean_text):
            val_str = m.group(0)
            val = self.clean_value(val_str)
            if val is not None:
                if 2010 <= val <= 2030 and "," not in val_str:
                    continue
                all_vals.append({"val": val, "pos": m.start(), "raw": val_str})
        
        if len(all_vals) < 8:
            logger.debug(f"CAIXA Pagina {page_num}: Apenas {len(all_vals)} valores.")
            return None

        # 3. VERIFICAÇÃO DE CONTEXTO: Deve haver palavras-chave da CAIXA na página
        page_upper = page_text.upper()
        
        # Requisito 1: Header do extrato da Caixa
        has_caixa_header = "EXTRATO FUNDO" in page_upper or "INFORMATIVO" in page_upper
        
        # Requisito 2: Combinação de Saldo + Rendimento (evita tabelas genéricas)
        has_bank_context = "SALDO BRUTO" in page_upper and "RENDIMENTO" in page_upper
        
        if not (has_caixa_header or has_bank_context):
            logger.debug(f"CAIXA Página {page_num}: Contexto bancário não identificado. Ignorando.")
            return None

        # 4. Global Math Window (Tamanho 8)
        best_candidate = None
        best_diff = 999999.0

        for i in range(len(all_vals) - 7):
            window = all_vals[i:i+8]
            
            # Verificação de PROXIMIDADE: Os valores devem estar próximos no texto
            distancia = window[-1]["pos"] - window[0]["pos"]
            if distancia > 1500:
                continue

            test_results = {self.campos_caixa[j]: window[j]["val"] for j in range(8)}
            
            math_ok, math_debug = self.is_math_valid(test_results)
            
            if math_ok:
                logger.info(f"CAIXA Pagina {page_num}: GOL! Janela detectada.")
                
                # Formata para o padrão unificado da nossa aplicação
                rendimento_liquido = (test_results["rendimento_bruto"] 
                                      - test_results["imposto_renda"] 
                                      - test_results["iof"] 
                                      - test_results["taxa_saida"])
                
                campos_padronizados = {
                    "saldo_anterior": test_results["saldo_anterior"],
                    "aplicacoes": test_results["aplicacoes"],
                    "resgates": test_results["resgates"],
                    "rendimento_bruto": test_results["rendimento_bruto"],
                    "imposto_renda": test_results["imposto_renda"],
                    "iof": test_results["iof"] + test_results["taxa_saida"], # Combinamos IOF e Taxa no campo IOF padrao
                    "rendimento_liquido": round(rendimento_liquido, 2),
                    "saldo_atual": test_results["saldo_bruto"]
                }
                
                return {
                    "tipo": "RESUMO_MENSAL", 
                    "pagina": page_num, 
                    "campos": campos_padronizados, 
                    "math_error": False,
                    "math_debug": math_debug
                }
            
            # Guarda o quase-acerto
            try:
                vals = [w["val"] for w in window]
                current_diff = abs((vals[0] + vals[1] - vals[2] + vals[3] - vals[4] - vals[5] - vals[6]) - vals[7])
                if current_diff < best_diff:
                    best_diff = current_diff
                    best_candidate = test_results
            except:
                pass

        if best_candidate and best_diff < 10.0:
            logger.warning(f"CAIXA Pagina {page_num}: Janela quase perfeita (Diff: {best_diff:.2f}).")
            
        return None
