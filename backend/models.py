from pydantic import BaseModel
from typing import Optional, Literal, Dict, List, Any


class ExtractionResult(BaseModel):
    campo: str
    valor: Optional[float] = None
    data_extracao: Optional[str] = None
    pagina: Optional[int] = None
    linha_ocr: Optional[str] = None
    confianca: Literal["ALTA", "MEDIA", "BAIXA", "AMBIGUO"]
    status: Literal["SUCESSO", "FALHA", "Vazio", "AMBIGUO"]

class DocumentResponse(BaseModel):
    resultados_por_pagina: Dict[int, List[ExtractionResult]]
    resumos_mensais: Optional[Dict[int, Dict[str, Any]]] = {}
    movimentacoes_cc: Optional[List[Dict[str, Any]]] = []  # Novo: transações CC
    ocr_bruto: str
