"""
Gerenciador de progresso em tempo real
Envia atualizações via callback para WebSocket
"""

import logging
from typing import Optional, Callable
from datetime import datetime

logger = logging.getLogger(__name__)


class ProgressManager:
    """
    Gerencia o progresso do processamento e notifica em tempo real
    """
    
    def __init__(self, callback: Optional[Callable] = None):
        self.callback = callback
        self.current_step = 0
        self.total_steps = 0
        self.current_message = ""
        self.started_at = None
    
    def start(self, total_pages: int):
        """Inicia o rastreamento de progresso"""
        self.started_at = datetime.now()
        # Cada página tem 2 etapas: OCR + Parser
        self.total_steps = total_pages * 2
        self.current_step = 0
        self._notify("Iniciando processamento...", 0)
    
    def update_ocr(self, page_num: int, total_pages: int):
        """Atualiza progresso do OCR"""
        self.current_step += 1
        message = f"Lendo página {page_num}/{total_pages} (OCR)"
        progress = int((self.current_step / self.total_steps) * 100)
        self._notify(message, progress)
    
    def update_parser(self, page_num: int, total_pages: int, found_resumo: bool = False):
        """Atualiza progresso do parser"""
        self.current_step += 1
        if found_resumo:
            message = f"✓ Resumo encontrado na página {page_num}/{total_pages}"
        else:
            message = f"Analisando página {page_num}/{total_pages}"
        progress = int((self.current_step / self.total_steps) * 100)
        self._notify(message, progress)
    
    def update_preprocessing(self, page_num: int, total_pages: int):
        """Atualiza progresso do pré-processamento"""
        message = f"Corrigindo inclinação da página {page_num}/{total_pages}"
        # Não incrementa current_step (é parte do OCR)
        progress = int((self.current_step / self.total_steps) * 100)
        self._notify(message, progress)
    
    def update_saving(self, resumos_count: int):
        """Atualiza quando estiver salvando no banco"""
        message = f"Salvando {resumos_count} resumos no banco..."
        self._notify(message, 95)
    
    def complete(self, resumos_count: int):
        """Finaliza o processamento"""
        elapsed = (datetime.now() - self.started_at).total_seconds()
        message = f"✓ Concluído! {resumos_count} resumos extraídos em {elapsed:.1f}s"
        self._notify(message, 100)
    
    def error(self, error_message: str):
        """Notifica erro"""
        message = f"✗ Erro: {error_message}"
        self._notify(message, -1)
    
    def _notify(self, message: str, progress: int):
        """Envia notificação via callback"""
        self.current_message = message
        
        payload = {
            "message": message,
            "progress": progress,
            "step": self.current_step,
            "total_steps": self.total_steps
        }
        
        logger.info(f"[PROGRESSO {progress}%] {message}")
        
        if self.callback:
            try:
                self.callback(payload)
            except Exception as e:
                logger.warning(f"Erro ao enviar progresso via callback: {e}")
