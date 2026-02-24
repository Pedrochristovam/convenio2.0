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


class GroqResumoParser:
    """
    Parser usando Groq (Llama 3.1 70B) para extração de resumos mensais
    
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
        Extrai os 8 campos do resumo usando Groq
        
        Args:
            page_text: Texto OCR completo da página
            page_num: Número da página (para logs)
            
        Returns:
            Dict com os 8 campos ou None se falhar
        """
        try:
            # Limita o texto
            if "RESUMO" in page_text.upper():
                pos_resumo = page_text.upper().index("RESUMO")
                texto_relevante = page_text[pos_resumo:pos_resumo+2000]
            else:
                texto_relevante = page_text[:2000]
            
            prompt = self._build_prompt(texto_relevante)
            
            logger.info(f"Página {page_num}: Enviando para Groq (Llama 3.1)...")
            
            # Envia para Groq
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",  # Modelo ATUAL (2026)
                messages=[
                    {
                        "role": "system",
                        "content": "Você é um extrator de dados financeiros preciso. Retorne APENAS JSON válido, sem explicações."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0,  # Zero criatividade (determinístico)
                max_tokens=500,
                response_format={"type": "json_object"}  # Força retorno JSON
            )
            
            # Extrai JSON da resposta
            response_text = response.choices[0].message.content.strip()
            
            logger.debug(f"Resposta Groq: {response_text[:200]}")
            
            # Parse JSON
            campos = json.loads(response_text)
            
            # Valida que tem os 8 campos
            campos_esperados = [
                "saldo_anterior", "aplicacoes", "resgates", "rendimento_bruto",
                "imposto_renda", "iof", "rendimento_liquido", "saldo_atual"
            ]
            
            for campo in campos_esperados:
                if campo not in campos:
                    logger.warning(f"Página {page_num}: Campo '{campo}' faltando, adicionando null")
                    campos[campo] = None
            
            # Log dos valores extraídos
            campos_encontrados = sum(1 for v in campos.values() if v is not None)
            logger.info(f"✓ Página {page_num}: Groq extraiu {campos_encontrados}/8 campos com sucesso")
            
            for campo, valor in campos.items():
                if valor is not None:
                    logger.info(f"  {campo}: {valor}")
            
            return {
                "tipo": "RESUMO_MENSAL",
                "pagina": page_num,
                "campos": campos
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Página {page_num}: Erro ao parsear JSON: {e}")
            logger.error(f"Resposta: {response_text[:500]}")
            return None
        
        except Exception as e:
            logger.error(f"Página {page_num}: Erro no Groq: {e}")
            return None
    
    def _build_prompt(self, texto_ocr: str) -> str:
        """
        Constrói o prompt para o Groq
        """
        return f"""Extraia EXATAMENTE estes 8 valores numéricos do texto OCR de um resumo mensal de investimento.

Procure por uma seção "Resumo do mês" e extraia:

1. SALDO ANTERIOR - O saldo NO INÍCIO do período (primeiro campo)
2. APLICAÇÕES (+) - Novos investimentos (aceite 0,00)
3. RESGATES (-) - Retiradas (aceite 0,00)
4. RENDIMENTO BRUTO (+) - Rendimento antes de impostos
5. IMPOSTO DE RENDA (-) - IR retido (aceite 0,00)
6. IOF (-) - IOF cobrado (aceite 0,00)
7. RENDIMENTO LÍQUIDO - Rendimento após impostos
8. SALDO ATUAL - O saldo NO FINAL do período (último campo, geralmente maior que SALDO ANTERIOR)

TEXTO OCR:
{texto_ocr}

REGRAS CRÍTICAS:
- Converta valores brasileiros: "60.820,83" → 60820.83
- Se não existir, retorne null
- Valores 0,00 são VÁLIDOS
- Os valores podem estar ao lado ou abaixo do nome do campo
- IMPORTANTE: SALDO ANTERIOR é o PRIMEIRO valor, SALDO ATUAL é o ÚLTIMO valor
- SALDO ATUAL geralmente é DIFERENTE de SALDO ANTERIOR (pode ser maior ou menor)
- NÃO repita o mesmo valor em campos diferentes
- Se um campo tem "ANTERIOR" no nome, é o valor DO INÍCIO
- Se um campo tem "ATUAL" no nome, é o valor DO FINAL

Retorne APENAS JSON válido:
{{
  "saldo_anterior": 60820.83,
  "aplicacoes": 0.0,
  "resgates": 0.0,
  "rendimento_bruto": 469.18,
  "imposto_renda": 0.0,
  "iof": 0.0,
  "rendimento_liquido": 469.18,
  "saldo_atual": 61290.01
}}"""
