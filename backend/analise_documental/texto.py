import math
import re
import unicodedata
from bisect import bisect_left
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

MONEY_RE = re.compile(r"(?<![\d.,])(\d{1,3}(?:[.\s]\d{3})*,\d{2})(?![\d])")
DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})(?!\d)")
CNPJ_RE = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")
# "Fls.: 83" costuma sair do OCR como "Fis: 83", "FIs.: 83", "Is: 83" ou "ls. 83"
FOLHA_RE = re.compile(r"(?:\bF\s?[lIi1|]\s?[sS5]|(?<![A-Za-z])[Il|][sS])\s*[.:,;]{1,2}\s*(\d{1,4})\b")
NUMERO_DOC_RE = re.compile(r"\bN\s*[º°o.]\s*[:.]?\s*(\d{1,6}(?:[./-]\d{2,4})?)", re.IGNORECASE)

NAO_IDENTIFICADO = "NÃO IDENTIFICADO NOS DOCUMENTOS DISPONIBILIZADOS – PENDENTE DE CONFERÊNCIA PELO ANALISTA."
PENDENTE_HUMANO = "PENDENTE DE VALIDAÇÃO HUMANA."


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def norm(text: str) -> str:
    """Maiúsculas, sem acento, espaços colapsados — base para regras e comparação."""
    return re.sub(r"\s+", " ", strip_accents(text or "").upper()).strip()


def parse_money(raw) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip().replace("R$", "").replace(" ", "")
    if not s:
        return None
    neg = s.startswith("-") or s.endswith("-")
    s = s.strip("-")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        val = float(s)
    except ValueError:
        return None
    return -val if neg else val


def fmt_money(value: Optional[float]) -> str:
    if value is None:
        return "—"
    s = f"{abs(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if value < 0 else ''}R$ {s}"


def find_money(text: str) -> List[float]:
    out = []
    for m in MONEY_RE.finditer(text or ""):
        v = parse_money(m.group(1).replace(" ", "."))
        if v is not None:
            out.append(v)
    return out


def parse_date(raw) -> Optional[date]:
    if not raw:
        return None
    if isinstance(raw, date):
        return raw
    m = DATE_RE.search(str(raw))
    if not m:
        return None
    d, mth, y = (int(x) for x in m.groups())
    if y < 100:
        y += 2000 if y < 70 else 1900
    try:
        return date(y, mth, d)
    except ValueError:
        return None


def fmt_date(d: Optional[date]) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def find_dates(text: str) -> List[date]:
    out = []
    for m in DATE_RE.finditer(text or ""):
        d = parse_date(m.group(0))
        if d and 1990 <= d.year <= datetime.now().year + 5:
            out.append(d)
    return out


def find_folhas(text: str) -> List[int]:
    """Carimbos de numeração física ("Fls. 123") — o OCR costuma deformá-los."""
    vals = []
    for m in FOLHA_RE.finditer(text or ""):
        n = int(m.group(1))
        if 0 < n < 5000:
            vals.append(n)
    return vals


def select_windows(text: str, patterns: List[str], radius: int = 450, max_chars: int = 5000) -> str:
    """
    Recorta trechos ao redor de palavras-chave para caber no orçamento de tokens.
    Os trechos entram por relevância (variedade de palavras-chave, valendo mais as raras),
    não pela posição: palavras que aparecem em toda página não podem esgotar o orçamento
    com o começo do texto.
    """
    if len(text) <= max_chars:
        return text
    upper = strip_accents(text).upper()
    hits: List[Tuple[int, int]] = []
    for i, pat in enumerate(patterns):
        hits.extend((m.start(), i) for m in re.finditer(pat, upper))
    hits.sort()
    posicoes = [p for p, _ in hits]
    contagem = [0] * len(patterns)
    for _, i in hits:
        contagem[i] += 1
    peso = [1.0 / (1.0 + math.log1p(n)) for n in contagem]

    def score(s: int, e: int) -> float:
        presentes = {i for _, i in hits[bisect_left(posicoes, s):bisect_left(posicoes, e)]}
        return sum(peso[i] for i in presentes)

    cabecalho = (0, min(len(text), 900))
    candidatos = sorted(
        {(max(0, p - radius), min(len(text), p + radius)) for p in posicoes},
        key=lambda se: (-score(*se), se[0]),
    )
    escolhidos: List[Tuple[int, int]] = [cabecalho]
    total = cabecalho[1]
    for s, e in candidatos:
        if total >= max_chars:
            break
        if any(s < pe and e > ps for ps, pe in escolhidos):
            continue
        e = min(e, s + max_chars - total)
        escolhidos.append((s, e))
        total += e - s
    escolhidos.sort()
    return "\n[...]\n".join(text[s:e] for s, e in escolhidos)


def _compact(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", strip_accents(text or "").upper())


def locate_excerpt(trecho: str, pages: List[Tuple[int, str]], min_ratio: float = 0.82) -> Optional[int]:
    """
    Confirma que o trecho citado pela IA existe no OCR e devolve a página.
    A comparação ignora espaços, pontuação e acentos (o OCR os deforma com frequência).
    """
    target = _compact(trecho)
    if len(target) < 6:
        return None
    compacts = [(p, _compact(t)) for p, t in pages]
    for p, c in compacts:
        if target in c:
            return p
    window = len(target)
    step = max(4, window // 4)
    best_page, best_ratio = None, 0.0
    for p, c in compacts:
        if len(c) < window // 2:
            continue
        for i in range(0, max(1, len(c) - window + 1), step):
            ratio = SequenceMatcher(None, target, c[i:i + window], autojunk=False).ratio()
            if ratio > best_ratio:
                best_page, best_ratio = p, ratio
                if ratio >= 0.97:
                    return p
    return best_page if best_ratio >= min_ratio else None


def value_in_excerpt(valor, trecho: str) -> bool:
    """O valor numérico/data informado precisa aparecer no próprio trecho citado."""
    if valor is None or not trecho:
        return False
    if isinstance(valor, (int, float)):
        cents = f"{abs(float(valor)):.2f}".replace(".", "")
        digits = re.sub(r"\D", "", trecho)
        return cents.lstrip("0") in digits if cents.strip("0") else True
    d = parse_date(valor) if DATE_RE.search(str(valor)) else None
    if d:
        return any(x == d for x in find_dates(trecho)) or d.strftime("%d/%m/%Y") in trecho
    return True


def jaccard_shingles(a: str, b: str, k: int = 3) -> float:
    wa, wb = norm(a).split(), norm(b).split()
    sa = {" ".join(wa[i:i + k]) for i in range(max(0, len(wa) - k + 1))}
    sb = {" ".join(wb[i:i + k]) for i in range(max(0, len(wb) - k + 1))}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)
