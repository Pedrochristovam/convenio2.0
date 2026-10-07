"""
Cruzamentos determinísticos (itens 5, 11–14 e 17 do PROMPT-MESTRE).

Toda aritmética é feita aqui, nunca pela IA. Dados lidos por OCR podem conter
erros de leitura, por isso divergências viram ocorrências com fonte e pedido de
validação humana, e não conclusões.
"""

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from backend.analise_documental.classificador import Pagina
from backend.analise_documental.extrato_cc import como_movimentacoes, ler_extrato_cc, rotular, serializar, ultimo_periodo
from backend.analise_documental.extratores import fonte_campo, valor_campo
from backend.analise_documental.inventario import Documento
from backend.analise_documental.texto import (
    PENDENTE_HUMANO,
    find_dates,
    find_money,
    fmt_date,
    fmt_money,
    norm,
    parse_date,
    parse_money,
)
from backend.analise_documental.varredura import folha

CATEGORIAS = {
    "a": "Irregularidade formal sem dano identificado",
    "b": "Pendência documental",
    "c": "Inconsistência financeira",
    "d": "Irregularidade técnica",
    "e": "Indício de dano ao erário",
    "f": "Dano quantificável",
    "g": "Depende de manifestação técnica",
    "h": "Depende de manifestação jurídica",
    "i": "Depende de manifestação da Controladoria",
    "j": "Informação insuficiente para conclusão",
}

TOL = 0.05
RENDIMENTO_MAX_MENSAL = 0.03
MESES = {m: i for i, m in enumerate(
    ["JANEIRO", "FEVEREIRO", "MARCO", "ABRIL", "MAIO", "JUNHO", "JULHO",
     "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"], start=1)}
MES_REF_RE = re.compile(r"REFERENCIA\s*:?\s*([A-Z]{4,9})\s*/\s*(\d{4})")

INTERNO_RE = re.compile(r"APLIC|RESGATE|BB CP|RENDE|FUNDO|ADMIN|SUPREMO|SALDO")
TARIFA_RE = re.compile(r"TARIFA|\bTAR\b|CESTA|PACOTE")
DEVOLUCAO_RE = re.compile(r"FAZENDA|\bDAE\b|DEVOLU|RESTITU")
IMPOSTO_RE = re.compile(r"IMPOSTO|\bGPS\b|DARF|INSS|PREVIDENCIA")
# Lançamentos do razão contábil da prefeitura (não são movimentação bancária)
CONTABIL_RE = re.compile(r"^(SUB-?\s?EMPENHO|RETENCAO|ARRECADACAO|ARROCADACAO|DOCUMENTO EXTRA|EMPENHO|LIQUIDACAO|"
                         r"PAGAMENTO DE EMPENHO\s*$|N\.?\s?F\.?\s*\d)")
TIPOS_COMPROVANTE = ("COMPROVANTE_PAGAMENTO", "COPIA_CHEQUE", "RECIBO")
NF_ANO_NUM_RE = re.compile(r"(20\d{2})/0*(\d{1,6})(?!\d)")
NF_NUM_ANO_RE = re.compile(r"(?<!\d)0*(\d{1,6})/(20\d{2})(?!\d)")


def numero_nf(raw) -> Optional[str]:
    """Normaliza o número da NF para "NN/AAAA" (a IA às vezes devolve "2016/22" ou só o ano)."""
    if raw in (None, ""):
        return None
    s = re.sub(r"\s+", "", str(raw))
    m = NF_ANO_NUM_RE.search(s)
    if m:
        return f"{int(m.group(2)):02d}/{m.group(1)}"
    m = NF_NUM_ANO_RE.search(s)
    if m:
        return f"{int(m.group(1)):02d}/{m.group(2)}"
    m = re.fullmatch(r"\D{0,4}0*(\d{1,6})", s)
    if m and not re.fullmatch(r"(19|20)\d{2}", m.group(1)):
        return f"{int(m.group(1)):02d}"
    return None


@dataclass
class Ocorrencia:
    categoria: str
    item: str
    titulo: str
    descricao: str
    valor: Optional[float] = None
    fontes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["categoria_nome"] = CATEGORIAS[self.categoria]
        return d


@dataclass
class Evidencia:
    valor: float
    data: Optional[date]
    descricao: str
    tipo: str  # C | D
    origem: str  # extrato | comprovante
    classe: str  # pagamento | interno | tarifa | devolucao | imposto | credito | contabil
    localizacao: str
    arquivo: str = ""
    pagina: int = 0

    def to_dict(self):
        return {**asdict(self), "data": fmt_date(self.data)}


def _eq(a: Optional[float], b: Optional[float], tol: float = TOL) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol


def _mes_ref(texto: str) -> Optional[Tuple[int, int]]:
    m = MES_REF_RE.search(norm(texto))
    if m and m.group(1) in MESES:
        return int(m.group(2)), MESES[m.group(1)]
    return None


