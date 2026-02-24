"""
Parser usando Google Gemini para extração flexível
Funciona com QUALQUER layout de documento
"""

import os
import logging
import json
from typing import Dict, Optional
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class GeminiResumoParser:
    """
    Parser usando Gemini 1.5 Flash para extração de resumos mensais
    
    Vantagens:
    - Funciona com QUALQUER layout (1 coluna, 2 colunas, valores ao lado, valores abaixo)
    - Entende contexto semântico
    - Lida com OCR imperfeito
    - 1500 requisições/dia GRÁTIS
    """
    
    def __init__(self):
        api_key = os.getenv("GOOGLE_VISION_API_KEY")  # Usa a mesma key do Vision
        
        if not api_key:
            raise ValueError("GOOGLE_VISION_API_KEY não configurada")
        
        genai.configure(api_key=api_key)
        
        # Usa Gemini 1.5 Flash (mais rápido e barato)
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        
        logger.info("Gemini Parser inicializado (1500 requisições/dia grátis)")
    
    def parse_resumo(self, page_text: str, page_num: int) -> Optional[Dict]:
        """
        Extrai os 8 campos do resumo usando Gemini
        
        Args:
            page_text: Texto OCR completo da página
            page_num: Número da página (para logs)
            
        Returns:
            Dict com os 8 campos ou None se falhar
        """
        try:
            # Limita o texto para não estourar tokens (pega só primeiros 2000 chars após "RESUMO")
            if "RESUMO" in page_text.upper():
                pos_resumo = page_text.upper().index("RESUMO")
                texto_relevante = page_text[pos_resumo:pos_resumo+2000]
            else:
                texto_relevante = page_text[:2000]
            
            prompt = self._build_prompt(texto_relevante)
            
            logger.info(f"Página {page_num}: Enviando para Gemini...")
            
            # Envia para Gemini
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0,  # ZERO criatividade (determinístico)
                    "top_p": 1,
                    "max_output_tokens": 300,
                }
            )
            
            # Extrai JSON da resposta
            response_text = response.text.strip()
            
            logger.debug(f"Resposta Gemini: {response_text[:200]}")
            
            # Remove markdown se existir
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            # Parse JSON
            campos = json.loads(response_text)
            
            # Valida que tem os 8 campos
            campos_esperados = [
                "saldo_anterior", "aplicacoes", "resgates", "rendimento_bruto",
                "imposto_renda", "iof", "rendimento_liquido", "saldo_atual"
            ]
            
            for campo in campos_esperados:
                if campo not in campos:
                    logger.warning(f"Página {page_num}: Campo '{campo}' faltando na resposta")
                    campos[campo] = None
            
            # Log dos valores extraídos
            campos_encontrados = sum(1 for v in campos.values() if v is not None)
            logger.info(f"✓ Página {page_num}: Gemini extraiu {campos_encontrados}/8 campos com sucesso")
            
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
            logger.error(f"Página {page_num}: Erro no Gemini: {e}")
            return None
    
    def _build_prompt(self, texto_ocr: str) -> str:
        """
        Constrói o prompt para o Gemini
        """
        return f"""Você é um extrator de dados financeiros preciso e determinístico.

TAREFA: Encontre e extraia EXATAMENTE estes 8 valores numéricos do texto OCR abaixo.

Procure por uma seção chamada "Resumo do mês" ou "Resumo do mes" e extraia:

1. **SALDO ANTERIOR** - O saldo inicial do período
2. **APLICAÇÕES (+)** ou **APLICACOES (+)** - Novos investimentos (aceite 0,00)
3. **RESGATES (-)** - Retiradas/saques (aceite 0,00)
4. **RENDIMENTO BRUTO (+)** - Rendimento antes de impostos
5. **IMPOSTO DE RENDA (-)** - IR retido (aceite 0,00)
6. **IOF (-)** - IOF cobrado (aceite 0,00)
7. **RENDIMENTO LÍQUIDO** ou **RENDIMENTO LIQUIDO** - Rendimento após impostos
8. **SALDO ATUAL** ou **SALDO ATUAL =** - O saldo final do período

TEXTO OCR:
---
{texto_ocr}
---

REGRAS CRÍTICAS:
1. Converta valores brasileiros para formato numérico: "60.820,83" → 60820.83
2. Se um campo não existir, retorne null (não invente)
3. Valores 0,00 ou 0.0 são VÁLIDOS (não ignore)
4. Os valores podem estar na mesma linha ou linha abaixo do nome do campo
5. Ignore cabeçalhos, rodapés e outras informações

Retorne APENAS JSON válido (sem explicações):
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
    
    def parse_all_pages(self, pages_texts: list) -> Dict[int, Dict]:
        """
        Processa múltiplas páginas com Gemini
        
        Args:
            pages_texts: Lista de textos OCR por página
            
        Returns:
            Dict[page_num, resumo_data]
        """
        resumos = {}
        
        for idx, page_text in enumerate(pages_texts):
            page_num = idx + 1
            
            # Verifica se tem "Resumo do mês"
            if "RESUMO" not in page_text.upper() or ("MÊS" not in page_text.upper() and "MES" not in page_text.upper()):
                continue
            
            # Extrai o bloco de resumo
            bloco = self._extract_resumo_block(page_text)
            if not bloco:
                continue
            
            # Envia para Gemini
            resumo = self.parse_resumo(bloco, page_num)
            
            if resumo:
                resumos[page_num] = resumo
        
        logger.info(f"Gemini processou {len(resumos)} resumos mensais")
        return resumos
    
    def _extract_resumo_block(self, page_text: str) -> Optional[str]:
        """
        Extrai o bloco de texto da seção "Resumo do mês"
        """
        import re
        
        match_inicio = re.search(r"RESUMO\s+DO\s+M[EÊ]S", page_text, re.IGNORECASE)
        if not match_inicio:
            return None
        
        texto_pos_resumo = page_text[match_inicio.start():]
        
        # Encontra o fim da seção
        fim_patterns = [
            r"\n\s*Valor\s+da\s+Cota",
            r"\n\s*Rentabilidade",
            r"\n\s*Data\s+Hist[oó]rico",
            r"\n\s*Transação\s+efetuada"
        ]
        
        fim_pos = len(texto_pos_resumo)
        for pattern in fim_patterns:
            match_fim = re.search(pattern, texto_pos_resumo, re.IGNORECASE)
            if match_fim and match_fim.start() > 100:
                fim_pos = min(fim_pos, match_fim.start())
        
        bloco = texto_pos_resumo[:fim_pos]
        
        # Retorna apenas se tiver pelo menos 200 caracteres (evita blocos incompletos)
        if len(bloco) < 200:
            return None
        
        return bloco
