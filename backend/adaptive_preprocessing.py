"""
Pré-processamento ADAPTATIVO de imagens
Aplica melhorias APENAS quando necessário (baixa qualidade OCR)
"""

import io
import logging
from typing import Tuple, Optional
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np

logger = logging.getLogger(__name__)


class AdaptiveImagePreprocessor:
    """
    Preprocessa imagens APENAS quando o OCR detectar baixa qualidade
    
    Estratégia:
    1. Tenta OCR na imagem original
    2. Se resultado for ruim (pouco texto), aplica melhorias
    3. Retorna a melhor versão
    """
    
    def __init__(self):
        self.min_text_length = 100  # Se OCR retornar menos que isso, tenta melhorar
    
    def should_enhance(self, ocr_text: str) -> bool:
        """
        Decide se a imagem precisa de melhorias baseado no resultado OCR
        
        Critérios:
        - Texto muito curto (< 100 caracteres)
        - Muitos caracteres estranhos
        - Poucos números (em extrato bancário deveria ter muitos)
        """
        if len(ocr_text) < self.min_text_length:
            logger.info(f"OCR retornou apenas {len(ocr_text)} caracteres - Aplicando melhorias")
            return True
        
        # Conta quantos números tem (extrato bancário tem muitos)
        numeros = sum(1 for c in ocr_text if c.isdigit())
        if numeros < 10:
            logger.info(f"Poucos números detectados ({numeros}) - Aplicando melhorias")
            return True
        
        return False
    
    def enhance_image(self, image_bytes: bytes) -> bytes:
        """
        Aplica melhorias na imagem:
        1. Aumenta contraste
        2. Nitidez
        3. Correção de inclinação
        4. Redução de ruído
        """
        try:
            img = Image.open(io.BytesIO(image_bytes))
            
            # Converte para RGB se necessário
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            logger.info(f"Melhorando imagem: {img.size[0]}x{img.size[1]} pixels")
            
            # 1. Aumenta contraste (ajuda com escaneamentos fracos)
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.5)  # 50% mais contraste
            
            # 2. Aumenta nitidez (ajuda com imagens borradas)
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.5)
            
            # 3. Correção de inclinação (deskew)
            try:
                angle = self._detect_skew(img)
                if abs(angle) > 0.5:  # Só corrige se inclinação > 0.5 graus
                    logger.info(f"Corrigindo inclinação: {angle:.2f} graus")
                    img = img.rotate(angle, expand=True, fillcolor='white')
            except Exception as e:
                logger.warning(f"Falha no deskew: {e}")
            
            # 4. Redução de ruído (remove "sujeira" do escaneamento)
            img = img.filter(ImageFilter.MedianFilter(size=3))
            
            # Converte de volta para bytes
            output = io.BytesIO()
            img.save(output, format='PNG', optimize=True)
            output.seek(0)
            
            result = output.read()
            logger.info(f"Imagem melhorada: {len(image_bytes)} -> {len(result)} bytes")
            
            return result
            
        except Exception as e:
            logger.warning(f"Erro ao melhorar imagem, usando original: {e}")
            return image_bytes
    
    def _detect_skew(self, img: Image.Image) -> float:
        """
        Detecta ângulo de inclinação da imagem
        Método simplificado usando análise de bordas
        """
        try:
            # Converte para numpy array
            img_array = np.array(img.convert('L'))  # Escala de cinza
            
            # Calcula gradiente horizontal (detecta linhas de texto)
            sobel_y = np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]])
            
            h, w = img_array.shape
            edges = np.zeros_like(img_array, dtype=float)
            
            # Aplica filtro Sobel (simplificado)
            for i in range(1, h-1):
                for j in range(1, w-1):
                    region = img_array[i-1:i+2, j-1:j+2]
                    edges[i, j] = abs(np.sum(region * sobel_y))
            
            # Pega região central (onde geralmente está o texto)
            center_h = h // 2
            margin = h // 4
            center_region = edges[center_h - margin:center_h + margin, :]
            
            # Soma intensidades por linha
            row_sums = np.sum(center_region, axis=1)
            
            # Se não há bordas suficientes, não há texto detectável
            if np.max(row_sums) < np.mean(row_sums) * 2:
                return 0.0
            
            # Calcula inclinação baseada em linhas dominantes
            # (implementação simplificada - assume inclinação pequena)
            threshold = np.mean(row_sums) + np.std(row_sums)
            text_rows = np.where(row_sums > threshold)[0]
            
            if len(text_rows) < 5:
                return 0.0
            
            # Estima ângulo baseado em espaçamento irregular
            spacings = np.diff(text_rows)
            avg_spacing = np.mean(spacings)
            
            # Se espaçamento muito irregular, provavelmente há inclinação
            irregularity = np.std(spacings) / (avg_spacing + 1)
            
            # Converte irregularidade em ângulo estimado (heurística)
            angle = np.clip(irregularity * 2 - 1, -5, 5)
            
            return angle
            
        except Exception as e:
            logger.warning(f"Erro na detecção de inclinação: {e}")
            return 0.0