def _serie_resumos(resumos_por_arquivo: Dict[str, Dict[int, Dict]], paginas_por_ref: Dict[Tuple[str, int], Pagina]) -> List[Dict]:
    serie, vistos = [], set()
    for arquivo, resumos in resumos_por_arquivo.items():
        for pagina, dados in sorted(resumos.items()):
            pg = paginas_por_ref.get((arquivo, int(pagina)))
            mes = _mes_ref(pg.texto) if pg else None
            chave = mes or (arquivo, pagina)
            if chave in vistos:
                continue
            vistos.add(chave)
            c = dados.get("campos", {})
            rl = c.get("rendimento_liquido")
            if rl is None and c.get("rendimento_bruto") is not None:
                rl = (c.get("rendimento_bruto") or 0) - (c.get("imposto_renda") or 0) - (c.get("iof") or 0)
            base = max(abs(c.get(k) or 0) for k in ("saldo_anterior", "saldo_atual", "aplicacoes"))
            serie.append({
                "mes": f"{mes[1]:02d}/{mes[0]}" if mes else None,
                "ordem": mes or (9999, 0),
                "localizacao": f"{arquivo}, p. {pagina}",
                "saldo_anterior": c.get("saldo_anterior"),
                "aplicacoes": c.get("aplicacoes"),
                "resgates": c.get("resgates"),
                "rendimento_liquido": rl,
                "saldo_atual": c.get("saldo_atual"),
                # Fundos de curto prazo não rendem mais que ~3% ao mês: acima disso é erro de leitura
                "leitura_suspeita": bool(rl and base and abs(rl) > RENDIMENTO_MAX_MENSAL * base),
            })
    serie.sort(key=lambda s: s["ordem"])
    for s in serie:
        s.pop("ordem")
    return serie


def _evidencias(cc_por_arquivo: Dict[str, List[Dict]], paginas_por_ref, tipo_por_ref, teto: float) -> List[Evidencia]:
    out, vistos = [], set()
    for arquivo, linhas in cc_por_arquivo.items():
        for tx in linhas:
            valor = tx.get("valor")
            if valor is None or not (0.01 <= float(valor) <= teto):
                continue
            hist = norm(tx.get("historico") or "")
            if "SALDO" in hist and "ANTERIOR" in hist:
                continue
            data = parse_date(tx.get("data_movimento") or tx.get("data_balancete"))
            tipo = (tx.get("valor_tipo") or "D").upper()[:1]
            chave = (data, round(float(valor), 2), tipo)
            if chave in vistos:
                continue
            vistos.add(chave)
            ref = (arquivo, int(tx.get("pagina") or 0))
            tipo_doc = tipo_por_ref.get(ref, "")
            origem = "extrato" if tipo_doc in ("EXTRATOS", "EXTRATO_CC", "EXTRATO_APLICACAO") else "comprovante"
            # Num comprovante a página inteira descreve um único pagamento (ex.: "Convenio GPS")
            contexto = hist
            if origem == "comprovante" and ref in paginas_por_ref:
                contexto = f"{hist} {norm(paginas_por_ref[ref].texto)}"
            if CONTABIL_RE.search(hist):
                classe = "contabil"
            elif INTERNO_RE.search(hist):
                classe = "interno"
            elif DEVOLUCAO_RE.search(contexto):
                classe = "devolucao"
            elif TARIFA_RE.search(hist):
                classe = "tarifa"
            elif IMPOSTO_RE.search(contexto):
                classe = "imposto"
            else:
                classe = "pagamento" if tipo == "D" else "credito"
            out.append(Evidencia(float(valor), data, (tx.get("historico") or "")[:90], tipo, origem, classe,
                                 f"{arquivo}, p. {tx.get('pagina')}", arquivo, int(tx.get("pagina") or 0)))
    return out


def _volume_principal(docs: List[Documento]) -> Optional[str]:
    """Volume da prestação de contas: é a ele que as folhas citadas na AD se referem."""
    arquivos = {p.arquivo for d in docs for p in d.paginas}
    for a in sorted(arquivos):
        if "PRESTACAO DE CONTAS" in norm(a.replace("_", " ")):
            return a
    for d in docs:
        if d.tipo == "OFICIO" and not d.duplicado_de and d.paginas:
            return d.paginas[0].arquivo
    contagem: Dict[str, int] = {}
    for d in docs:
        if d.tipo == "NOTA_FISCAL":
            contagem[d.paginas[0].arquivo] = contagem.get(d.paginas[0].arquivo, 0) + 1
    return max(contagem, key=contagem.get) if contagem else None


def _ref(arquivo: str, pagina: int) -> Dict[str, Any]:
    return {"arquivo": arquivo, "pagina": pagina, "folha": folha(arquivo, pagina), "localizacao": f"{arquivo}, p. {pagina}"}


def _agrupar_notas(docs: List[Documento], principal: Optional[str]):
    """Cópias da mesma NF (ex.: Volume 3 'Documentos Excedentes') viram um único item."""
    itens = []
    for d in docs:
        e = d.extracao or {}
        itens.append({
            "doc": d, "e": e, "bruto": valor_campo(e, "valor_bruto"),
            "numero": numero_nf(valor_campo(e, "numero")),
            "emissao": parse_date(valor_campo(e, "data_emissao")),
            "emitente": valor_campo(e, "emitente"),
            "confirmados": sum(1 for v in e.values() if isinstance(v, dict) and v.get("status") == "confirmado"),
        })
    grupos: List[List[Dict]] = []
    for it in sorted(itens, key=lambda x: (x["doc"].paginas[0].arquivo != principal, -x["confirmados"])):
        if it["bruto"] is None:
            continue
        for g in grupos:
            a = g[0]
            if not _eq(a["bruto"], it["bruto"], 0.011):
                continue
            if a["numero"] and it["numero"] and a["numero"] != it["numero"]:
                continue
            if a["emissao"] and it["emissao"] and abs((a["emissao"] - it["emissao"]).days) > 5:
                continue
            g.append(it)
            break
        else:
            grupos.append([it])
    sem_valor = [it for it in itens if it["bruto"] is None]
    return grupos, sem_valor


def _primeiro(grupo: List[Dict], campo: str):
    for it in grupo:
        v = valor_campo(it["e"], campo)
        if v not in (None, ""):
            return v
    return None


def _subconjunto(valores: List[Tuple[float, Any]], alvo: float, maximo: int = 4):
    from itertools import combinations
    for n in range(1, maximo + 1):
        for combo in combinations(valores, n):
            if _eq(sum(v for v, _ in combo), alvo, 0.02):
                return list(combo)
    return None


