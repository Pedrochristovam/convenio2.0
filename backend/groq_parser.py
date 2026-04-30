"""
Parser usando Groq (Llama 3.1) para extração flexível
100% GRÁTIS, muito rápido, sem complicação
"""

import os
import logging
import json
from typing import Dict, Optional
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class GroqParser:
    """
    Parser usando Groq (Llama 3.1 70B) para extração de resumos e conta corrente
    
    Vantagens:
    - 100% GRÁTIS (sem limites por enquanto)
    - MUITO rápido (mais que OpenAI)
    - Funciona com QUALQUER layout
    - Zero configuração (só precisa de API key)
    """
    
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        
        if not api_key:
            raise ValueError("GROQ_API_KEY não configurada no .env")
        
        self.client = Groq(api_key=api_key)
        
        logger.info("Groq Parser inicializado (100% GRÁTIS, ultra-rápido)")
    
    def parse_resumo(self, page_text: str, page_num: int) -> Optional[Dict]:
        """
        Extrai os 8 campos do resumo mensal.
        O Groq é muito bom em filtrar ruídos, então enviamos um bloco generoso.
        """
        try:
            import re
            
            # 1) Normalização para evitar erros de encoding no OCR (MÃŠS -> MES)
            page_upper = page_text.upper().replace('ÃŠ', 'E').replace('Ã', 'A')
            
            # Requisito relaxado: Basta ter algo que lembre extrato para tentarmos
            # (A chamada externa ja faz uma pre-selecao)
            is_potential = any(k in page_upper for k in ["RESUMO", "SALDO", "DOCUMENTO", "EXTRATO"])
            
            if not is_potential:
                logger.debug(f"Página {page_num} (Groq): Nenhum indício de extrato. Ignorando.")
                return None

            # 2) Isola o bloco começando pelo título ou SALDO ANTERIOR
            # Mas NÃO corta no final agressivamente, deixa Groq filtrar.
            match_inicio = re.search(r"Resumo\s+do\s+m[eêé]s|SALDO\s+ANTERIOR", page_text, re.IGNORECASE)
            
            if match_inicio:
                bloco_resumo = page_text[match_inicio.start():match_inicio.start() + 2500]
            else:
                bloco_resumo = page_text
            
            if len(bloco_resumo.strip()) < 50:
                return None

            logger.info(f"Página {page_num}: Enviando bloco de {len(bloco_resumo)} caracteres para Groq...")

            texto_relevante = bloco_resumo[:5000] # Aumentado para 5000
            
            prompt = self._build_prompt(texto_relevante)
            
            logger.info(f"Página {page_num}: Enviando para Groq (Llama 3.3 70B)...")
            
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "Você é um extrator de dados financeiros especialista em extratos do Banco do Brasil. Retorne APENAS JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                response_format={"type": "json_object"}
            )
            
            response_text = response.choices[0].message.content.strip()
            campos = json.loads(response_text)
            
            return {
                "tipo": "RESUMO_MENSAL",
                "pagina": page_num,
                "campos": campos
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Página {page_num}: Erro ao parsear JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Página {page_num}: Erro no Groq: {e}")
            return None

    def parse_conta_corrente(self, page_text: str, page_num: int) -> Optional[Dict]:
        """
        Extrai transações da conta corrente usando Groq.
        """
        try:
            # Filtro básico
            indicios = ["LANÇAMENTOS", "DATA", "HISTÓRICO", "VALOR", "SALDO"]
            upper_text = page_text.upper()
            if not any(word in upper_text for word in indicios):
                return None

            logger.info(f"Página {page_num}: Enviando CC para Groq...")
            
            prompt = self._build_cc_prompt(page_text[:6000])
            
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "Você é um extrator de dados bancários especialista em Banco do Brasil. Retorne APENAS um objeto JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                response_format={"type": "json_object"}
            )
            
            response_text = response.choices[0].message.content.strip()
            data = json.loads(response_text)
            
            # Normalização simples do header
            header = data.get("header", {})
            transacoes = data.get("transacoes", [])
            
            # Converte valores numéricos se necessário
            for tx in transacoes:
                if isinstance(tx.get("valor"), str):
                    try: tx["valor"] = float(tx["valor"].replace(',', '.'))
                    except: tx["valor"] = 0
                if isinstance(tx.get("saldo"), str):
                    try: tx["saldo"] = float(tx["saldo"].replace(',', '.'))
                    except: tx["saldo"] = 0

            return {
                "tipo": "CONTA_CORRENTE",
                "pagina": page_num,
                "header": header,
                "transacoes": transacoes
            }
            
        except Exception as e:
            logger.error(f"Página {page_num}: Erro no Groq CC: {e}")
            return None
    
    def _build_prompt(self, texto_ocr: str) -> str:
        """
        Constrói o prompt para o Groq com regras para layouts Banco do Brasil
        """
        return f"""Você é um extrator de dados de alta precisão.
Extraia os 8 valores numéricos da tabela "Resumo do mês" deste extrato bancário.

TEXTO OCR:
---
{texto_ocr}
---

INSTRUÇÕES OBRIGATÓRIAS:
1. Identifique a tabela que contém explicitamente os labels: "Saldo Anterior", "Aplicações", "Resgates", "Rendimento Bruto", "Rendimento Líquido" e "Saldo Atual".
2. SE VOCÊ NÃO ENCONTRAR essa tabela específica, retorne todos os campos como 0.0 (ZERO). Não tente adivinhar valores de outras tabelas ou textos soltos.
3. CONFERÊNCIA MATEMÁTICA: Você DEVE validar que:
   Saldo Anterior + Aplicações - Resgates + Rendimento Líquido = Saldo Atual.
4. ATENÇÃO AOS SINAIS: Rendimento pode ser negativo. Resgates são valores subtraídos.
5. Retorne APENAS o JSON puro.

JSON esperado:
{{
  "saldo_anterior": float,
  "aplicacoes": float,
  "resgates": float,
  "rendimento_bruto": float,
  "imposto_renda": float,
  "iof": float,
  "rendimento_liquido": float,
  "saldo_atual": float
}}"""

    def _build_cc_prompt(self, texto_ocr: str) -> str:
        return f"""Extraia todas as transações da tabela 'Lançamentos' deste extrato do Banco do Brasil.
        
TEXTO OCR:
{texto_ocr}

REGRAS:
1. Retorne um JSON com "header" (agencia, conta, titular, periodo) e "transacoes" (lista).
2. Para cada transação, extraia:
   - data_balancete (DD/MM/AAAA)
   - data_movimento (DD/MM/AAAA)
   - historico (texto da descrição)
   - valor (número positivo, use ponto para decimal)
   - valor_tipo ("C" para crédito, "D" para débito)
   - saldo (número do saldo após a transação)
   - saldo_tipo ("C" ou "D")
3. O OCR pode estar fragmentado. Reconstrua as linhas unindo fragmentos próximos.
4. Se o valor estiver com "C" ou "D" ao lado, use isso para valor_tipo.

Exemplo de saída:
{{
  "header": {{"agencia": "1234", "conta": "5678-9", "titular": "JOAO SILVA", "periodo": "01/2024"}},
  "transacoes": [
    {{"data_balancete": "01/01/2024", "data_movimento": "02/01/2024", "historico": "DOC RECEBIDO", "valor": 100.0, "valor_tipo": "C", "saldo": 1000.0, "saldo_tipo": "C"}}
  ]
}}"""
