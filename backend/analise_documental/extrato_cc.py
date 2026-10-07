"""
Leitura determinística do extrato de conta corrente (layout Banco do Brasil) a partir do OCR.

Cada lançamento do extrato tem duas datas (movimento e balancete), histórico,
documento, valor com C/D e, às vezes, o saldo. O valor é o primeiro número
seguido de C/D; os dígitos são confiáveis mesmo quando o OCR perde a vírgula
("880D" = 8,80 D). Quando o saldo impresso não fecha com os lançamentos, as
linhas do trecho são marcadas para conferência — o sistema não corrige valores.
"""

import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from backend.analise_documental.classificador import Pagina
from backend.analise_documental.texto import fmt_date, fmt_money, norm, parse_date

CABECALHO_RE = re.compile(r"EXTRATO (DE )?CONTA CORRENTE")
PERIODO_RE = re.compile(r"PERIODO DO EXTRATO\s*:?\s*(\d{2})\s*/\s*(\d{4})")
LANCAMENTO_RE = re.compile(r"^\W*(\d{2}/\d{2}/\d{4})\s*\|?\s*(\d{2}/\d{2}/\d{4})\s*\|?\s*(.*)$")
SALDO_RE = re.compile(r"^\W*(\d{2}/\d{2}/\d{4})\s*\|?\s*(SALDO\b.*)$", re.I)
VALOR_CD_RE = re.compile(r"(\d[\d.,]*\d)\s*(€?[CD]|€)(?![A-BD-Za-bd-z])")
VALOR_OK_RE = re.compile(r"^\d{1,3}([.,]\d{3})*,\d{2}$|^\d+[.,]\d{2}$")
# "17,200 0,00 C": o OCR leu o "D" do lançamento como zero
D_LIDO_ZERO_RE = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2})[0O]\s+\S*$")


def _valor(token: str) -> Optional[float]:
    digitos = re.sub(r"\D", "", token)
    if len(digitos) < 3:
        return None
    return int(digitos) / 100


def _paginas_extrato(paginas: List[Pagina], principal: Optional[str]) -> List[Pagina]:
    cc = [p for p in paginas if p.tipo == "EXTRATO_CC" or CABECALHO_RE.search(norm(p.texto[:1500]))]
    do_principal = [p for p in cc if p.arquivo == principal]
    return sorted(do_principal or cc, key=lambda p: (p.arquivo, p.pagina))


def _ler_pagina(p: Pagina) -> Tuple[List[Dict[str, Any]], List[Tuple[int, float]], Optional[float]]:
    """Lançamentos da página, saldos impressos (índice do último lançamento, saldo) e saldo anterior."""
    linhas: List[Dict[str, Any]] = []
    saldos: List[Tuple[int, float]] = []
    anterior = None
    for bruta in p.texto.splitlines():
        s = SALDO_RE.match(bruta.strip())
        if s:
            m = VALOR_CD_RE.search(s.group(2))
            if m and VALOR_OK_RE.match(m.group(1)):
                v = _valor(m.group(1)) * (-1 if "D" in m.group(2) else 1)
                if "ANTERIOR" in norm(s.group(2)):
                    anterior = v
                else:
                    saldos.append((len(linhas) - 1, v))
            continue
        m = LANCAMENTO_RE.match(bruta.strip())
        if not m:
            continue
        resto = m.group(3)
        if "SALDO" in norm(resto)[:20]:
            continue
        valores = list(VALOR_CD_RE.finditer(resto))
        dt = parse_date(m.group(1))
        if not valores or not dt:
            continue
        v, tipo, saldo_tok = _valor(valores[0].group(1)), valores[0].group(2), valores[1] if len(valores) > 1 else None
        fim_valor = valores[0].start()
        if not v:
            z = D_LIDO_ZERO_RE.search(resto[:valores[0].start()].rstrip() + " x")
            if not z:
                continue
            v, tipo, saldo_tok, fim_valor = _valor(z.group(1)), "D", valores[0], z.start()
        antes = resto[:fim_valor].strip(" |")
        historico = re.split(r"\s(?=\d)", antes, maxsplit=1)[0].strip(" |")
        documento = antes[len(historico):].strip()
        linhas.append({
            "data": dt, "historico": historico, "documento": documento, "valor": v,
            "tipo": "D" if "D" in tipo else "C",
            "arquivo": p.arquivo, "pagina": p.pagina, "texto": bruta.strip(), "conferir": None,
        })
        if saldo_tok and VALOR_OK_RE.match(saldo_tok.group(1)):
            saldos.append((len(linhas) - 1, _valor(saldo_tok.group(1)) * (-1 if "D" in saldo_tok.group(2) else 1)))
    return linhas, saldos, anterior