VALOR_CONHECIMENTO_RE = re.compile(r"VALOR\s*R\$\s*(\d{1,3}(?:[.\s]\d{3})*,\s?\d{2})")


def _conhecimentos_receita(docs: List[Documento]) -> List[Dict[str, Any]]:
    """Lançamentos de receita da prefeitura: repasses recebidos e rendimentos recolhidos."""
    itens = []
    for d in docs:
        texto = norm(d.texto)
        m = VALOR_CONHECIMENTO_RE.search(texto)
        datas = find_dates(d.texto)
        if re.search(r"TRANSFERENCIAS? DE CONVENIO", texto):
            natureza = "repasse"
        elif re.search(r"REMUNERACAO DE (OUTROS )?DEPOSITOS", texto):
            natureza = "rendimento"
        else:
            natureza = "outra"
        itens.append({
            "documento": d.id,
            "localizacao": d.localizacao,
            "valor": parse_money(m.group(1)) if m else None,
            # As primeiras datas são o período do relatório; a última é a do lançamento
            "data": fmt_date(datas[-1]) if datas else None,
            "natureza": natureza,
        })
    return itens


def _periodo_texto(texto: Optional[str]) -> Tuple[Optional[date], Optional[date]]:
    ds = find_dates(texto or "")
    return (ds[0], ds[-1]) if len(ds) >= 2 else (None, None)


