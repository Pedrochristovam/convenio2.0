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
        # Ordem EXATA dos campos no documento
        self.campos_ordem = [
            "saldo_anterior",
            "aplicacoes",
            "resgates",
            "rendimento_bruto",
            "imposto_renda",
            "iof",
            "rendimento_liquido",
            "saldo_atual"
        ]
        
        # Padrão simples: qualquer número brasileiro (com . ou espaço como separador e , decimal)
        self.valor_pattern = re.compile(r'(\d{1,3}(?:[\.\s]\d{3})*,\d{2})')
    
    def clean_value(self, value_str: str) -> Optional[float]:
        """
        Converte string para float
        
        "169 731,94" → 169731.94
        "105.000,00" → 105000.00
        "0,00" → 0.0
        """
        try:
            cleaned = value_str.strip().replace(" ", "").replace(".", "").replace(",", ".")
            valor = float(cleaned)
            return valor
        except (ValueError, AttributeError):
            logger.warning(f"Nao foi possivel converter valor: '{value_str}'")
            return None
    
    def extract_resumo_section(self, page_text: str) -> Optional[str]:
        """
        Extrai apenas o bloco de texto da seção "Resumo do mês"
        """
        match_inicio = re.search(r"RESUMO\s+DO\s+M[EÊ]S", page_text, re.IGNORECASE)
        if not match_inicio:
            return None
        
        texto_pos_resumo = page_text[match_inicio.start():]
        
        # Encontra o fim da seção
        fim_patterns = [
            r"\n\s*Valor\s+da\s+Cota",  # Linha após "SALDO ATUAL"
            r"\n\s*Rentabilidade",
            r"\n\s*Data\s+Hist[oó]rico",
            r"\n\s*\d{2}/\d{2}/\d{4}\s+[A-Z]"
        ]
        
        fim_pos = len(texto_pos_resumo)
        for pattern in fim_patterns:
            match_fim = re.search(pattern, texto_pos_resumo, re.IGNORECASE)
            if match_fim and match_fim.start() > 100:
                fim_pos = min(fim_pos, match_fim.start())
        
        bloco_resumo = texto_pos_resumo[:fim_pos]
        logger.info(f"Bloco de Resumo extraido ({len(bloco_resumo)} caracteres)")
        return bloco_resumo
    
    def parse_resumo_simples(self, bloco_resumo: str) -> Dict[str, Optional[float]]:
        """
        Parser para LAYOUT DE 2 COLUNAS:
        
        COLUNA ESQUERDA:              COLUNA DIREITA:
        SALDO ANTERIOR                APLICAÇÕES (+)
        60.820,83                     0,00
        
        RESGATES (-)                  RENDIMENTO BRUTO (+)
        0,00                          469,18
        
        IMPOSTO DE RENDA (-)          IOF (-)
        0,00                          0,00
        
        RENDIMENTO LÍQUIDO            SALDO ATUAL =
        469,18                        61.290,01
        
        ESTRATÉGIA:
        1. Divide o bloco em linhas
        2. Encontra a linha com o TERMO
        3. Pega o valor da PRÓXIMA linha (abaixo), NA MESMA POSIÇÃO horizontal
        """
        
        linhas = bloco_resumo.split('\n')
        
        # Dicionário de termos para buscar
        termos_busca = {
            "saldo_anterior": ["SALDO ANTERIOR"],
            "aplicacoes": ["APLICAÇÕES (+)", "APLICACOES (+)", "APLICAÇÕES", "APLICACOES"],
            "resgates": ["RESGATES (-)"],
            "rendimento_bruto": ["RENDIMENTO BRUTO (+)"],
            "imposto_renda": ["IMPOSTO DE RENDA (-)", "IMPOSTO RENDA (-)"],
            "iof": ["IOF (-)"],
            "rendimento_liquido": ["RENDIMENTO LÍQUIDO", "RENDIMENTO LIQUIDO"],
            "saldo_atual": ["SALDO ATUAL =", "SALDO ATUAL"]
        }
        
        resultado = {}
        
        for campo in self.campos_ordem:
            termos = termos_busca[campo]
            valor_encontrado = None
            
            # Procura o termo nas linhas
            for i, linha in enumerate(linhas):
                linha_upper = linha.upper()
                
                termo_encontrado = None
                posicao_termo = -1
                
                for termo in termos:
                    if termo in linha_upper:
                        termo_encontrado = termo
                        posicao_termo = linha_upper.index(termo)
                        break
                
                if termo_encontrado:
                    logger.debug(f"Campo '{campo}': termo '{termo_encontrado}' encontrado na linha {i}, posição {posicao_termo}")
                    
                    # ESTRATÉGIA: Valor está na PRÓXIMA linha (ou até 3 linhas abaixo)
                    # Na mesma região horizontal (±20 caracteres da posição do termo)
                    
                    for offset in range(1, 4):  # Tenta próximas 3 linhas
                        if i + offset >= len(linhas):
                            break
                        
                        linha_valor = linhas[i + offset]
                        
                        # Busca valores nesta linha
                        valores = self.valor_pattern.findall(linha_valor)
                        
                        if not valores:
                            continue
                        
                        # Se há apenas 1 valor na linha, usa ele
                        if len(valores) == 1:
                            valor_encontrado = self.clean_value(valores[0])
                            logger.info(f"  {campo}: {valor_encontrado} (1 valor na linha {i+offset})")
                            break
                        
                        # Se há múltiplos valores, pega o que está mais próximo horizontalmente do termo
                        melhor_valor = None
                        menor_distancia = float('inf')
                        
                        for valor_str in valores:
                            pos_valor = linha_valor.index(valor_str)
                            distancia = abs(pos_valor - posicao_termo)
                            
                            if distancia < menor_distancia:
                                menor_distancia = distancia
                                melhor_valor = valor_str
                        
                        if melhor_valor and menor_distancia < 50:  # Aceita até 50 caracteres de distância
                            valor_encontrado = self.clean_value(melhor_valor)
                            logger.info(f"  {campo}: {valor_encontrado} (valor mais próximo na linha {i+offset}, distância {menor_distancia})")
                            break
                    
                    if valor_encontrado:
                        break
            
            resultado[campo] = valor_encontrado
            
            if valor_encontrado is None:
                logger.warning(f"  {campo}: NAO ENCONTRADO")
        
        # Log de auditoria
        campos_encontrados = sum(1 for v in resultado.values() if v is not None)
        logger.info(f"Resumo extraído: {campos_encontrados}/8 campos encontrados")
        
        return resultado
    
    def parse_resumo(self, page_text: str, page_num: int) -> Optional[Dict[str, Any]]:
        """
        Extrai campos do "Resumo do mês"
        """
        if not re.search(r"RESUMO\s+DO\s+M[EÊ]S", page_text, re.IGNORECASE):
            return None
        
        bloco_resumo = self.extract_resumo_section(page_text)
        if not bloco_resumo:
            logger.warning(f"Pagina {page_num}: 'Resumo do Mes' detectado mas bloco nao extraido")
            return None
        
        logger.info(f"Pagina {page_num}: Processando Resumo do Mes")
        
        # Parser SIMPLES linha por linha
        campos_extraidos = self.parse_resumo_simples(bloco_resumo)
        
        # Conta quantos campos foram encontrados
        campos_encontrados = sum(1 for v in campos_extraidos.values() if v is not None)
        logger.info(f"Resumo do Mes extraido: {campos_encontrados}/8 campos encontrados")
        
        resultado = {
            "tipo": "RESUMO_MENSAL",
            "pagina": page_num,
            "campos": campos_extraidos
        }
        
        return resultado
    
    def parse_all_pages(self, pages_texts: list) -> Dict[int, Dict[str, Any]]:
        """
        Processa múltiplas páginas e retorna resumos encontrados
        """
        resumos = {}
        paginas_sem_resumo = []
        
        for idx, page_text in enumerate(pages_texts):
            page_num = idx + 1
            
            if not re.search(r"RESUMO\s+DO\s+M[EÊ]S", page_text, re.IGNORECASE):
                paginas_sem_resumo.append(page_num)
                continue
            
            resumo = self.parse_resumo(page_text, page_num)
            
            if resumo:
                resumos[page_num] = resumo
        
        if resumos:
            logger.info("=" * 60)
            logger.info(f"RELATORIO DE RESUMOS MENSAIS:")
            logger.info(f"  Total de paginas processadas: {len(pages_texts)}")
            logger.info(f"  Paginas com resumo mensal: {len(resumos)} {list(resumos.keys())[:10]}{'...' if len(resumos) > 10 else ''}")
            logger.info(f"  Paginas sem resumo mensal: {len(paginas_sem_resumo)}")
            logger.info("=" * 60)
        
        return resumos
