"""
Pré-processamento de imagens antes do OCR
Inclui:
- Deskewing (correção de inclinação)
- Binarização (melhora contraste)
- Remoção de ruído
"""

import io
import logging
from typing import Optional
from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)


class ImagePreprocessor:
    """
    Preprocessa imagens de PDF para melhorar a qualidade do OCR
    
    Técnicas aplicadas:
    1. Deskewing: Corrige páginas escaneadas com inclinação
    2. Binarização: Converte para preto/branco puro
    3. Contraste: Melhora legibilidade
    """
    
    def __init__(self):
        self.deskew_enabled = True
        self.binarization_enabled = True
    
    def preprocess(self, image_bytes: bytes) -> bytes:
        """
        Aplica todas as técnicas de pré-processamento
        
        Args:
            image_bytes: Imagem original em bytes
            
        Returns:
            Imagem processada em bytes
        """
        try:
            # Carrega imagem
            img = Image.open(io.BytesIO(image_bytes))
            
            # Converte para RGB se necessário
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            logger.debug(f"Imagem original: {img.size[0]}x{img.size[1]} pixels")
            
            # Aplica deskewing
            if self.deskew_enabled:
                img = self._deskew_image(img)
            
            # Aplica binarização
            if self.binarization_enabled:
                img = self._binarize_image(img)
            
            # Converte de volta para bytes
            output = io.BytesIO()
            img.save(output, format='PNG', optimize=True)
            output.seek(0)
            
            result = output.read()
            logger.debug(f"Imagem processada: {len(image_bytes)} -> {len(result)} bytes")
            
            return result
            
        except Exception as e:
            logger.warning(f"Erro no pré-processamento, usando imagem original: {e}")
            return image_bytes
    
    def _deskew_image(self, img: Image.Image) -> Image.Image:
        """
        Corrige inclinação da página (deskewing)
        
        Método: Detecção de linhas de texto usando transformada de Hough
        """
        try:
            # Converte para numpy array
            img_array = np.array(img)
            
            # Converte para escala de cinza
            gray = np.dot(img_array[...,:3], [0.2989, 0.5870, 0.1140])
            gray = gray.astype(np.uint8)
            
            # Detecta bordas (simplificado - Sobel)
            sobel_x = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]])
            edges = self._convolve2d(gray, sobel_x)
            
            # Calcula ângulo de inclinação
            angle = self._calculate_skew_angle(edges)
            
            if abs(angle) > 0.5:  # Só corrige se inclinação > 0.5 graus
                logger.info(f"Corrigindo inclinação: {angle:.2f} graus")
                img = img.rotate(angle, expand=True, fillcolor='white')
            else:
                logger.debug(f"Inclinação OK: {angle:.2f} graus")
            
            return img
            
        except Exception as e:
            logger.warning(f"Erro no deskewing: {e}")
            return img
    
    def _calculate_skew_angle(self, edges: np.ndarray) -> float:
        """
        Calcula o ângulo de inclinação da imagem
        
        Método simplificado baseado na análise de bordas horizontais
        """
        try:
            h, w = edges.shape
            
            # Pega apenas a parte central (onde geralmente está o texto)
            center_h = h // 2
            margin = h // 4
            center_region = edges[center_h - margin:center_h + margin, :]
            
            # Soma as intensidades em cada linha
            row_sums = np.sum(center_region, axis=1)
            
            # Encontra linhas com mais bordas (texto)
            threshold = np.mean(row_sums) + np.std(row_sums)
            text_rows = np.where(row_sums > threshold)[0]
            
            if len(text_rows) < 10:
                return 0.0  # Não há texto suficiente para detectar inclinação
            
            # Calcula a inclinação média
            angles = []
            for i in range(0, len(text_rows) - 5, 5):
                y1, y2 = text_rows[i], text_rows[i + 5]
                if y2 > y1:
                    angle = np.arctan2(y2 - y1, w) * 180 / np.pi - 90
                    angles.append(angle)
            
            if angles:
                median_angle = np.median(angles)
                # Limita o ângulo entre -10 e 10 graus
                return np.clip(median_angle, -10, 10)
            
            return 0.0
            
        except Exception as e:
            logger.warning(f"Erro no cálculo de ângulo: {e}")
            return 0.0
    
    def _binarize_image(self, img: Image.Image) -> Image.Image:
        """
        Binarização adaptativa (Otsu's method simplificado)
        Converte para preto/branco puro, melhorando contraste
        """
        try:
            # Converte para escala de cinza
            gray = img.convert('L')
            
            # Converte para numpy
            gray_array = np.array(gray)
            
            # Calcula threshold automático (Otsu simplificado)
            threshold = self._calculate_otsu_threshold(gray_array)
            
            # Aplica threshold
            binary = (gray_array > threshold) * 255
            binary = binary.astype(np.uint8)
            
            # Converte de volta para PIL
            result = Image.fromarray(binary).convert('RGB')
            
            logger.debug(f"Binarização aplicada (threshold: {threshold})")
            
            return result
            
        except Exception as e:
            logger.warning(f"Erro na binarização: {e}")
            return img
    
    def _calculate_otsu_threshold(self, img_array: np.ndarray) -> int:
        """
        Calcula threshold ótimo usando método de Otsu simplificado
        """
        try:
            # Histograma
            hist, _ = np.histogram(img_array.flatten(), bins=256, range=(0, 256))
            hist = hist.astype(float)
            
            # Normaliza
            hist /= hist.sum()
            
            # Calcula threshold que maximiza a variância entre classes
            max_variance = 0
            best_threshold = 127
            
            for t in range(1, 255):
                # Peso das classes
                w0 = hist[:t].sum()
                w1 = hist[t:].sum()
                
                if w0 == 0 or w1 == 0:
                    continue
                
                # Média das classes
                mu0 = (np.arange(t) * hist[:t]).sum() / w0
                mu1 = (np.arange(t, 256) * hist[t:]).sum() / w1
                
                # Variância entre classes
                variance = w0 * w1 * (mu0 - mu1) ** 2
                
                if variance > max_variance:
                    max_variance = variance
                    best_threshold = t
            
            return best_threshold
            
        except Exception as e:
            logger.warning(f"Erro no cálculo de threshold: {e}")
            return 127  # Threshold padrão
    
    def _convolve2d(self, image: np.ndarray, kernel: np.ndarray) -> np.ndarray:
        """
        Convolução 2D simples (para detecção de bordas)
        """
        try:
            h, w = image.shape
            kh, kw = kernel.shape
            
            # Padding
            pad_h = kh // 2
            pad_w = kw // 2
            padded = np.pad(image, ((pad_h, pad_h), (pad_w, pad_w)), mode='edge')
            
            # Convolução
            output = np.zeros_like(image)
            for i in range(h):
                for j in range(w):
                    region = padded[i:i+kh, j:j+kw]
                    output[i, j] = np.abs(np.sum(region * kernel))
            
            return output
            
        except Exception as e:
            logger.warning(f"Erro na convolução: {e}")
            return image
