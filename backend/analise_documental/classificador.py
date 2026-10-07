import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from backend.analise_documental.texto import find_folhas, norm
from backend.analise_documental.tipos import ILEGIVEL, INDEFINIDO, TIPOS, TIPOS_POR_CODIGO, lista_para_prompt
from backend.ocr_service import HybridOCR

logger = logging.getLogger(__name__)

HEADER_CHARS = 700
MIN_SCORE = 4.0
MIN_MARGIN = 1.5
LLM_BATCH = 8
LLM_SNIPPET = 650

ANEXO_RE = re.compile(r"ANEXO\s+([IVXL]{1,6})\s*[-–:.]?\s*([A-Z][A-Z /,-]{4,70})")

EMAIL_RE = re.compile(r"\bDE:.{0,120}ENVIADO EM:", re.S)
PC_RE = re.compile(r"PRESTA[CG]AO DE CONTAS")
NAO_PC_RE = re.compile(r"SOLICITA\w*\s+(DE\s+)?VISTORIA|TERMO ADITIVO|ANUENCIA")
SOLICITACAO_RE = re.compile(r"OF[IL]CIO DE SOLICITA[CG]AO|SOLICITA[CG]AO DE CELEBRA[CG]AO|CELEBRA[CG]AO D[OE] CONVENIO")
CARTA_RE = re.compile(r"\bOF[IL]CIO\b\s*(N|NO|Nº|N°|:)|\bMEMO\b|\bASSUNTO:")
INSTRUMENTO_RE = re.compile(r"CLAUSULA|RESOLVEM|CELEBRAM|PARTICIPES")
PARECER_FINAL_RE = re.compile(
    r"FASE FINAL|VISTORIA FINAL|PRESTA[CG]AO DE CONTAS FINAL|OBJETO (FOI )?(EXECUTADO|CONCLUIDO)|"
    r"OBRA CONCLUIDA|CONCLUSAO DA OBRA|100\s*%")
ACOMPANHAMENTO_RE = re.compile(r"FASE INICIAL|FASE INTERMEDIARIA|CONFORMIDADE TECNICA|\b\d\s*\S?\s*PARCELA")
DECLARACAO_RE = re.compile(r"\bDECLAR(O|AMOS)\b.{0,20}PARA (OS )?(DEVIDOS )?FINS", re.S)


@dataclass
class Pagina:
    arquivo: str
    pagina: int
    texto: str
    engine: str
    ordem: int = 0
    qualidade: float = 0.0
    tipo: str = INDEFINIDO
    score: float = 0.0
    fonte: str = "regra"
    continuacao: bool = False
    titulo_anexo: Optional[str] = None
    folhas: List[int] = field(default_factory=list)
    candidatos: Dict[str, float] = field(default_factory=dict)

    @property
    def ref(self) -> str:
        return f"{self.arquivo} p.{self.pagina}"


def _score_page(texto_norm: str) -> Dict[str, float]:
    header = texto_norm[:HEADER_CHARS]
    scores: Dict[str, float] = {}
    for tipo in TIPOS:
        total = 0.0
        for pattern, weight in tipo.padroes:
            if re.search(pattern, header):
                total += weight * 1.6
            elif re.search(pattern, texto_norm):
                total += weight
        if total:
            scores[tipo.codigo] = round(total, 2)
    return scores


def _refinar(pg: Pagina, texto_norm: str) -> None:
    """
    Separa documentos que usam o vocabulário de outro tipo: só é ofício de encaminhamento
    o que trata da prestação de contas; carta pedindo aditivo não é o aditivo; nota técnica
    de celebração/fase inicial ou declaração do engenheiro do convenente não é o Parecer final.
    """
    if pg.tipo == ILEGIVEL:
        return
    header = texto_norm[:HEADER_CHARS]
    if EMAIL_RE.search(header):
        pg.tipo = "CORRESPONDENCIA"
    elif pg.tipo == "OFICIO":
        if SOLICITACAO_RE.search(header):
            pg.tipo = "OFICIO_SOLICITACAO"
        elif not PC_RE.search(texto_norm) or NAO_PC_RE.search(header):
            pg.tipo = "CORRESPONDENCIA"
    elif pg.tipo == "TERMO_ADITIVO":
        if CARTA_RE.search(header) and not INSTRUMENTO_RE.search(texto_norm):
            pg.tipo = "CORRESPONDENCIA"
    elif pg.tipo == "PARECER_TECNICO" and not PARECER_FINAL_RE.search(texto_norm):
        if DECLARACAO_RE.search(texto_norm):
            pg.tipo = "DECLARACAO"
        elif ACOMPANHAMENTO_RE.search(texto_norm):
            pg.tipo = "NOTA_TECNICA_ACOMPANHAMENTO"


