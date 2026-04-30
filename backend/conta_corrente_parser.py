import re
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class ContaCorrenteParser:
    """
    Parser para Extratos de Conta Corrente do Banco do Brasil.
    Extrai o cabeçalho (agência, conta, titular, período) e cada
    linha de lançamento da tabela de movimentações.
    """

    # Padrões de detecção da página de conta corrente
    DETECTION_PATTERNS = [
        r"extrato\s+conta\s+corrente",
        r"lançamentos",
    ]

    # Regex para valores monetários (aceita C/D e sem sufixo). Permite , e . como decimal
    VALOR_RE = re.compile(r'(\d{1,3}(?:[.\s]\d{3})*[.,]\d{2})\s*([CDcd])?', re.IGNORECASE)

    # Regex para datas no formato DD/MM/AAAA ou DD/MM/YY (agora mais flexível com espaços)
    DATA_RE = re.compile(r'\b(\d{2}\s*/\s*\d{2}\s*/\s*\d{2,4})\b')

    def is_conta_corrente_page(self, page_text: str, page_num: int = 0) -> bool:
        """Detecta se a página é um extrato de conta corrente do BB."""
        # Limpeza agressiva para detecção
        import unicodedata
        text_clean = "".join(
            c for c in unicodedata.normalize('NFD', page_text.lower())
            if unicodedata.category(c) != 'Mn'
        )
        
        # Sinais de CC (BB)
        has_extrato = "extrato" in text_clean
        has_conta_corrente = "conta corrente" in text_clean or "c.c" in text_clean or "c corrente" in text_clean
        has_lancamentos = "lancamentos" in text_clean or "dt. balancete" in text_clean or "historico" in text_clean
        has_periodo = "periodo" in text_clean or "agencia" in text_clean or "conta atual" in text_clean
        
        # Sinais que indicam que NÃO é CC (é Investimento)
        is_investimento = "investimento" in text_clean or "fundo" in text_clean or "rentabilidade" in text_clean
        
        # Se tem o título clássico, é CC (mesmo que pareça investimento por ter algum termo de fundo no rodapé)
        if has_extrato and has_conta_corrente:
            logger.info(f"Página {page_num}: ✓ Identificado como CC via Título Direto.")
            return True
            
        # Score-based para casos fragmentados
        score = sum([has_extrato, has_conta_corrente, has_lancamentos, has_periodo])
        logger.info(f"Página {page_num}: CC Score {score} (Invest: {is_investimento})")
        
        if score >= 2 and not is_investimento:
            return True
            
        # Caso especial: BB às vezes coloca "Extrato conta corrente" e logo abaixo os lançamentos
        if has_conta_corrente and has_lancamentos:
             return True

        return False

    def _extract_header(self, page_text: str) -> Dict[str, str]:
        """Extrai agência, conta corrente, titular e período do cabeçalho."""
        header = {
            "agencia": "",
            "conta": "",
            "titular": "",
            "periodo": "",
        }
        lines = page_text.split('\n')
        for line in lines:
            line_s = line.strip()
            # Agência
            m = re.search(r'[Aa]g[êe]ncia[:\s]+(\d+[\-\d]*)', line_s)
            if m:
                header["agencia"] = m.group(1).strip()
            # Conta
            m = re.search(r'[Cc]onta\s+[Cc]orrente[:\s]+([\d\-]+)\s*(.*)', line_s)
            if m:
                header["conta"] = m.group(1).strip()
                possible_name = m.group(2).strip()
                if len(possible_name) > 3:
                    header["titular"] = possible_name
            # Período
            m = re.search(r'(?:per[íi]odo|período)[:\s]*([\d/\s]+)', line_s, re.IGNORECASE)
            if m:
                header["periodo"] = m.group(1).strip()
        return header

    def _parse_transaction_line(self, line: str) -> Optional[Dict[str, Any]]:
        """
        Tenta extrair uma transação de uma linha de texto.
        """
        line = line.strip()
        if len(line) < 8:
            return None

        # Procura datas (limpa espaços extras que o OCR pode inserir: 30 / 12 / 2024 -> 30/12/2024)
        found_dates = self.DATA_RE.findall(line)
        if not found_dates:
            return None
        
        # Normaliza as datas (remove espaços)
        dates = [d.replace(' ', '') for d in found_dates]

        # Procura valores
        values = self.VALOR_RE.findall(line)
        if not values:
            return None

        # Isola histórico: remove tudo que é data ou valor
        hist_text = line
        for d in found_dates: hist_text = hist_text.replace(d, '')
        for v_raw, suffix in values: hist_text = hist_text.replace(v_raw, '')
        
        # Limpeza agressiva do histórico
        hist_text = re.sub(r'[\d.,/|-]{5,}', '', hist_text) # Remove números soltos grandes
        hist_text = re.sub(r'\s{2,}', ' ', hist_text).strip(' |*')

        # Se não restou nada no histórico, provavelmente é linha de cabeçalho ou saldo
        if len(hist_text) < 3 and len(values) < 2:
            return None

        parsed_values = []
        for raw_val, suffix in values:
            try:
                raw_val = raw_val.replace(' ', '')
                if ',' in raw_val:
                    clean = raw_val.replace('.', '').replace(',', '.')
                else:
                    parts = raw_val.rsplit('.', 1)
                    if len(parts) == 2:
                        clean = parts[0].replace('.', '') + '.' + parts[1]
                    else:
                        clean = raw_val
                parsed_values.append({
                    "val": float(clean),
                    "tipo": suffix.upper() if suffix else "C",
                })
            except: pass

        if not parsed_values:
            return None

        # Se tiver 2 ou mais valores, o último costuma ser o saldo
        # Se tiver só 1, assumimos que o OCR falhou no saldo e pegamos só o valor
        valor_data = parsed_values[-2] if len(parsed_values) >= 2 else parsed_values[0]
        saldo_data = parsed_values[-1]

        return {
            "data_balancete": dates[0],
            "data_movimento": dates[1] if len(dates) > 1 else dates[0],
            "historico": hist_text[:120],
            "valor": valor_data["val"],
            "valor_tipo": valor_data["tipo"],
            "saldo": saldo_data["val"],
            "saldo_tipo": saldo_data["tipo"],
            "raw_line": line[:200],
        }

    def parse_conta_corrente(self, page_text: str, page_num: int) -> Optional[Dict[str, Any]]:
        """Analisa o texto de uma página buscando movimentações de conta corrente."""
        logger.info(f"--- CC_PARSER START (Pág {page_num}) ---")
        
        if not self.is_conta_corrente_page(page_text):
            logger.info(f"Pág {page_num}: NÃO IDENTIFICADA como Conta Corrente.")
            return None
        
        logger.info(f"Pág {page_num}: IDENTIFICADA como Conta Corrente. Iniciando extração...")
        
        lines = page_text.split('\n')
        transactions = []
        current_tx = {"dates": [], "values": [], "lines": []}
        in_lancamentos = False

        def _push_current():
            nonlocal current_tx
            if current_tx and (current_tx["dates"] or current_tx["values"]):
                # Validação e Formatação
                hist = " ".join(current_tx["lines"]).strip()
                # Limpa lixo do histórico
                hist = self.DATA_RE.sub('', hist)
                hist = self.VALOR_RE.sub('', hist)
                hist = re.sub(r'(?i)(?:fis|fls|folha|pag|page)\.?\s*[:\d\-]*', '', hist) # Remove FIS., FLS., FOLHA, etc.
                hist = re.sub(r'[\d.,/|-]{5,}', '', hist)
                hist = re.sub(r'\s{2,}', ' ', hist).strip(' |*')

                v_list = current_tx["values"]
                # Penúltimo = Valor, Último = Saldo
                valor = v_list[-2] if len(v_list) >= 2 else (v_list[0] if v_list else {"val": 0, "tipo": "C"})
                saldo = v_list[-1] if v_list else {"val": 0, "tipo": "C"}
                
                dt_mov = current_tx["dates"][1] if len(current_tx["dates"]) > 1 else (current_tx["dates"][0] if current_tx["dates"] else "")
                
                # Extração de Documento (se houver um número isolado de 3-10 dígitos no histórico)
                doc_match = re.search(r'\b(\d{3,10})\b', hist)
                documento = doc_match.group(1) if doc_match else ""
                if documento:
                    hist = hist.replace(documento, '').strip()

                # Limpeza final de ruído bancário comum
                hist = re.sub(r'(?i)\b(agencia|conta|atual|cliente|lote|folha|pag|page)\b\.?.*', '', hist)
                hist = re.sub(r'\s{2,}', ' ', hist).strip(' |*-')

                tx = {
                    "data_balancete": current_tx["dates"][0] if current_tx["dates"] else "",
                    "data_movimento": dt_mov,
                    "historico": hist[:100],
                    "documento": documento,
                    "valor": valor["val"],
                    "valor_tipo": valor["tipo"],
                    "saldo": saldo["val"],
                    "saldo_tipo": saldo["tipo"],
                    "pagina": page_num
                }
                logger.debug(f" -> PUSHING TX: {tx['data_movimento']} | {tx['historico']} | {tx['valor']}")
                transactions.append(tx)
                
            current_tx = {"dates": [], "values": [], "lines": []}

        for line in lines:
            line_s = line.strip()
            if not line_s: continue
            line_lower = line_s.lower()

            # Detecção de Seção
            if "lançamentos" in line_lower or "lancamentos" in line_lower or "dt." in line_lower:
                in_lancamentos = True
                continue
            if "observações" in line_lower or "observacoes" in line_lower or "transação efetuada" in line_lower:
                break

            if not in_lancamentos:
                continue

            # Detecta datas e valores
            found_dates = [d.replace(' ', '') for d in self.DATA_RE.findall(line_s)]
            found_vals = []
            for raw_val, suffix in self.VALOR_RE.findall(line_s):
                try:
                    raw_val = raw_val.replace(' ', '')
                    if ',' in raw_val:
                        clean = raw_val.replace('.', '').replace(',', '.')
                    else:
                        parts = raw_val.rsplit('.', 1)
                        if len(parts) == 2:
                            clean = parts[0].replace('.', '') + '.' + parts[1]
                        else:
                            clean = raw_val
                    found_vals.append({"val": float(clean), "tipo": suffix.upper() if suffix else "C"})
                except: pass

            # Se achamos data, inicia novo bloco
            if found_dates:
                _push_current()
                current_tx["dates"].extend(found_dates)
            
            current_tx["values"].extend(found_vals)
            current_tx["lines"].append(line_s)

        # Finaliza último bloco
        _push_current()

        if not transactions:
            logger.warning(f"Pág {page_num}: Identificada como CC, mas zero transações extraídas.")
            return None
            
        logger.info(f"--- CC_PARSER END: {len(transactions)} transações encontradas ---")
        return {
            "page": page_num,
            "header": self._extract_header(page_text),
            "transacoes": transactions
        }