def _conferir_saldos(linhas: List[Dict[str, Any]], saldos: List[Tuple[int, float]], anterior: Optional[float]):
    """
    Confere os lançamentos contra o último saldo que fechou. Um saldo intermediário
    mal lido não condena o trecho se o saldo seguinte fechar a partir do anterior.
    """
    def fecha(de: float, ini: int, fim: int, saldo: float) -> float:
        return round(saldo - de - sum(x["valor"] if x["tipo"] == "C" else -x["valor"] for x in linhas[ini:fim + 1]), 2)

    def marcar(ini: int, fim: int, saldo: float, dif: float):
        for x in linhas[ini:fim + 1]:
            x["conferir"] = (f"Saldo impresso no extrato ({fmt_money(saldo)}) não fecha com os lançamentos "
                             f"lidos (diferença de {fmt_money(abs(dif))}): conferir a leitura dos valores.")

    base, inicio, pendente = anterior, 0, None
    for idx, saldo in saldos:
        if base is None:
            base, inicio = saldo, idx + 1
            continue
        if abs(fecha(base, inicio, idx, saldo)) <= 0.009:
            base, inicio, pendente = saldo, idx + 1, None
        elif pendente and abs(fecha(pendente[1], pendente[0] + 1, idx, saldo)) <= 0.009:
            marcar(inicio, pendente[0], pendente[1], fecha(base, inicio, pendente[0], pendente[1]))
            base, inicio, pendente = saldo, idx + 1, None
        else:
            pendente = (idx, saldo)
    if pendente:
        marcar(inicio, pendente[0], pendente[1], fecha(base, inicio, pendente[0], pendente[1]))


def ler_extrato_cc(paginas: List[Pagina], principal: Optional[str]) -> List[Dict[str, Any]]:
    """Lançamentos da conta corrente em ordem cronológica, um extrato por mês (cópias repetidas são ignoradas)."""
    vistos = set()
    out: List[Dict[str, Any]] = []
    for p in _paginas_extrato(paginas, principal):
        linhas, saldos, anterior = _ler_pagina(p)
        if not linhas:
            continue
        m = PERIODO_RE.search(norm(p.texto[:2000]))
        periodo = (int(m.group(2)), int(m.group(1))) if m else None
        chave = periodo or tuple((x["data"], x["valor"], x["tipo"]) for x in linhas)
        if chave in vistos:
            continue
        vistos.add(chave)
        _conferir_saldos(linhas, saldos, anterior)
        out.extend(linhas)
    out.sort(key=lambda x: x["data"])
    return out


def ultimo_periodo(paginas: List[Pagina], principal: Optional[str]) -> Optional[Dict[str, Any]]:
    """Mês mais recente de extrato de conta corrente apresentado (cabeçalho "Período do extrato")."""
    melhor = None
    for p in _paginas_extrato(paginas, principal):
        m = PERIODO_RE.search(norm(p.texto[:2000]))
        if m and 1 <= int(m.group(1)) <= 12 and (not melhor or (int(m.group(2)), int(m.group(1))) > melhor[0]):
            melhor = ((int(m.group(2)), int(m.group(1))), p)
    if not melhor:
        return None
    (ano, mes), p = melhor
    return {"mes": mes, "ano": ano, "arquivo": p.arquivo, "pagina": p.pagina}