def executar_cruzamentos(
    docs: List[Documento],
    paginas: List[Pagina],
    convenio: Dict[str, Any],
    resumos_por_arquivo: Dict[str, Dict[int, Dict]],
    cc_por_arquivo: Dict[str, List[Dict]],
) -> Dict[str, Any]:
    ocorrencias: List[Ocorrencia] = []
    paginas_por_ref = {(p.arquivo, p.pagina): p for p in paginas}
    tipo_por_ref = {(p.arquivo, p.pagina): d.tipo for d in docs for p in d.paginas}
    ativos = [d for d in docs if not d.duplicado_de]
    por_tipo: Dict[str, List[Documento]] = {}
    for d in ativos:
        por_tipo.setdefault(d.tipo, []).append(d)

    execucao = (por_tipo.get("EXECUCAO_FISICO_FINANCEIRA") or [None])[0]
    exe = execucao.extracao if execucao else {}

    # ── Valores pactuados e declarados ──
    def pick(nome_conv: str, nome_exe: Optional[str] = None):
        v = valor_campo(convenio, nome_conv)
        if v is not None:
            return v, fonte_campo(convenio, nome_conv), "convênio"
        if nome_exe and exe:
            v = valor_campo(exe, nome_exe)
            if v is not None:
                return v, fonte_campo(exe, nome_exe), "demonstrativo de execução"
        return None, None, None

    repasse, repasse_fonte, repasse_origem = pick("valor_concedente", "valor_concedente")
    contrap_pact, contrap_fonte, _ = pick("valor_contrapartida")
    contrap_exec = valor_campo(exe, "valor_contrapartida") if exe else None
    total_pact = valor_campo(convenio, "valor_total")

    vig_ini = parse_date(valor_campo(convenio, "vigencia_inicio"))
    vig_fim = parse_date(valor_campo(convenio, "vigencia_fim"))
    vig_fonte = fonte_campo(convenio, "vigencia_fim")
    assinatura = parse_date(valor_campo(convenio, "data_assinatura"))
    # Guias de conferência costumam trazer "Vigência: <data final original>" — não é data de início
    if vig_ini and ((vig_fim and vig_ini >= vig_fim) or (assinatura and (vig_ini - assinatura).days > 180)):
        ocorrencias.append(Ocorrencia(
            "j", "Prazo da prestação de contas", "Início de vigência inconsistente",
            f"Data lida como início da vigência ({fmt_date(vig_ini)}) é incompatível com a assinatura "
            f"({fmt_date(assinatura) if assinatura else '—'}) ou com o fim ({fmt_date(vig_fim) if vig_fim else '—'}); "
            f"provavelmente é o término original antes dos aditivos. {PENDENTE_HUMANO}",
            None, [fonte_campo(convenio, "vigencia_inicio") or ""]))
        vig_ini = None
    if (not vig_ini or not vig_fim) and exe and valor_campo(exe, "periodo"):
        a, b = _periodo_texto(valor_campo(exe, "periodo"))
        vig_ini, vig_fim = vig_ini or a, vig_fim or b
        vig_fonte = vig_fonte or fonte_campo(exe, "periodo")

    teto = max(filter(None, [total_pact, repasse, 1_000_000.0])) * 2
    principal = _volume_principal(docs)
    linhas_extrato = ler_extrato_cc(paginas, principal)
    if linhas_extrato:
        lidas = {(x["arquivo"], x["pagina"]) for x in linhas_extrato}
        cc_por_arquivo = {a: [t for t in ls if (a, int(t.get("pagina") or 0)) not in lidas] for a, ls in cc_por_arquivo.items()}
        for a, ls in como_movimentacoes(linhas_extrato).items():
            cc_por_arquivo[a] = ls + cc_por_arquivo.get(a, [])
    evidencias = _evidencias(cc_por_arquivo, paginas_por_ref, tipo_por_ref, teto)
    pagamentos = [e for e in evidencias if e.tipo == "D" and e.classe == "pagamento"]

    # ── Extratos de aplicação: continuidade e rendimentos ──
    serie = _serie_resumos(resumos_por_arquivo, paginas_por_ref)
    quebras = []
    datados = [s for s in serie if s["mes"]]
    for prev, cur in zip(datados, datados[1:]):
        if prev["saldo_atual"] is None or cur["saldo_anterior"] is None:
            continue
        if not _eq(prev["saldo_atual"], cur["saldo_anterior"]):
            quebras.append((prev, cur))
            # O banco garante a continuidade entre meses: divergência indica leitura errada ou extrato faltante
            ocorrencias.append(Ocorrencia(
                "j", "Aplicações/rendimentos", "Continuidade entre extratos não confirmada",
                f"Saldo atual de {prev['mes']} ({fmt_money(prev['saldo_atual'])}) difere do saldo anterior de "
                f"{cur['mes']} ({fmt_money(cur['saldo_anterior'])}). Provável erro de leitura do OCR ou extrato "
                f"faltante; conferir no documento. {PENDENTE_HUMANO}",
                round(cur["saldo_anterior"] - prev["saldo_atual"], 2), [prev["localizacao"], cur["localizacao"]]))
    meses = [(int(s["mes"][3:]), int(s["mes"][:2])) for s in serie if s["mes"]]
    lacunas = []
    for (y1, m1), (y2, m2) in zip(meses, meses[1:]):
        diff = (y2 - y1) * 12 + (m2 - m1)
        if diff > 1:
            lacunas.append(f"{m1:02d}/{y1} → {m2:02d}/{y2}")
    if lacunas:
        ocorrencias.append(Ocorrencia(
            "b", "Aplicações/rendimentos", "Meses sem extrato de aplicação",
            f"Não foram localizados extratos de aplicação entre: {', '.join(lacunas)}.", None, []))
    suspeitos = [s for s in serie if s["leitura_suspeita"]]
    if suspeitos:
        ocorrencias.append(Ocorrencia(
            "j", "Aplicações/rendimentos", "Leitura suspeita de extrato de aplicação",
            "Rendimento mensal incompatível com o saldo (possível erro de OCR), excluído da soma: "
            + "; ".join(f"{s['mes'] or s['localizacao']} = {fmt_money(s['rendimento_liquido'])}" for s in suspeitos)
            + f". {PENDENTE_HUMANO}", None, [s["localizacao"] for s in suspeitos]))
    rend_extratos = round(sum(s["rendimento_liquido"] or 0 for s in serie if not s["leitura_suspeita"]), 2) if serie else None

    rend_declarado = valor_campo(exe, "rendimentos_aplicacao") if exe else None
    if rend_declarado is not None and rend_extratos is not None and abs(rend_declarado - rend_extratos) > 1.0:
        ocorrencias.append(Ocorrencia(
            "c", "Aplicações/rendimentos", "ALERTA DE DIVERGÊNCIA – rendimentos",
            f"Rendimentos declarados no demonstrativo: {fmt_money(rend_declarado)}; soma dos rendimentos líquidos "
            f"lidos nos extratos ({len(serie)} meses): {fmt_money(rend_extratos)}. Diferença de "
            f"{fmt_money(rend_declarado - rend_extratos)}. {PENDENTE_HUMANO}",
            round(rend_declarado - rend_extratos, 2), [fonte_campo(exe, "rendimentos_aplicacao") or execucao.localizacao]))

    # ── Conhecimentos de receita (contabilidade da convenente) ──
    conhecimentos = _conhecimentos_receita(por_tipo.get("CONHECIMENTO_RECEITA", []))
    rec_repasses = round(sum(c["valor"] or 0 for c in conhecimentos if c["natureza"] == "repasse"), 2)
    rec_rendimentos = round(sum(c["valor"] or 0 for c in conhecimentos if c["natureza"] == "rendimento"), 2)
    locs_conhec = [c["localizacao"] for c in conhecimentos][:6]
    if conhecimentos and repasse is not None and rec_repasses and not _eq(rec_repasses, repasse):
        ocorrencias.append(Ocorrencia(
            "c", "Movimentação bancária", "Repasses contabilizados divergem do valor do concedente",
            f"Soma dos conhecimentos de receita de transferência de convênio: {fmt_money(rec_repasses)}; "
            f"valor do concedente: {fmt_money(repasse)}. Pode faltar parcela ou haver erro de leitura. {PENDENTE_HUMANO}",
            round(repasse - rec_repasses, 2), locs_conhec))
    if conhecimentos and rend_declarado is not None and rec_rendimentos and abs(rend_declarado - rec_rendimentos) > 1.0:
        ocorrencias.append(Ocorrencia(
            "c", "Aplicações/rendimentos", "ALERTA DE DIVERGÊNCIA – rendimentos contabilizados × declarados",
            f"Rendimentos recolhidos como receita (conhecimentos de receita): {fmt_money(rec_rendimentos)}; "
            f"declarados no demonstrativo: {fmt_money(rend_declarado)}. {PENDENTE_HUMANO}",
            round(rend_declarado - rec_rendimentos, 2), locs_conhec))

    # ── Aritmética do demonstrativo ──
    demonstrativo = None
    if exe:
        partes = {k: valor_campo(exe, k) for k in ("valor_concedente", "valor_contrapartida", "rendimentos_aplicacao", "valor_total")}
        if all(partes[k] is not None for k in ("valor_concedente", "valor_contrapartida", "valor_total")):
            soma = round(partes["valor_concedente"] + partes["valor_contrapartida"] + (partes["rendimentos_aplicacao"] or 0), 2)
            ok = _eq(soma, partes["valor_total"])
            demonstrativo = {**partes, "soma_calculada": soma, "confere": ok, "localizacao": execucao.localizacao}
            if not ok:
                diferenca = round(partes["valor_total"] - soma, 2)
                dicas = [
                    f"a diferença ({fmt_money(diferenca)}) é igual ao valor do DAE de devolução {d.id} ({d.localizacao})"
                    for d in por_tipo.get("DAE_DEVOLUCAO", [])
                    if _eq(abs(diferenca), valor_campo(d.extracao or {}, "valor"))
                ]
                ocorrencias.append(Ocorrencia(
                    "c", "Irregularidades financeiras", "Total do demonstrativo não confere",
                    f"Concedente + contrapartida + rendimentos = {fmt_money(soma)}, mas o total declarado é "
                    f"{fmt_money(partes['valor_total'])}." + (f" Observação: {'; '.join(dicas)}." if dicas else ""),
                    diferenca, [execucao.localizacao]))

    # ── Contrapartida e proporcionalidade ──
    contrapartida = None
    if contrap_pact is not None or contrap_exec is not None:
        base_total = (repasse or 0) + (contrap_pact or contrap_exec or 0)
        contrapartida = {
            "pactuada": contrap_pact,
            "pactuada_fonte": contrap_fonte,
            "declarada_executada": contrap_exec,
            "percentual_concedente": round(100 * repasse / base_total, 4) if repasse and base_total else None,
            "percentual_convenente": round(100 * (contrap_pact or contrap_exec) / base_total, 4) if base_total else None,
            "memoria_calculo": (
                f"Base = repasse {fmt_money(repasse)} + contrapartida {fmt_money(contrap_pact or contrap_exec)} = {fmt_money(base_total)}"
                if base_total else None
            ),
        }
        if contrap_pact is not None and contrap_exec is not None and contrap_exec + TOL < contrap_pact:
            ocorrencias.append(Ocorrencia(
                "c", "Contrapartida", "Contrapartida declarada inferior à pactuada",
                f"Pactuada {fmt_money(contrap_pact)}; declarada {fmt_money(contrap_exec)}. "
                "Eventual proporcionalidade depende do regime jurídico.", round(contrap_pact - contrap_exec, 2),
                [x for x in (contrap_fonte, execucao.localizacao if execucao else None) if x]))

    # ── Repasse × extrato ──
    creditos = [e for e in evidencias if e.tipo == "C" and e.classe == "credito"]
    repasse_localizado = [e for e in creditos if _eq(e.valor, repasse)] if repasse else []
    if repasse is None:
        aplicacoes_serie = []
    else:
        aplicacoes_serie = [s for s in serie if _eq(s["aplicacoes"], repasse)]

    # ── Notas fiscais × pagamentos ──
    paginas_comprov = sorted(
        [p for t in TIPOS_COMPROVANTE for d in por_tipo.get(t, []) for p in d.paginas],
        key=lambda p: (p.arquivo != principal, p.arquivo, p.pagina))
    valores_pagina = {(p.arquivo, p.pagina): find_money(p.texto) for p in paginas_comprov}
    paginas_guia = [p for d in por_tipo.get("GUIA_RECOLHIMENTO", []) for p in d.paginas]
    valores_guia = {(p.arquivo, p.pagina): find_money(p.texto) for p in paginas_guia}

    def pagina_com_valor(valor: Optional[float], onde: Dict) -> Optional[Dict[str, Any]]:
        if not valor:
            return None
        for (arq, pag), vals in onde.items():
            if any(_eq(v, valor, 0.011) for v in vals):
                return _ref(arq, pag)
        return None

    # A data do pagamento é a do débito no extrato (o comprovante pode trazer a data do agendamento)
    pool = sorted(
        [(i, ev) for i, ev in enumerate(evidencias) if ev.tipo == "D" and ev.classe in ("pagamento", "imposto", "devolucao")],
        key=lambda x: (x[1].arquivo != principal, x[1].origem != "extrato"))
    usados: set = set()

    def marcar(ev: Evidencia):
        for i, x in pool:
            if _eq(x.valor, ev.valor, 0.011) and (not x.data or not ev.data or abs((x.data - ev.data).days) <= 7):
                usados.add(i)

    def achar(valores: List[float], referencia: Optional[date], antes: int, depois: int):
        for v in valores:
            for i, ev in pool:
                if i in usados or not _eq(ev.valor, v, 0.011):
                    continue
                if referencia and ev.data and not (-antes <= (ev.data - referencia).days <= depois):
                    continue
                return ev
        return None

    grupos, notas_sem_valor = _agrupar_notas(por_tipo.get("NOTA_FISCAL", []), principal)
    retencoes_lidas = {round(v, 2) for g in grupos for it in g
                       for v in (valor_campo(it["e"], k) for k in ("retencao_inss", "retencao_iss", "retencao_ir")) if v}
    notas_descartadas = []
    validos = []
    for g in grupos:
        # Guia/empenho de retenção classificado como NF: sem emitente e com valor igual a uma retenção
        if not any(it["emitente"] for it in g) and round(g[0]["bruto"], 2) in retencoes_lidas:
            notas_descartadas.append({"documentos": [it["doc"].id for it in g], "valor": g[0]["bruto"],
                                      "motivo": "valor igual a uma retenção de outra NF e sem emitente (guia/empenho)"})
            continue
        validos.append(g)
    validos.sort(key=lambda g: (min((it["emissao"] for it in g if it["emissao"]), default=date.max)))

    notas = []
    for g in validos:
        rep = g[0]
        d = rep["doc"]
        bruto = rep["bruto"]
        inss = _primeiro(g, "retencao_inss") or 0.0
        iss = _primeiro(g, "retencao_iss") or 0.0
        ir = _primeiro(g, "retencao_ir") or 0.0
        liquido_ext = _primeiro(g, "valor_liquido")
        emissao = next((it["emissao"] for it in g if it["emissao"]), None)
        numero = next((it["numero"] for it in g if it["numero"]), None)
        candidatos = []
        for v in (bruto - inss - iss - ir, bruto - inss - iss, liquido_ext, bruto - inss, bruto):
            if v and v > 0 and not any(_eq(v, c, 0.011) for c in candidatos):
                candidatos.append(round(v, 2))
        pag = achar(candidatos, emissao, 5, 180)
        if not pag and emissao:
            faixa = [(i, ev) for i, ev in pool if i not in usados and ev.data
                     and 0.85 * bruto <= ev.valor <= bruto - inss - iss + 0.01 and 0 <= (ev.data - emissao).days <= 120]
            if faixa:
                pag = min(faixa, key=lambda x: (x[1].data - emissao).days)[1]
        pago = pag.valor if pag else None
        if pag:
            marcar(pag)
        ret_fed = ir
        if pago is not None and (inss or iss):
            # O líquido pago define a retenção federal; o IR lido isoladamente na NF costuma vir errado
            resto = round(bruto - inss - iss - pago, 2)
            if -0.01 <= resto < 0.1 * bruto:
                ret_fed = max(resto, 0.0)
        comprov_pag = (_ref(pag.arquivo, pag.pagina) if pag and pag.origem == "comprovante" else None) or \
            pagina_com_valor(pago or candidatos[0], valores_pagina)

        tributos = None
        total_trib = round(inss + iss + ret_fed, 2)
        if total_trib > 0.01:
            ev_trib = achar([total_trib], pag.data if pag and pag.data else emissao, 10, 40 if pag else 180)
            if ev_trib:
                marcar(ev_trib)
            comprov_trib = (_ref(ev_trib.arquivo, ev_trib.pagina) if ev_trib and ev_trib.origem == "comprovante" else None) or \
                pagina_com_valor(total_trib, valores_pagina)
            tributos = {
                "valor": total_trib,
                "data": fmt_date(ev_trib.data) if ev_trib and ev_trib.data else None,
                "extrato": ev_trib.localizacao if ev_trib else None,
                "comprovante": comprov_trib,
            }
        guias = {nome: pagina_com_valor(v, valores_guia) for nome, v in (("inss", inss), ("iss", iss), ("ret_fed", ret_fed)) if v}
        nf = {
            "documento": d.id,
            "documentos": [it["doc"].id for it in g],
            "copias": [it["doc"].localizacao for it in g[1:]],
            "localizacao": d.localizacao,
            "pagina_ref": _ref(d.paginas[0].arquivo, d.paginas[0].pagina),
            "numero": numero,
            "numero_lido": valor_campo(rep["e"], "numero"),
            "data_emissao": fmt_date(emissao) if emissao else None,
            "emitente": _primeiro(g, "emitente"),
            "cnpj": _primeiro(g, "cnpj_emitente"),
            "valor_bruto": bruto,
            "retencao_inss": inss,
            "retencao_iss": iss,
            "retencao_ret_fed": ret_fed,
            "retencoes": round(inss + iss + ret_fed, 2),
            "valor_liquido": pago if pago is not None else (liquido_ext or candidatos[0]),
            "pagamento": pag.to_dict() if pag else None,
            "pagamento_comprovante": comprov_pag,
            "tributos": tributos,
            "guias": guias,
            "guias_faltantes": [k for k, v in guias.items() if not v],
            "campos_nao_confirmados": [k for k, v in rep["e"].items()
                                       if isinstance(v, dict) and v.get("status") not in ("confirmado", "nao_identificado")],
        }
        notas.append(nf)
        rotulo = numero or d.id
        if not pag:
            ocorrencias.append(Ocorrencia(
                "b", "Comprovantes de despesas", f"Pagamento da NF {rotulo} não localizado",
                f"Nenhum débito/comprovante de {fmt_money(candidatos[0])} (líquido de retenções) ou {fmt_money(bruto)} "
                "(bruto) foi encontrado nos extratos/comprovantes lidos. Pode haver pagamento parcelado ou erro de leitura.",
                bruto, [d.localizacao]))
        if emissao and vig_ini and vig_fim and not (vig_ini <= emissao <= vig_fim):
            ocorrencias.append(Ocorrencia(
                "c", "Comprovantes de despesas", f"NF {rotulo} emitida fora da vigência",
                f"Emissão em {fmt_date(emissao)}; vigência {fmt_date(vig_ini)} a {fmt_date(vig_fim)}. {PENDENTE_HUMANO}",
                bruto, [d.localizacao] + ([vig_fonte] if vig_fonte else [])))

    numeros_ok = {n["numero"] for n in notas if n["numero"]}
    nao_lidas = [it for it in notas_sem_valor if not (it["numero"] and it["numero"] in numeros_ok)]
    if nao_lidas:
        ocorrencias.append(Ocorrencia(
            "j", "Comprovantes de despesas", "Notas fiscais com valor não identificado",
            f"{len(nao_lidas)} página(s) classificadas como NF sem valor legível (podem ser cópias ou guias): "
            + "; ".join(it["doc"].localizacao for it in nao_lidas[:8]) + f". {PENDENTE_HUMANO}",
            None, [it["doc"].localizacao for it in nao_lidas[:8]]))
    valores_nf = [n["valor_bruto"] for n in notas if n["valor_bruto"] is not None]
    total_nf = round(sum(valores_nf), 2) if valores_nf else None
    sem_guia = [n for n in notas if n["guias_faltantes"]]

    sem_nf = [ev for i, ev in pool if i not in usados and ev.classe == "pagamento"
              and ev.origem == "comprovante" and (principal is None or ev.arquivo == principal)]
    if sem_nf:
        ocorrencias.append(Ocorrencia(
            "j", "Movimentação bancária", "Débitos sem nota fiscal correspondente identificada",
            "Débitos lidos em comprovantes do volume da prestação de contas que não casaram com NF, tributos ou "
            "devolução: " + "; ".join(f"{fmt_money(ev.valor)} em {fmt_date(ev.data)} ({ev.localizacao})" for ev in sem_nf[:10])
            + f". Podem ser leituras repetidas do OCR. {PENDENTE_HUMANO}",
            None, [ev.localizacao for ev in sem_nf[:10]]))

    # ── Parcelas do repasse ──
    parcelas_repasse = None
    if repasse:
        creditos_val: Dict[float, Any] = {}
        for e in evidencias:
            if e.tipo == "C" and e.classe == "credito" and 0.05 * repasse <= e.valor <= repasse + TOL:
                creditos_val.setdefault(round(e.valor, 2), e)
        for c in conhecimentos:
            if c["natureza"] == "repasse" and c["valor"]:
                creditos_val.setdefault(round(c["valor"], 2), None)
        combo = _subconjunto(sorted(creditos_val.items(), key=lambda x: -x[0])[:25], repasse)
        if not combo:
            # Comprovantes do concedente: a transferência à prefeitura aparece como débito
            transf = {round(e.valor, 2): e for e in evidencias
                      if e.tipo == "D" and re.search(r"TRANSFER\w*\s+(PARA|A)\s+(A\s+)?PREFEITURA", norm(e.descricao))
                      and 0.05 * repasse <= e.valor <= repasse + TOL}
            combo = _subconjunto(sorted(transf.items(), key=lambda x: -x[0])[:25], repasse)
        if combo:
            parcelas_repasse = [{"valor": v, "data": fmt_date(e.data) if e and e.data else None,
                                 "localizacao": e.localizacao if e else None} for v, e in combo]
            parcelas_repasse.sort(key=lambda x: (parse_date(x["data"]) or date.max))

    # ── Cobertura dos extratos ──
    tipo_pagina = {(p.arquivo, p.pagina): p.tipo for p in paginas}
    linhas_cc = [ev for ev in evidencias if ev.origem == "extrato" and ev.data and tipo_pagina.get((ev.arquivo, ev.pagina)) == "EXTRATO_CC"]
    ultimo_cc = None
    datas_cc = []
    for arquivo, linhas in cc_por_arquivo.items():
        for tx in linhas:
            if tipo_pagina.get((arquivo, int(tx.get("pagina") or 0))) != "EXTRATO_CC":
                continue
            dt = parse_date(tx.get("data_movimento") or tx.get("data_balancete"))
            if dt:
                datas_cc.append((dt, tx, arquivo))
    if datas_cc:
        dt, tx, arquivo = max(datas_cc, key=lambda x: x[0])
        saldo_tx = [t for d_, t, _ in datas_cc if d_ == dt and "SALDO" in norm(t.get("historico") or "")]
        ultimo_cc = {"data": fmt_date(dt), "mes": dt.month, "ano": dt.year,
                     "saldo": float(saldo_tx[-1]["valor"]) if saldo_tx and saldo_tx[-1].get("valor") is not None else None,
                     "localizacao": f"{arquivo}, p. {tx.get('pagina')}"}
    elif linhas_cc:
        ev = max(linhas_cc, key=lambda e: e.data)
        ultimo_cc = {"data": fmt_date(ev.data), "mes": ev.data.month, "ano": ev.data.year, "saldo": None, "localizacao": ev.localizacao}
    periodo = ultimo_periodo(paginas, principal)
    if periodo and (not ultimo_cc or (periodo["ano"], periodo["mes"]) > (ultimo_cc["ano"], ultimo_cc["mes"])):
        ultimo_cc = {"data": f"{periodo['mes']:02d}/{periodo['ano']}", "mes": periodo["mes"], "ano": periodo["ano"],
                     "saldo": None, "localizacao": f"{periodo['arquivo']}, p. {periodo['pagina']}"}

    produtos: Dict[str, Optional[Tuple[int, int]]] = {}
    for p in paginas:
        if p.tipo == "EXTRATO_APLICACAO" and tipo_por_ref.get((p.arquivo, p.pagina)) in ("EXTRATOS", "EXTRATO_APLICACAO"):
            t = norm(p.texto)
            if "SUPREMO" in t:
                nome = "Serviço Público Supremo"
            elif "POUPAN" in t:
                nome = "Poupança Ouro" if "OURO" in t else "Poupança"
            elif "RENDE FACIL" in t:
                nome = "BB Rende Fácil"
            else:
                continue
            mes = _mes_ref(p.texto)
            if not mes:
                ds = find_dates(p.texto)
                mes = (max(ds).year, max(ds).month) if ds else None
            atual = produtos.get(nome)
            produtos[nome] = max(filter(None, [atual, mes])) if (atual or mes) else None
    aplicacoes_produtos = [{"produto": k, "ultimo_mes": f"{v[1]:02d}/{v[0]}" if v else None} for k, v in produtos.items()]

    if vig_fim:
        for ev in pagamentos:
            if ev.data and ev.data > vig_fim:
                ocorrencias.append(Ocorrencia(
                    "c", "Movimentação bancária", "Pagamento após o fim da vigência",
                    f"{fmt_money(ev.valor)} em {fmt_date(ev.data)} ({ev.descricao}); vigência até {fmt_date(vig_fim)}. {PENDENTE_HUMANO}",
                    ev.valor, [ev.localizacao]))

    # ── Devoluções ──
    devolucoes = []
    for d in por_tipo.get("DAE_DEVOLUCAO", []):
        e = d.extracao or {}
        valor = valor_campo(e, "valor")
        if valor is None:
            vals = find_money(d.texto)
            valor = max(vals) if vals else None
        if valor is not None and valor <= 0.01:
            valor = None
        comprov = [ev for ev in evidencias if ev.tipo == "D" and _eq(ev.valor, valor)] if valor else []
        devolucoes.append({
            "documento": d.id,
            "localizacao": d.localizacao,
            "valor": valor,
            "data": valor_campo(e, "data_vencimento_ou_pagamento"),
            "natureza": valor_campo(e, "natureza"),
            "comprovacao": [c.to_dict() for c in comprov],
            "comprovada": bool(comprov),
        })
        if valor is not None and not comprov:
            ocorrencias.append(Ocorrencia(
                "b", "Devoluções", "Pagamento do DAE não comprovado",
                f"DAE de {fmt_money(valor)} ({d.localizacao}) sem débito/comprovante de mesmo valor localizado.",
                valor, [d.localizacao]))
    total_devolvido = round(sum(x["valor"] or 0 for x in devolucoes if x["comprovada"]), 2) if devolucoes else 0.0

    # ── Fórmula de controle (item 12) ──
    receitas = None
    if repasse is not None:
        receitas = round(repasse + (contrap_exec if contrap_exec is not None else (contrap_pact or 0)) + (rend_extratos or 0), 2)
    saldo_apurado = round(receitas - (total_nf or 0) - total_devolvido, 2) if receitas is not None else None
    saldo_final_extrato = next((s["saldo_atual"] for s in reversed(serie) if s["saldo_atual"] is not None), None)
    controle = {
        "saldo_inicial": 0.0,
        "repasses": repasse,
        "repasse_origem": repasse_origem,
        "contrapartida": contrap_exec if contrap_exec is not None else contrap_pact,
        "rendimentos_extratos": rend_extratos,
        "despesas_notas_fiscais": total_nf,
        "devolucoes": total_devolvido,
        "saldo_apurado": saldo_apurado,
        "saldo_final_extrato_aplicacao": saldo_final_extrato,
        "saldo_final_localizacao": serie[-1]["localizacao"] if serie else None,
        "memoria": (
            f"0,00 + {fmt_money(repasse)} + {fmt_money(contrap_exec if contrap_exec is not None else contrap_pact)} + "
            f"{fmt_money(rend_extratos)} − {fmt_money(total_nf)} − {fmt_money(total_devolvido)} = {fmt_money(saldo_apurado)}"
            if saldo_apurado is not None else None
        ),
    }
    if saldo_apurado is not None and saldo_final_extrato is not None and abs(saldo_apurado - saldo_final_extrato) > 1.0:
        ocorrencias.append(Ocorrencia(
            "c", "Saldo", "ALERTA DE DIVERGÊNCIA – saldo apurado × saldo bancário",
            f"Saldo apurado pela fórmula de controle: {fmt_money(saldo_apurado)}; último saldo de aplicação lido: "
            f"{fmt_money(saldo_final_extrato)}. A diferença pode decorrer de despesas sem NF lida, retenções, tarifas "
            f"ou saldo em conta corrente. {PENDENTE_HUMANO}",
            round(saldo_apurado - saldo_final_extrato, 2), [controle["saldo_final_localizacao"] or ""]))

    # Saldo residual sem devolução comprovada: receitas superam as despesas comprovadas
    residual = None
    if receitas is not None and total_nf is not None:
        residual = round(receitas - total_nf - total_devolvido, 2)
    devolucao_pendente = bool(residual is not None and residual > 1.0)

    return {
        "principal": principal,
        "vigencia": {"inicio": fmt_date(vig_ini) if vig_ini else None, "fim": fmt_date(vig_fim) if vig_fim else None, "fonte": vig_fonte},
        "repasse": {
            "valor": repasse, "fonte": repasse_fonte, "origem": repasse_origem,
            "creditos_iguais_no_extrato": [e.to_dict() for e in repasse_localizado],
            "aplicacoes_iguais": [s["localizacao"] for s in aplicacoes_serie],
        },
        "contrapartida": contrapartida,
        "demonstrativo": demonstrativo,
        "extratos_aplicacao": {
            "meses": len(serie), "serie": serie, "quebras_continuidade": len(quebras), "lacunas": lacunas,
            "rendimentos_liquidos_total": rend_extratos, "rendimentos_declarados": rend_declarado,
        },
        "conhecimentos_receita": {
            "itens": conhecimentos,
            "total_repasses": rec_repasses,
            "total_rendimentos": rec_rendimentos,
        },
        "notas_fiscais": notas,
        "total_notas_fiscais": total_nf,
        "notas_descartadas": notas_descartadas,
        "notas_sem_valor": [it["doc"].localizacao for it in nao_lidas],
        "notas_sem_guia": [n["numero"] or n["documento"] for n in sem_guia],
        "parcelas_repasse": parcelas_repasse,
        "extrato_cc_linhas": [{**x, "folha": folha(x["arquivo"], x["pagina"])}
                              for x in serializar(rotular(linhas_extrato, notas, parcelas_repasse))],
        "extrato_cc_ultimo": ultimo_cc,
        "aplicacoes_produtos": aplicacoes_produtos,
        "residual": residual,
        "devolucao_pendente": devolucao_pendente,
        "evidencias_bancarias": {
            "total": len(evidencias),
            "pagamentos": [e.to_dict() for e in pagamentos],
            "tarifas": [e.to_dict() for e in evidencias if e.classe == "tarifa"],
            "impostos": [e.to_dict() for e in evidencias if e.classe == "imposto"],
            "devolucoes": [e.to_dict() for e in evidencias if e.classe == "devolucao"],
        },
        "devolucoes": devolucoes,
        "total_devolvido": total_devolvido,
        "controle": controle,
        "ocorrencias": [o.to_dict() for o in ocorrencias],
    }
