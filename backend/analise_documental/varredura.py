"""
Varredura determinística do OCR inteiro.

Dados que se repetem ao longo do processo (número do convênio, conta específica,
interveniente, licitação, contrato) são lidos por consenso de ocorrências: uma
leitura isolada errada do OCR ou da IA perde para a forma que aparece dezenas de
vezes. Também converte página do PDF em folha física quando o nome do arquivo
traz a faixa digitalizada ("Páginas 002-213").
"""

import re
from collections import Counter
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.analise_documental.texto import fmt_date, fmt_money, norm, parse_date, parse_money

ARQ_PAGINAS_RE = re.compile(r"PAGINAS?\s*(\d{1,4})\s*[-A]\s*(\d{1,4})")
ARQ_VOLUME_RE = re.compile(r"VOLUME\s*(\d{1,2})")

MESES_EXTENSO = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
                 "outubro", "novembro", "dezembro"]
MESES_NUM = {"JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8,
             "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12}

# Secretarias intervenientes: sigla → (rótulo usado na AD, nome completo, sigla atual)
SECRETARIAS = {
    "SETOP": ("SETOP/SEINFRA", "Secretaria de Estado de Infraestrutura e Mobilidade de Minas Gerais - SEINFRA", "SEINFRA"),
    "SEINFRA": ("SEINFRA", "Secretaria de Estado de Infraestrutura e Mobilidade de Minas Gerais - SEINFRA", "SEINFRA"),
    "SEDRU": ("SEDRU", "Secretaria de Estado de Desenvolvimento Regional e Política Urbana - SEDRU", "SEDRU"),
    "SEGOV": ("SEGOV", "Secretaria de Estado de Governo - SEGOV", "SEGOV"),
    "SEDESE": ("SEDESE", "Secretaria de Estado de Desenvolvimento Social - SEDESE", "SEDESE"),
    "SEE": ("SEE", "Secretaria de Estado de Educação - SEE", "SEE"),
    "SES": ("SES", "Secretaria de Estado de Saúde - SES", "SES"),
    "SEAPA": ("SEAPA", "Secretaria de Estado de Agricultura, Pecuária e Abastecimento - SEAPA", "SEAPA"),
    "SECULT": ("SECULT", "Secretaria de Estado de Cultura e Turismo - SECULT", "SECULT"),
    "SEDE": ("SEDE", "Secretaria de Estado de Desenvolvimento Econômico - SEDE", "SEDE"),
    "SEJUSP": ("SEJUSP", "Secretaria de Estado de Justiça e Segurança Pública - SEJUSP", "SEJUSP"),
    "SEMAD": ("SEMAD", "Secretaria de Estado de Meio Ambiente e Desenvolvimento Sustentável - SEMAD", "SEMAD"),
    "SEESP": ("SEESP", "Secretaria de Estado de Esportes - SEESP", "SEESP"),
}
NOMES_SECRETARIAS = {
    "SECRETARIA DE ESTADO DE TRANSPORTES E OBRAS PUBLICAS": "SETOP",
    "SECRETARIA DE ESTADO DE INFRAESTRUTURA": "SEINFRA",
    "SECRETARIA DE ESTADO DE DESENVOLVIMENTO REGIONAL": "SEDRU",
    "SECRETARIA DE ESTADO DE ESPORTES": "SEESP",
    "SECRETARIA DE ESTADO DE EDUCACAO": "SEE",
    "SECRETARIA DE ESTADO DE SAUDE": "SES",
}
BANCOS = (("BANCO DO BRASIL", "Banco do Brasil"), ("CAIXA ECONOMICA", "Caixa Econômica Federal"),
          ("BRADESCO", "Bradesco"), ("ITAU", "Itaú"), ("SANTANDER", "Santander"), ("SICOOB", "Sicoob"))

NUM_CONV_RE = re.compile(r"CONVENIO\W{0,12}(?:N\W{0,4})?(?:DE SAIDA\W{0,6})?(\d{1,6}(?:[.\s]?\d{3,6})?)\s*[/-]\s*(\d{4}|\d{2})\b")
VIG_RE = (
    re.compile(r"VIGENCIA\W{0,4}(?:ATE\W{0,3})?(\d{1,2}/\d{1,2}/\d{4})"),
    re.compile(r"VIGENCIA[^.]{0,80}?\bATE\b\W{0,3}(?:O DIA\W{0,3})?(\d{1,2}/\d{1,2}/\d{4})"),
)
AG_RE = re.compile(r"AG(?:ENCIA|\.)?(?: BANCARIA| VINCULADA)?\W{0,8}(?:N\W{0,3})?(\d[\d.]{0,5})\s?-\s?([\dX])\b")
CONTA_RE = re.compile(r"CONTA(?: CORRENTE| BANCARIA)?\W{0,8}(?:N\W{0,3})?(\d{1,3}(?:\.\d{3})+|\d{3,9})\s?-\s?([\dX])\b")
PROC_RE = re.compile(r"PROCESSO LICITATORIO\W{0,6}(?:N\W{0,4})?(\d{1,5})(?:\s*/\s*(\d{4}))?")
MOD_RE = re.compile(r"(CONCORRENCIA(?: PUBLICA)?|TOMADA DE PRECOS?|CONVITE|PREGAO(?: PRESENCIAL| ELETRONICO)?)"
                    r"\W{0,6}(?:N\W{0,4})?(\d{1,4})\s*/\s*(\d{4})")
CONTRATO_RE = re.compile(r"CONTRATO(?: ADMINISTRATIVO)?(?: DE [A-Z ]{3,70}?)?\W{0,4}N\W{0,4}(?:[A-Z]{2,6}\s*-\s*)?(\d{1,4})\s*/\s*(\d{4})")
VALOR_CONTRATO_RE = re.compile(r"VALOR (?:GLOBAL |TOTAL )?(?:DO CONTRATO|CONTRATUAL|GLOBAL)\W{0,12}R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})")
PRORROGACAO_RE = re.compile(r"PRORROGACAO DO PRAZO DE VIGENCIA[^.]{0,80}?POR MAIS (\d{1,2})\s*\(?[A-Z ]*\)?\s*MES(?:ES)?,?\s*CONTADOS? (?:DESTA|DA) DATA")
DATA_EXTENSO_RE = re.compile(r"(\d{1,2})\s*(?:DE\s*)?(JANEIRO|FEVEREIRO|MARCO|ABRIL|MAIO|JUNHO|JULHO|AGOSTO|SETEMBRO|OUTUBRO|NOVEMBRO|DEZEMBRO)\s*(?:DE\s*)?(\d{4})")
OS_RE = re.compile(r"ORDEM DE SERVICOS?\W{0,6}N\W{0,4}\d")

MODALIDADES = {"CONCORRENCIA": "Concorrência Pública", "CONCORRENCIA PUBLICA": "Concorrência Pública",
               "TOMADA DE PRECO": "Tomada de Preços", "TOMADA DE PRECOS": "Tomada de Preços", "CONVITE": "Convite",
               "PREGAO": "Pregão", "PREGAO PRESENCIAL": "Pregão Presencial", "PREGAO ELETRONICO": "Pregão Eletrônico"}


# ─────────────────────────────────────────────────────────────────────────────
# Folhas
# ─────────────────────────────────────────────────────────────────────────────

def _arq(arquivo: str) -> str:
    return norm((arquivo or "").replace("_", " "))


def primeira_folha(arquivo: str) -> Optional[int]:
    m = ARQ_PAGINAS_RE.search(_arq(arquivo))
    return int(m.group(1)) if m else None


def volume(arquivo: str) -> Optional[int]:
    m = ARQ_VOLUME_RE.search(_arq(arquivo))
    return int(m.group(1)) if m else None


def folha(arquivo: str, pagina: int) -> Optional[int]:
    ini = primeira_folha(arquivo)
    return ini + int(pagina) - 1 if ini is not None else None


def _fmt_fl(n: int) -> str:
    return f"{n:02d}"


def faixa_folhas(refs: Iterable[Tuple[str, int]], principal: Optional[str] = None) -> Tuple[str, bool]:
    """
    "35-59" para páginas do volume principal; "Vol. 1, fls. 88-101" para outros volumes.
    Sem faixa no nome do arquivo, devolve arquivo/página (a conferir).
    """
    por_arq: Dict[str, List[int]] = {}
    for arq, pag in refs:
        por_arq.setdefault(arq, []).append(int(pag))
    if not por_arq:
        return "", False
    partes, confiavel = [], True
    ordem = sorted(por_arq, key=lambda a: (a != principal, volume(a) or 99))
    for arq in ordem:
        pags = sorted(por_arq[arq])
        ini, fim = folha(arq, pags[0]), folha(arq, pags[-1])
        if ini is None:
            confiavel = False
            nome = re.sub(r"\.pdf$", "", arq, flags=re.IGNORECASE)
            partes.append(f"{nome}, p. {pags[0]}" + (f"-{pags[-1]}" if pags[-1] != pags[0] else ""))
            continue
        faixa = _fmt_fl(ini) if ini == fim else f"{_fmt_fl(ini)}-{_fmt_fl(fim)}"
        if arq == principal or len(por_arq) == 1 and principal is None:
            partes.append(faixa)
        else:
            vol = volume(arq)
            partes.append(f"Vol. {vol}, fls. {faixa}" if vol else f"{arq}, fls. {faixa}")
    return "; ".join(partes), confiavel


def mes_extenso(mes: int, ano: int) -> str:
    return f"{MESES_EXTENSO[mes - 1]}/{ano}"


def data_extenso(d: date) -> str:
    return f"{d.day:02d} de {MESES_EXTENSO[d.month - 1]} de {d.year}"


# ─────────────────────────────────────────────────────────────────────────────
# Consenso
# ─────────────────────────────────────────────────────────────────────────────

class _Votos:
    def __init__(self):
        self.contagem: Counter = Counter()
        self.formas: Dict[Any, Counter] = {}
        self.local: Dict[Any, Tuple[str, str]] = {}

    def add(self, chave, forma: str, trecho: str, local: str, peso: int = 1):
        self.contagem[chave] += peso
        self.formas.setdefault(chave, Counter())[forma] += 1
        self.local.setdefault(chave, (trecho, local))

    def vencedor(self, minimo: int = 2):
        if not self.contagem:
            return None
        chave, n = self.contagem.most_common(1)[0]
        if n < minimo:
            return None
        trecho, local = self.local[chave]
        return {"chave": chave, "forma": self.formas[chave].most_common(1)[0][0], "ocorrencias": n,
                "trecho": trecho, "localizacao": local, "formas": self.formas[chave]}


def _trecho(texto: str, m: re.Match, raio: int = 50) -> str:
    return re.sub(r"\s+", " ", texto[max(0, m.start() - raio):m.end() + raio]).strip()


def _campo(valor, trecho: str, local: str, ocorrencias: int, **extra) -> Dict[str, Any]:
    return {"valor": valor, "trecho": trecho, "localizacao": local, "status": "confirmado",
            "origem": f"varredura do processo ({ocorrencias} ocorrência(s))", **extra}


def _paginas_norm(paginas) -> List[Tuple[Any, str]]:
    # "º"/"ª" contam como letra em \w e quebrariam os padrões "Nº"
    return [(p, norm(p.texto).replace("º", " ").replace("ª", " ")) for p in paginas]


# ─────────────────────────────────────────────────────────────────────────────
# Dados do convênio
# ─────────────────────────────────────────────────────────────────────────────

def _numero_convenio(pn, arquivos: List[str]):
    votos = _Votos()
    nos_arquivos = {d for a in arquivos for d in re.findall(r"\d{6,12}", a)}
    for p, t in pn:
        for m in NUM_CONV_RE.finditer(t):
            digitos = re.sub(r"\D", "", m.group(1))
            ano = int(m.group(2)) if len(m.group(2)) == 4 else 2000 + int(m.group(2))
            if not 1990 <= ano <= date.today().year + 1:
                continue
            votos.add((digitos, ano), f"{digitos}/{ano}", _trecho(t, m), p.ref, 6 if digitos in nos_arquivos else 1)
    return votos.vencedor(2)


def _vigencia_fim(pn, numero_digitos: Optional[str]):
    candidatos = []
    for p, t in pn:
        if numero_digitos and numero_digitos not in re.sub(r"\D", "", t):
            continue
        for rx in VIG_RE:
            for m in rx.finditer(t):
                antes = t[max(0, m.start() - 80):m.start()]
                if "CONTRAT" in antes:
                    continue
                d = parse_date(m.group(1))
                if d and 2000 <= d.year <= date.today().year:
                    candidatos.append((d, _trecho(t, m), p.ref))
    if not candidatos:
        return None
    return max(candidatos, key=lambda c: c[0])


def _interveniente(pn):
    votos = Counter()
    exemplo: Dict[str, Tuple[str, str]] = {}
    for p, t in pn:
        for nome, sigla in NOMES_SECRETARIAS.items():
            for m in re.finditer(nome, t):
                perto = t[max(0, m.start() - 120):m.start()]
                votos[sigla] += 5 if re.search(r"INTERVENI|INTERMEDIO", perto) else 2
                exemplo.setdefault(sigla, (_trecho(t, m), p.ref))
        for sigla in SECRETARIAS:
            for m in re.finditer(rf"\b{sigla}\b(?!\s*/\s*AGE)", t):
                votos[sigla] += 1
                exemplo.setdefault(sigla, (_trecho(t, m), p.ref))
    if not votos:
        return None
    sigla, n = votos.most_common(1)[0]
    if n < 3:
        return None
    return sigla, n, exemplo[sigla]


def _conta(pn):
    ag, cc = _Votos(), _Votos()
    bancos = Counter()
    for p, t in pn:
        for chave, nome in BANCOS:
            bancos[nome] += t.count(chave)
        peso_pag = 3 if re.search(r"CONVENIO|ESPECIFICA|VINCULADA", t) else 1
        for m in AG_RE.finditer(t):
            num = re.sub(r"\D", "", m.group(1)).lstrip("0") or "0"
            ag.add(f"{num}-{m.group(2)}", f"{num}-{m.group(2)}", _trecho(t, m), p.ref, peso_pag)
        for m in CONTA_RE.finditer(t):
            num = re.sub(r"\D", "", m.group(1)).lstrip("0") or "0"
            if len(num) < 3:
                continue
            cc.add(f"{num}-{m.group(2)}", f"{num}-{m.group(2)}", _trecho(t, m), p.ref, peso_pag)
    va, vc = ag.vencedor(3), cc.vencedor(3)
    if not va or not vc:
        return None
    banco = bancos.most_common(1)[0][0] if bancos and bancos.most_common(1)[0][1] else None
    return {"banco": banco, "agencia": va["chave"], "conta": vc["chave"], "trecho": vc["trecho"],
            "localizacao": vc["localizacao"], "ocorrencias": min(va["ocorrencias"], vc["ocorrencias"])}


def texto_conta(banco: Optional[str], agencia: Optional[str], conta: Optional[str]) -> str:
    return f"{banco or 'Banco ---'} / Ag: {agencia or '---'} / CC: {conta or '---'}"


def completar_convenio(convenio: Dict[str, Any], paginas, arquivos: List[str]) -> Dict[str, Any]:
    """Preenche/corrige os dados do convênio com o consenso do processo. Devolve o que foi alterado."""
    pn = _paginas_norm(paginas)
    alterados: Dict[str, Any] = {}

    def vazio(nome: str) -> bool:
        item = convenio.get(nome) or {}
        return item.get("valor") in (None, "") or item.get("status") != "confirmado"

    num = _numero_convenio(pn, arquivos)
    if num and vazio("numero_convenio"):
        convenio["numero_convenio"] = _campo(num["forma"], num["trecho"], num["localizacao"], num["ocorrencias"])
        alterados["numero_convenio"] = num["forma"]

    if vazio("vigencia_fim"):
        vig = _vigencia_fim(pn, num["chave"][0] if num else None)
        if vig:
            convenio["vigencia_fim"] = _campo(fmt_date(vig[0]), vig[1], vig[2], 1)
            alterados["vigencia_fim"] = fmt_date(vig[0])

    interv = _interveniente(pn)
    if interv and vazio("interveniente"):
        sigla, n, (trecho, local) = interv
        rotulo, nome, atual = SECRETARIAS[sigla]
        convenio["interveniente"] = _campo(rotulo, trecho, local, n, nome_completo=nome, sigla_atual=atual)
        alterados["interveniente"] = rotulo
    elif convenio.get("interveniente", {}).get("valor"):
        valor = norm(convenio["interveniente"]["valor"])
        sigla = next((s for s in SECRETARIAS if re.search(rf"\b{s}\b", valor)), None) or \
            next((s for n, s in NOMES_SECRETARIAS.items() if n in valor), None)
        if sigla:
            rotulo, nome, atual = SECRETARIAS[sigla]
            convenio["interveniente"].update(valor=rotulo, nome_completo=nome, sigla_atual=atual)

    conta = _conta(pn)
    if conta:
        atual = norm(str((convenio.get("banco_agencia_conta") or {}).get("valor") or ""))
        digitos_atual = re.sub(r"\D", "", atual)
        if vazio("banco_agencia_conta") or re.sub(r"\D", "", conta["conta"]) not in digitos_atual:
            texto = texto_conta(conta["banco"], conta["agencia"], conta["conta"])
            convenio["banco_agencia_conta"] = _campo(texto, conta["trecho"], conta["localizacao"], conta["ocorrencias"],
                                                     banco=conta["banco"], agencia=conta["agencia"], conta=conta["conta"])
            alterados["banco_agencia_conta"] = texto
    return alterados


# ─────────────────────────────────────────────────────────────────────────────
# Licitação / contrato / ordem de serviço
# ─────────────────────────────────────────────────────────────────────────────

def _data_doc(texto_norm: str) -> Optional[date]:
    datas = []
    for m in DATA_EXTENSO_RE.finditer(texto_norm):
        try:
            datas.append(date(int(m.group(3)), MESES_NUM[m.group(2)], int(m.group(1))))
        except ValueError:
            continue
    return datas[-1] if datas else None


def _somar_meses(d: date, meses: int) -> date:
    ano, mes = divmod(d.month - 1 + meses, 12)
    ano += d.year
    mes += 1
    for dia in (d.day, 30, 29, 28):
        try:
            return date(ano, mes, dia)
        except ValueError:
            continue
    return d


def varrer_licitacao(paginas, docs=None, total_notas: Optional[float] = None) -> Dict[str, Any]:
    pn = _paginas_norm(paginas)
    proc, mod, ctr, valor = _Votos(), _Votos(), _Votos(), _Votos()
    os_refs: List[Tuple[str, int]] = []
    vigencias: List[Tuple[date, str, str]] = []
    for p, t in pn:
        for m in PROC_RE.finditer(t):
            proc.add(int(m.group(1)), m.group(1) + (f"/{m.group(2)}" if m.group(2) else ""), _trecho(t, m), p.ref)
        for m in MOD_RE.finditer(t):
            tipo = MODALIDADES.get(m.group(1), m.group(1).title())
            mod.add((tipo, int(m.group(2)), m.group(3)), f"{m.group(2)}/{m.group(3)}", _trecho(t, m), p.ref)
        for m in CONTRATO_RE.finditer(t):
            ctr.add((int(m.group(1)), m.group(2)), f"{int(m.group(1))}/{m.group(2)}", _trecho(t, m), p.ref)
        for m in VALOR_CONTRATO_RE.finditer(t):
            v = parse_money(m.group(1))
            if v:
                valor.add(round(v, 2), m.group(1), _trecho(t, m), p.ref, 3 if total_notas and abs(v - total_notas) < 1 else 1)
        if OS_RE.search(t[:600]):
            os_refs.append((p.arquivo, p.pagina))
        m = PRORROGACAO_RE.search(t)
        if m:
            d = _data_doc(t)
            if d:
                vigencias.append((_somar_meses(d, int(m.group(1))), _trecho(t, m), p.ref))

    out: Dict[str, Any] = {"ordem_servico_paginas": os_refs}
    v = proc.vencedor(2)
    if v:
        com_ano = [f for f in v["formas"] if "/" in f]
        out["processo"] = (max(com_ano, key=lambda f: v["formas"][f]) if com_ano else v["forma"])
        out["processo_trecho"], out["processo_local"] = v["trecho"], v["localizacao"]
    v = mod.vencedor(2)
    if v:
        tipo, _, ano = v["chave"]
        # Edital costuma trazer o número com três dígitos ("009/2016"); prevalece se aparecer com frequência
        formas = v["formas"]
        longas = [f for f in formas if len(f.split("/")[0]) >= 3 and formas[f] >= 3]
        numero = longas[0] if longas else formas.most_common(1)[0][0]
        out["modalidade"] = f"{tipo} nº {numero}"
        out["modalidade_local"] = v["localizacao"]
    v = ctr.vencedor(2)
    if v:
        out["contrato"] = v["forma"]
        out["contrato_local"] = v["localizacao"]
    v = valor.vencedor(1)
    if v:
        out["valor_contrato"] = v["chave"]
        out["valor_local"] = v["localizacao"]
    if vigencias:
        fim = max(vigencias, key=lambda x: x[0])
        out["vigencia_contrato"] = fmt_date(fim[0])
        out["vigencia_local"] = fim[2]
        out["vigencia_trecho"] = fim[1]
    return out


def resumo_licitacao(lic: Dict[str, Any]) -> str:
    partes = [f"processo {lic.get('processo') or '—'}", lic.get("modalidade") or "modalidade —",
              f"contrato {lic.get('contrato') or '—'}", f"valor {fmt_money(lic.get('valor_contrato'))}",
              f"vigência {lic.get('vigencia_contrato') or '—'}"]
    return "; ".join(partes)