def como_movimentacoes(linhas: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Mesmo formato de `listar_movimentacoes_cc`, para alimentar as evidências bancárias."""
    por_arquivo: Dict[str, List[Dict[str, Any]]] = {}
    for x in linhas:
        por_arquivo.setdefault(x["arquivo"], []).append({
            "pagina": x["pagina"], "data_movimento": fmt_date(x["data"]), "historico": x["historico"],
            "valor": x["valor"], "valor_tipo": x["tipo"], "documento": x["documento"],
        })
    return por_arquivo


TARIFA_RE = re.compile(r"\bTAR\b|TARIFA|CESTA|PACOTE")
RESGATE_RE = re.compile(r"RESGATE")
APLICACAO_RE = re.compile(r"APLICAC|\bAPLIC\b")
FUNDO_RE = re.compile(r"BB ?CP|ADMIN|SUPREMO|RENDE FACIL|FUNDO")
DEVOLUCAO_RE = re.compile(r"FAZENDA|\bDAE\b|DEVOLU|RESTITU")
TARIFA_DEVOLVIDA_MAX = 50.0
# Ordem dentro do dia, como o analista lança: entradas que cobrem os débitos primeiro
ORDEM = {"Repasse MGI": 0, "Resgate": 0, "Tarifa D": 1, "NF": 2, "C": 3, "Estorno Cred não id": 4,
         "Tributos": 5, "Débito não identificado": 5, "Devolução": 5, "Aplicação": 6}


def _perto(a: Optional[date], b: Optional[date], dias: int) -> bool:
    return bool(a and b and abs((a - b).days) <= dias)


def rotular(linhas: List[Dict[str, Any]], notas: List[Dict[str, Any]], parcelas: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Dá a cada lançamento o rótulo da planilha de conciliação (as fórmulas do modelo dependem dele)."""
    alvos = []
    for n in notas:
        num = n.get("numero") or n.get("documento")
        pg = n.get("pagamento") or {}
        if pg.get("valor"):
            alvos.append(("NF", f"NF {num}", pg["valor"], parse_date(pg.get("data"))))
        t = n.get("tributos") or {}
        if t.get("valor"):
            nomes = [x for x, k in (("INSS", "retencao_inss"), ("ISSQN", "retencao_iss"), ("RET FED", "retencao_ret_fed")) if n.get(k)]
            alvos.append(("Tributos", f"{' + '.join(nomes)} NF {num}", t["valor"], parse_date(t.get("data")) or parse_date(pg.get("data"))))
    repasses = [(p["valor"], parse_date(p.get("data"))) for p in parcelas or [] if p.get("valor")]

    out = [dict(x, rotulo=None, grupo=None) for x in linhas]
    for x in out:
        h, credito = norm(x["historico"]), x["tipo"] == "C"
        if TARIFA_RE.search(h) and not credito:
            x["rotulo"], x["grupo"] = "Tarifa", "Tarifa D"
        elif RESGATE_RE.search(h) or (FUNDO_RE.search(h) and credito) or (APLICACAO_RE.search(h) and credito):
            x["rotulo"] = x["grupo"] = "Resgate"
        elif APLICACAO_RE.search(h) or FUNDO_RE.search(h):
            x["rotulo"] = x["grupo"] = "Aplicação"
        elif credito and any(abs(v - x["valor"]) <= 0.011 and (not d or _perto(d, x["data"], 5)) for v, d in repasses):
            x["rotulo"] = x["grupo"] = "Repasse MGI"
        elif not credito:
            for i, (grupo, rot, v, d) in enumerate(alvos):
                if abs(v - x["valor"]) <= 0.011 and (not d or _perto(d, x["data"], 7)):
                    x["rotulo"], x["grupo"] = rot, grupo
                    alvos.pop(i)
                    break
            else:
                if DEVOLUCAO_RE.search(h):
                    x["rotulo"] = x["grupo"] = "Devolução"
    for x in out:
        if x["rotulo"]:
            continue
        par = next((y for y in out if y is not x and not y["rotulo"] and y["tipo"] != x["tipo"]
                    and y["data"] == x["data"] and abs(y["valor"] - x["valor"]) <= 0.011), None)
        if par:
            cred, deb = (x, par) if x["tipo"] == "C" else (par, x)
            cred["rotulo"], cred["grupo"] = "Cred não id", "C"
            deb["rotulo"], deb["grupo"] = "Estorno Cred não id", "Estorno Cred não id"
        elif x["tipo"] == "C":
            x["rotulo"] = "Tarifa" if x["valor"] <= TARIFA_DEVOLVIDA_MAX else "Contrapartida"
            x["grupo"] = "C"
        else:
            x["rotulo"] = x["grupo"] = "Débito não identificado"
            x["conferir"] = x["conferir"] or "Débito sem NF, tributo ou devolução correspondente: identificar."
    ordem = {id(x): i for i, x in enumerate(out)}
    out.sort(key=lambda x: (x["data"], ORDEM.get(x["grupo"], 5), ordem[id(x)]))
    for x in out:
        x.pop("grupo")
    return out


def serializar(linhas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{**x, "data": fmt_date(x["data"]) if isinstance(x["data"], date) else x["data"]} for x in linhas]
