"""
OCR híbrido para produção (sem Google Vision):
1. PDF digital  → texto nativo via PyMuPDF
2. PDF escaneado / texto fraco → rasteriza + Tesseract (pt)
3. Imagem       → Tesseract (+ pré-processamento adaptativo se necessário)
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
from dataclasses import dataclass
from typing import Callable, List, Optional

import fitz  # PyMuPDF
from dotenv import load_dotenv
from PIL import Image

from backend.adaptive_preprocessing import AdaptiveImagePreprocessor

load_dotenv()
logger = logging.getLogger(__name__)

# O Tesseract abre várias threads por página (OpenMP); com 1 a CPU não dispara e o
# ganho de velocidade perdido é pequeno no modo psm 6. Ajustável por TESSERACT_THREADS.
os.environ.setdefault("OMP_THREAD_LIMIT", os.getenv("TESSERACT_THREADS", "1"))

# Qualidade mínima para aceitar texto nativo do PDF
MIN_NATIVE_CHARS = 40
MIN_NATIVE_DIGITS = 4
# Abaixo disso o texto do Tesseract é tratado como lixo (página deitada, foto, carimbo)
LOW_QUALITY_SCORE = 0.35


@dataclass
class PageOCRResult:
    text: str
    engine: str  # native | tesseract | tesseract_enhanced | tesseract_rotacionado
    char_count: int = 0

    def __post_init__(self):
        self.char_count = len(self.text or "")


class HybridOCR:
    """Extrator local: PyMuPDF + Tesseract. Interface estável para o coordinator."""

    def __init__(self):
        self.preprocessor = AdaptiveImagePreprocessor()
        self.tesseract_cmd = os.getenv("TESSERACT_CMD", "").strip()
        self.tesseract_lang = os.getenv("TESSERACT_LANG", "por+eng")
        self.tesseract_config = os.getenv("TESSERACT_CONFIG", "--oem 3 --psm 6")
        self._tesseract_ready = False
        self._init_tesseract()
        logger.info(
            "HybridOCR pronto (native PDF + Tesseract). tesseract=%s lang=%s",
            "OK" if self._tesseract_ready else "INDISPONÍVEL",
            self.tesseract_lang,
        )

    def _init_tesseract(self) -> None:
        try:
            import pytesseract

            if self.tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
            # Smoke test
            pytesseract.get_tesseract_version()
            self._tesseract_ready = True
        except Exception as e:
            self._tesseract_ready = False
            logger.error("Tesseract indisponível: %s", e)

    @staticmethod
    def _is_weak_text(text: str) -> bool:
        if not text or len(text.strip()) < MIN_NATIVE_CHARS:
            return True
        digits = len(re.findall(r"\d", text))
        return digits < MIN_NATIVE_DIGITS

    @staticmethod
    def text_quality(text: str) -> float:
        """Fração do texto formada por palavras legíveis (0 = lixo de OCR, 1 = texto limpo)."""
        if not text:
            return 0.0
        compact = re.sub(r"\s+", "", text)
        if not compact:
            return 0.0
        words = re.findall(r"[A-Za-zÀ-ÿ]{4,}", text)
        good = sum(len(w) for w in words if re.search(r"[aeiouáéíóúâêôãõAEIOUÁÉÍÓÚÂÊÔÃÕ]", w))
        return good / len(compact)

    @staticmethod
    def _open_image(data: bytes) -> Image.Image:
        image = Image.open(io.BytesIO(data))
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        return image

    def _ocr_pil(self, image: Image.Image) -> str:
        import pytesseract

        text = pytesseract.image_to_string(
            image,
            lang=self.tesseract_lang,
            config=self.tesseract_config,
        )
        return (text or "").strip()

    def _ocr_image_bytes(self, img_bytes: bytes, enhance: bool = False) -> str:
        if not self._tesseract_ready:
            logger.error("Tesseract não disponível — página sem OCR")
            return ""

        data = img_bytes
        if enhance:
            data = self.preprocessor.enhance_image(img_bytes)
        return self._ocr_pil(self._open_image(data))

    def _ocr_rotated(self, img_bytes: bytes) -> Optional[str]:
        """Detecta página digitalizada deitada/invertida (OSD) e refaz o OCR já rotacionada."""
        if not self._tesseract_ready:
            return None
        import pytesseract

        image = self._open_image(img_bytes)
        try:
            osd = pytesseract.image_to_osd(image, config="--psm 0")
        except Exception:
            # Fotos e páginas quase sem texto não têm caracteres suficientes para o OSD
            return None
        rot = re.search(r"Rotate:\s*(\d+)", osd)
        conf = re.search(r"Orientation confidence:\s*([\d.]+)", osd)
        if not rot or int(rot.group(1)) == 0:
            return None
        if conf and float(conf.group(1)) < 1.0:
            return None
        return self._ocr_pil(image.rotate(-int(rot.group(1)), expand=True))

    async def _ocr_image_async(self, img_bytes: bytes, enhance: bool = False) -> str:
        return await asyncio.to_thread(self._ocr_image_bytes, img_bytes, enhance)

    async def _ocr_best(self, img_bytes: bytes, page_label: str) -> tuple:
        """OCR com duas tentativas de recuperação: rotação (OSD) e pré-processamento."""
        text = await self._ocr_image_async(img_bytes, enhance=False)
        engine = "tesseract"

        if self.text_quality(text) < LOW_QUALITY_SCORE:
            rotated = await asyncio.to_thread(self._ocr_rotated, img_bytes)
            if rotated and self.text_quality(rotated) > self.text_quality(text):
                logger.info("%s: página rotacionada corrigida pelo OSD", page_label)
                text, engine = rotated, "tesseract_rotacionado"

        if self.preprocessor.should_enhance(text):
            logger.warning("%s: OCR fraco, tentando pré-processamento", page_label)
            retry = await self._ocr_image_async(img_bytes, enhance=True)
            if len(retry) > len(text) and self.text_quality(retry) >= self.text_quality(text):
                text, engine = retry, "tesseract_enhanced"
        return text, engine

    def _page_to_png(self, page: fitz.Page, zoom: float = 2.5) -> bytes:
        # Cinza ocupa 1/3 da memória do RGB e o Tesseract binariza a imagem de qualquer forma
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csGRAY, alpha=False)
        return pix.tobytes("png")

    async def _extract_pdf_page(
        self, page: fitz.Page, page_num: int
    ) -> PageOCRResult:
        native = (page.get_text("text") or "").strip()
        if not self._is_weak_text(native):
            logger.info("Página %s: texto nativo (%s chars)", page_num, len(native))
            return PageOCRResult(text=native, engine="native")

        logger.info(
            "Pagina %s: texto nativo fraco (%s chars) -> Tesseract",
            page_num,
            len(native),
        )
        img_bytes = await asyncio.to_thread(self._page_to_png, page, 2.5)
        text, engine = await self._ocr_best(img_bytes, f"Página {page_num}")

        # Se Tesseract falhou mas havia algum nativo, usa o nativo como fallback
        if not text and native:
            return PageOCRResult(text=native, engine="native_weak")

        return PageOCRResult(text=text, engine=engine)

    async def extract_pages_detailed(
        self,
        file_content: bytes,
        progress_callback: Optional[Callable] = None,
    ) -> List[PageOCRResult]:
        is_pdf = file_content.startswith(b"%PDF-")
        results: List[PageOCRResult] = []

        try:
            if is_pdf:
                doc = fitz.open(stream=file_content, filetype="pdf")
                num_pages = len(doc)
                logger.info("HybridOCR PDF: %s páginas", num_pages)

                if progress_callback:
                    await progress_callback(
                        {
                            "message": f"Extraindo texto de {num_pages} páginas (PDF nativo + Tesseract)...",
                            "progress": 0,
                            "step": 0,
                            "total_steps": num_pages,
                        }
                    )

                for page_num in range(num_pages):
                    if progress_callback:
                        await progress_callback(
                            {
                                "message": f"Lendo página {page_num + 1}/{num_pages}...",
                                "progress": int((page_num / max(num_pages, 1)) * 100),
                                "step": page_num + 1,
                                "total_steps": num_pages,
                            }
                        )
                    page = doc.load_page(page_num)
                    result = await self._extract_pdf_page(page, page_num + 1)
                    results.append(result)
                    logger.info(
                        "Página %s: engine=%s chars=%s",
                        page_num + 1,
                        result.engine,
                        result.char_count,
                    )

                doc.close()
            else:
                if progress_callback:
                    await progress_callback(
                        {"message": "OCR da imagem (Tesseract)...", "progress": 30}
                    )
                text, engine = await self._ocr_best(file_content, "Imagem")
                results.append(PageOCRResult(text=text, engine=engine))
                if progress_callback:
                    await progress_callback({"message": "OCR concluído", "progress": 100})

            logger.info("HybridOCR concluído: %s páginas", len(results))
            return results

        except Exception as e:
            logger.error("Erro crítico no HybridOCR: %s", e, exc_info=True)
            return results

    async def extract_text_pages(
        self,
        file_content: bytes,
        progress_callback: Optional[Callable] = None,
    ) -> List[str]:
        """Compatível com a API antiga (só textos)."""
        detailed = await self.extract_pages_detailed(file_content, progress_callback)
        return [p.text for p in detailed]


# Alias legado: qualquer import antigo de GoogleVisionOCR usa o híbrido
GoogleVisionOCR = HybridOCR