def classificar_por_regras(paginas: List[Pagina]) -> None:
    for i, pg in enumerate(paginas):
        pg.ordem = i
        pg.qualidade = HybridOCR.text_quality(pg.texto)
        pg.folhas = find_folhas(pg.texto[:900])
        n = norm(pg.texto)
        m = ANEXO_RE.search(n[:1500])
        if m:
            pg.titulo_anexo = f"ANEXO {m.group(1)} – {m.group(2).strip(' -')}"

        if len(n) < 60 or (pg.qualidade < 0.2 and len(n) < 400):
            pg.tipo, pg.fonte = ILEGIVEL, "regra"
            continue

        scores = _score_page(n)
        pg.candidatos = dict(sorted(scores.items(), key=lambda kv: -kv[1])[:4])
        if not scores:
            pg.tipo, pg.score = INDEFINIDO, 0.0
            continue
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        best, best_score = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0.0
        # Cabeçalho genérico dos formulários SETOP não deve vencer um tipo específico
        if best == "PRESTACAO_CONTAS" and len(ranked) > 1 and ranked[1][1] >= MIN_SCORE:
            best, best_score = ranked[1]
            second = scores["PRESTACAO_CONTAS"]
        pg.score = best_score
        # Em texto muito ruidoso um padrão curto (ex.: "DAE") casa por acaso
        ruidosa = pg.qualidade < 0.25 and best_score < 2 * MIN_SCORE
        if not ruidosa and best_score >= MIN_SCORE and (best_score - second >= MIN_MARGIN or best_score >= 2 * MIN_SCORE):
            pg.tipo = best
            _refinar(pg, n)
        else:
            pg.tipo = INDEFINIDO


def _llm_prompt(batch: List[Pagina], anterior: Dict[int, str]) -> str:
    blocos = []
    for pg in batch:
        trecho = re.sub(r"\s+", " ", pg.texto)[:LLM_SNIPPET]
        prev = anterior.get(pg.ordem, "nenhuma")
        blocos.append(f"### PAGINA id={pg.ordem} ({pg.ref}; tipo da página anterior: {prev})\n{trecho}")
    return (
        "Classifique cada página de um processo de prestação de contas de convênio "
        "(texto obtido por OCR, pode conter ruído).\n\n"
        f"TIPOS PERMITIDOS:\n{lista_para_prompt()}\n- INDEFINIDO: não é possível afirmar\n\n"
        "Regras:\n"
        "1. Use somente os códigos acima. Se o texto não sustentar a classificação, use INDEFINIDO.\n"
        "2. continuacao=true quando a página claramente continua o documento da página anterior "
        "(ex.: segunda folha de contrato, cláusulas sem cabeçalho).\n"
        "3. confianca entre 0 e 1.\n\n"
        + "\n\n".join(blocos)
        + '\n\nResponda em JSON: {"paginas": [{"id": <int>, "tipo": "<CODIGO>", "continuacao": <bool>, "confianca": <float>}]}'
    )


async def classificar_com_ia(
    paginas: List[Pagina],
    llm,
    progress: Optional[Callable] = None,
) -> int:
    """Refina páginas INDEFINIDO via IA (em lotes). Devolve quantas páginas foram enviadas."""
    if not llm or not llm.enabled:
        return 0
    pendentes = [p for p in paginas if p.tipo == INDEFINIDO]
    if not pendentes:
        return 0
    anterior = {p.ordem: paginas[p.ordem - 1].tipo if p.ordem > 0 else "nenhuma" for p in pendentes}
    for i in range(0, len(pendentes), LLM_BATCH):
        batch = pendentes[i:i + LLM_BATCH]
        if progress:
            await progress(f"Classificando páginas com IA ({i + len(batch)}/{len(pendentes)})")
        try:
            data = await llm.acomplete_json(
                "Você classifica documentos administrativos brasileiros. Responda apenas JSON.",
                _llm_prompt(batch, anterior),
                max_tokens=900,
                fast=True,
            )
        except Exception as exc:
            logger.warning("Classificação IA falhou para lote %s: %s", i // LLM_BATCH, exc)
            continue
        por_id = {pg.ordem: pg for pg in batch}
        for item in data.get("paginas", []) or []:
            try:
                pg = por_id.get(int(item.get("id")))
            except (TypeError, ValueError):
                continue
            if not pg:
                continue
            tipo = str(item.get("tipo") or "").strip().upper()
            conf = float(item.get("confianca") or 0)
            pg.continuacao = bool(item.get("continuacao"))
            if tipo in TIPOS_POR_CODIGO and conf >= 0.55:
                pg.tipo, pg.fonte, pg.score = tipo, "ia", round(conf, 2)
                _refinar(pg, norm(pg.texto))
    return len(pendentes)


def aplicar_continuacoes(paginas: List[Pagina]) -> None:
    """
    Páginas sem classificação logo após um documento de várias páginas
    (contrato, licitação, planilhas) são tratadas como continuação dele.
    """
    for i, pg in enumerate(paginas):
        if i == 0 or (pg.tipo != INDEFINIDO and not pg.continuacao):
            continue
        prev = paginas[i - 1]
        prev_tipo = TIPOS_POR_CODIGO.get(prev.tipo)
        if not prev_tipo:
            continue
        if pg.tipo == INDEFINIDO and not prev_tipo.pagina_unica and (
            pg.score < 2.0 or prev.tipo in pg.candidatos
        ):
            pg.tipo, pg.fonte, pg.continuacao = prev.tipo, "continuação presumida", True
        elif pg.continuacao and pg.tipo != prev.tipo:
            # A IA disse que continua o anterior: prevalece o tipo do documento em curso
            pg.tipo, pg.fonte = prev.tipo, "continuação (ia)"
