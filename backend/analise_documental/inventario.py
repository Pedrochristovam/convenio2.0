from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.analise_documental.classificador import Pagina
from backend.analise_documental.texto import (
    NUMERO_DOC_RE,
    find_dates,
    find_money,
    fmt_date,
    jaccard_shingles,
    norm,
)
from backend.analise_documental.tipos import ILEGIVEL, INDEFINIDO, TIPOS_POR_CODIGO, nome_tipo

# Tipos que se alternam página a página e formam um único bloco no inventário
FAMILIAS = {
    "EXTRATO_CC": "EXTRATOS",
    "EXTRATO_APLICACAO": "EXTRATOS",
}
NOME_FAMILIA = {"EXTRATOS": "Extratos bancários (conta corrente e aplicação)"}

DUPLICATE_THRESHOLD = 0.9
DUPLICATE_MIN_CHARS = 300


@dataclass
class Documento:
    id: str
    tipo: str
    nome: str
    paginas: List[Pagina]
    titulo_anexo: Optional[str] = None
    duplicado_de: Optional[str] = None
    extracao: Dict[str, Any] = field(default_factory=dict)
    subtipos: Dict[str, int] = field(default_factory=dict)

    @property
    def texto(self) -> str:
        return "\n".join(p.texto for p in self.paginas)

    @property
    def pares_pagina_texto(self):
        return [(p.ordem, p.texto) for p in self.paginas]

    @property
    def localizacao(self) -> str:
        partes = []
        por_arquivo: Dict[str, List[int]] = {}
        for p in self.paginas:
            por_arquivo.setdefault(p.arquivo, []).append(p.pagina)
        for arq, pags in por_arquivo.items():
            ini, fim = min(pags), max(pags)
            partes.append(f"{arq}, p. {ini}" if ini == fim else f"{arq}, pp. {ini}–{fim}")
        folhas = sorted({f for p in self.paginas for f in p.folhas})
        if folhas:
            partes.append(f"fl. {folhas[0]}" if len(folhas) == 1 else f"fls. {folhas[0]}–{folhas[-1]}")
        return "; ".join(partes)

    def to_dict(self) -> Dict[str, Any]:
        texto = self.texto
        datas = find_dates(texto)
        valores = find_money(texto)
        numero = NUMERO_DOC_RE.search(norm(texto)[:1500])
        return {
            "id": self.id,
            "tipo": self.tipo,
            "nome": self.nome,
            "titulo_anexo": self.titulo_anexo,
            "localizacao": self.localizacao,
            "paginas": [{"arquivo": p.arquivo, "pagina": p.pagina, "ordem": p.ordem} for p in self.paginas],
            "total_paginas": len(self.paginas),
            "classificacao": sorted({p.fonte for p in self.paginas}),
            "confianca_min": min((p.score for p in self.paginas), default=0),
            "subtipos": self.subtipos,
            "numero_detectado": numero.group(1) if numero else None,
            "datas_detectadas": [fmt_date(d) for d in sorted(set(datas))[:6]],
            "periodo_detectado": f"{fmt_date(min(datas))} a {fmt_date(max(datas))}" if len(datas) > 1 else None,
            "maior_valor_detectado": max(valores) if valores else None,
            "duplicado_de": self.duplicado_de,
            "extracao": self.extracao,
        }


def agrupar_documentos(paginas: List[Pagina]) -> List[Documento]:
    docs: List[Documento] = []
    atual: Optional[Documento] = None

    for pg in paginas:
        tipo = pg.tipo
        familia = FAMILIAS.get(tipo)
        chave = familia or tipo
        info = TIPOS_POR_CODIGO.get(tipo)
        unica = bool(info and info.pagina_unica) or tipo in (ILEGIVEL, INDEFINIDO)
        novo_anexo = pg.titulo_anexo and atual and pg.titulo_anexo != atual.titulo_anexo

        mesma_serie = atual is not None and atual.tipo == chave and not novo_anexo
        if mesma_serie and (not unica or pg.continuacao):
            atual.paginas.append(pg)
        else:
            atual = Documento(
                id="",
                tipo=chave,
                nome=NOME_FAMILIA.get(chave) or nome_tipo(tipo),
                paginas=[pg],
                titulo_anexo=pg.titulo_anexo,
            )
            docs.append(atual)
        if familia:
            atual.subtipos[tipo] = atual.subtipos.get(tipo, 0) + 1

    for i, d in enumerate(docs, start=1):
        d.id = f"D{i:03d}"
    return docs


def marcar_duplicados(docs: List[Documento]) -> int:
    """Documentos com texto praticamente idêntico a outro do mesmo tipo (item 4: não contar duas vezes)."""
    total = 0
    textos = {d.id: d.texto for d in docs}
    for i, d in enumerate(docs):
        if d.duplicado_de or d.tipo in (ILEGIVEL, INDEFINIDO, "EXTRATOS"):
            continue
        if len(textos[d.id]) < DUPLICATE_MIN_CHARS:
            continue
        for prev in docs[:i]:
            if prev.tipo != d.tipo or prev.duplicado_de:
                continue
            if abs(len(textos[prev.id]) - len(textos[d.id])) > 0.3 * len(textos[d.id]):
                continue
            if jaccard_shingles(textos[prev.id], textos[d.id]) >= DUPLICATE_THRESHOLD:
                d.duplicado_de = prev.id
                total += 1
                break
    return total
