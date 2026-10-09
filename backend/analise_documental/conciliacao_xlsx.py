"""
Saída 2 – Pré-preenchimento da planilha de Conciliação Financeira (GECOV/GECON).

Só são lançadas as células de entrada que o sistema extrai com rastreabilidade
(cabeçalho, notas fiscais, previsão do plano de trabalho × repassado e saldo
devolvido); as fórmulas do modelo calculam o restante. A movimentação bancária
linha a linha continua a cargo do analista. Cada célula preenchida recebe um
comentário com a origem do dado.
"""

import io
import re
from copy import copy
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from openpyxl.comments import Comment
from openpyxl.formula.tokenizer import Token, Tokenizer
from openpyxl.styles import Font, PatternFill

from backend.analise_documental.minuta_ad import MODELOS_DIR, _valor, coletar_dados
from backend.analise_documental.texto import parse_date
from backend.analise_documental.varredura import mes_extenso

AUTOR = "Convênio 2.0"
LARANJA = PatternFill("solid", fgColor="FFF4B183")

# Posições das células de entrada em cada modelo
LAYOUT = {
    False: {
        "arquivo": "conciliacao.xlsx",
        "convenio": "C6", "convenente": "C7", "vigencia": "C8", "conta": "C9",
        "contrato": "C33", "nf_linhas": range(35, 42),
        "previsto": ("D45", "D46"), "repassado": ("F45", "F46"), "devolvido": "J51",
        "nota": "N3",
    },
    True: {
        "arquivo": "conciliacao_inexecucao.xlsx",
        "convenio": "C6", "convenente": "C7", "vigencia": "G7", "conta": "C8",
        "contrato": "C47", "nf_linhas": range(49, 54),
        "previsto": None, "repassado": ("D57", "D58"), "devolvido": "L63",
        "nota": "N3",
    },
}


def _gravar(ws, ref: str, valor, origem: str, conferir: bool = False):
    cell = ws[ref]
    cell.value = valor
    cell.comment = Comment(f"Preenchido pelo sistema. Origem: {origem}", AUTOR)
    if conferir:
        cell.fill = LARANJA


def _data(v) -> Optional[datetime]:
    d = parse_date(v)
    return datetime(d.year, d.month, d.day) if d else None


MOV_LINHAS = range(11, 31)


def _finalizar_valores(ws, lay: Dict[str, Any], info: Dict[str, Any]):
    df = info["df"] or {}
    if lay["previsto"] and info["pact_conc"] is not None:
        _gravar(ws, lay["previsto"][0], info["pact_conc"], "valor do concedente pactuado (termo/plano de trabalho)")
        _gravar(ws, lay["previsto"][1], info["pact_cp"], "contrapartida pactuada (termo/plano de trabalho)")
    if df:
        _gravar(ws, lay["repassado"][0], df["concedente"],
                f"repasses ({(info['cruz'].get('controle') or {}).get('repasse_origem') or 'cruzamentos'})")
        _gravar(ws, lay["repassado"][1], df["contrapartida"], "contrapartida declarada/aportada (demonstrativo)", True)
    if info["total_devolvido"]:
        _gravar(ws, lay["devolvido"], info["total_devolvido"],
                "; ".join(f"{d.get('documento')} {d.get('localizacao')}" for d in info["devolucoes"]))


REF_RE = re.compile(r"(\$?)([A-Z]{1,3})(\$?)(\d+)")


def _deslocar_ref(ref: str, antes: int, n: int) -> str:
    return REF_RE.sub(lambda m: f"{m[1]}{m[2]}{m[3]}{int(m[4]) + n if int(m[4]) >= antes else m[4]}", ref)


def _deslocar_formula(formula: str, alvo: str, mesma_folha: bool, antes: int, n: int) -> str:
    partes = []
    for t in Tokenizer(formula).items:
        v = t.value
        if t.type == Token.OPERAND and t.subtype == Token.RANGE:
            if "!" in v:
                folha, ref = v.rsplit("!", 1)
                if folha.strip("'") == alvo:
                    v = f"{folha}!{_deslocar_ref(ref, antes, n)}"
            elif mesma_folha:
                v = _deslocar_ref(v, antes, n)
        partes.append(v)
    return "=" + "".join(partes)


def _inserir_linhas(wb, ws, antes: int, n: int):
    """Insere n linhas antes de `antes` levando junto fórmulas (inclusive de outras abas), mesclagens e alturas."""
    if n <= 0:
        return
    ws.insert_rows(antes, n)
    for m in ws.merged_cells.ranges:
        if m.min_row >= antes:
            m.shift(0, n)
    for r in sorted((r for r in list(ws.row_dimensions) if r >= antes), reverse=True):
        ws.row_dimensions[r + n].height = ws.row_dimensions[r].height
        ws.row_dimensions[r].height = None
    for folha in wb.worksheets:
        for row in folha.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    c.value = _deslocar_formula(c.value, ws.title, folha is ws, antes, n)
    modelo = antes + n
    for r in range(antes, antes + n):
        for col in range(1, ws.max_column + 1):
            ws.cell(r, col)._style = copy(ws.cell(modelo, col)._style)


def _formulas_movimento(ws, linhas: range):
    for r in linhas:
        ws[f"D{r}"].value = ws[f"D{r}"].value or 0
        ws[f"E{r}"].value = ws[f"E{r}"].value or 0
        ws[f"F{r}"].value = f"=D{r}-E{r}" if r == linhas.start else f"=F{r - 1}+D{r}-E{r}"
        ws[f"G{r}"].value = f'=IF($G$10=C{r},E{r},"-")'
        ws[f"H{r}"].value = f'=IF($H$10=C{r},D{r},"-")'
        ws[f"J{r}"].value = f'=IF("Tarifa"=C{r},E{r},"-")'
        ws[f"K{r}"].value = f'=IF("Tarifa"=C{r},D{r},"-")'


def _lancamentos_extrato(cruz: Dict[str, Any], principal: Optional[str]) -> List[Tuple[datetime, str, float, float, str, Optional[str]]]:
    """Todos os lançamentos do extrato da conta corrente, já rotulados (data, item, entrada, saída, origem, conferir)."""
    out = []
    for x in cruz.get("extrato_cc_linhas") or []:
        dt = _data(x.get("data"))
        if not dt:
            continue
        fl = f"fl. {x['folha']}" if x.get("folha") is not None and x.get("arquivo") == principal else f"{x.get('arquivo')}, p. {x.get('pagina')}"
        origem = f"extrato da conta corrente, {fl}: {x.get('texto')}"
        ent, sai = (x["valor"], 0.0) if x["tipo"] == "C" else (0.0, x["valor"])
        out.append((dt, x["rotulo"], ent, sai, origem, x.get("conferir")))
    return out


def _lancamentos(cruz: Dict[str, Any]) -> List[Tuple[datetime, int, str, float, float, str]]:
    """Repasses, pagamentos das NFs e transferências dos tributos (data, ordem, item, entrada, saída, origem)."""
    out = []
    for p in cruz.get("parcelas_repasse") or []:
        if _data(p.get("data")):
            out.append((_data(p["data"]), 0, "Repasse MGI", p["valor"], 0.0, p.get("localizacao") or "repasse"))
    for n in cruz.get("notas_fiscais") or []:
        num = n.get("numero") or n.get("documento")
        pg = n.get("pagamento") or {}
        if _data(pg.get("data")) and pg.get("valor"):
            out.append((_data(pg["data"]), 1, f"NF {num}", 0.0, pg["valor"], pg.get("localizacao") or ""))
        t = n.get("tributos") or {}
        data_t = _data(t.get("data")) or _data(pg.get("data"))
        if t.get("valor") and data_t:
            nomes = [x for x, k in (("INSS", "retencao_inss"), ("ISSQN", "retencao_iss"), ("RET FED", "retencao_ret_fed")) if n.get(k)]
            origem = (t.get("comprovante") or {}).get("localizacao") or t.get("extrato") or "soma das retenções da NF"
            out.append((data_t, 2, f"{' + '.join(nomes)} NF {num}", 0.0, t["valor"], origem))
    out.sort(key=lambda x: (x[0], x[1]))
    return out


def _preencher_parecer(ws, wb, resultado: Dict[str, Any], info: Dict[str, Any]):
    parecer = resultado["parecer"]
    cruz = info["cruz"]
    d = parecer["dados"]
    _gravar(ws, "B6", f"Convênio: {d.get('numero') or '---'}", "varredura do processo", not d.get("numero"))
    _gravar(ws, "B7", f"Convenente: Mun. {d.get('municipio') or '---'}", "dados do convênio", not d.get("municipio"))
    _gravar(ws, "B8", f"Vigência: {d.get('vigencia_fim') or '---'}", "dados do convênio", not d.get("vigencia_fim"))
    _gravar(ws, "B9", f"CC:{d.get('conta') or '---'}", "varredura do processo", not d.get("conta"))

    principal = parecer.get("principal")
    lanc = _lancamentos_extrato(cruz, principal) or \
        [(dt, item, ent, sai, origem, None) for dt, _, item, ent, sai, origem in _lancamentos(cruz)]
    mov = parecer["blocos"]["movimentacao"]
    ult = cruz.get("extrato_cc_ultimo") or {}
    solicitar = mov.get("resultado") == "NÃO ATENDE" and ult.get("mes")
    notas = cruz.get("notas_fiscais") or []

    # O modelo tem 20 linhas de movimentação e 7 de NF; o analista insere linhas quando não cabem
    mov_ini, mov_fim, nf_ini, nf_fim = MOV_LINHAS.start, MOV_LINHAS.stop - 1, LAYOUT[False]["nf_linhas"].start, LAYOUT[False]["nf_linhas"].stop - 1
    n_mov = max(0, len(lanc) + (1 if solicitar else 0) + 2 - len(MOV_LINHAS))
    n_nf = max(0, len(notas) - len(LAYOUT[False]["nf_linhas"]))
    _inserir_linhas(wb, ws, mov_fim, n_mov)
    _inserir_linhas(wb, ws, nf_fim + n_mov, n_nf)

    def pos(ref: str) -> str:
        col, row = re.match(r"([A-Z]+)(\d+)", ref).groups()
        row = int(row)
        return f"{col}{row + (n_mov if row >= mov_fim else 0) + (n_nf if row >= nf_fim else 0)}"

    linhas = range(mov_ini, mov_fim + n_mov + 1)
    for r in linhas:
        ws[f"D{r}"].value = ws[f"E{r}"].value = 0
    for r, (dt, item, ent, sai, origem, conferir) in zip(linhas, lanc):
        _gravar(ws, f"B{r}", dt, origem)
        ws[f"B{r}"].number_format = "dd/mm/yyyy"
        _gravar(ws, f"C{r}", item, f"{origem}. ATENÇÃO: {conferir}" if conferir else origem, bool(conferir))
        ws[f"D{r}"].value = ent
        ws[f"E{r}"].value = sai
        if conferir:
            for col in "DE":
                ws[f"{col}{r}"].fill = LARANJA
    _formulas_movimento(ws, linhas)
    if solicitar:
        mes, ano = (ult["mes"] + 1, ult["ano"]) if ult["mes"] < 12 else (1, ult["ano"] + 1)
        ref = f"C{linhas.start + len(lanc)}"
        _gravar(ws, ref, f"solicitar a partir de {mes_extenso(mes, ano)}", f"extratos apresentados até {ult.get('data')}")
        ws[ref].font = Font(bold=True, color="FFFF0000")

    empresa = parecer.get("empresa")
    if empresa:
        _gravar(ws, pos("B33"), f"CONTRATO EMPRESA: {empresa.upper()}", "emitente das notas fiscais")
    ws[pos("H34")].value = "RET FED"
    nf_linhas = list(range(nf_ini + n_mov, nf_fim + n_mov + n_nf + 1))
    for r in nf_linhas:
        ws[f"J{r}"].value = f"=F{r}-G{r}-H{r}-I{r}"
    for r, n in zip(nf_linhas, notas):
        origem = f"{n.get('documento')} – {n.get('localizacao')}"
        ref = n.get("pagina_ref") or {}
        fl = ref.get("folha")
        _gravar(ws, f"B{r}", fl if fl is not None and ref.get("arquivo") == principal else n.get("localizacao"), origem, fl is None)
        _gravar(ws, f"D{r}", n.get("numero") or n.get("numero_lido"), origem, not n.get("numero"))
        if _data(n.get("data_emissao")):
            _gravar(ws, f"E{r}", _data(n["data_emissao"]), origem)
            ws[f"E{r}"].number_format = "dd/mm/yyyy"
        _gravar(ws, f"F{r}", n.get("valor_bruto"), origem)
        for col, chave in (("G", "retencao_inss"), ("H", "retencao_ret_fed"), ("I", "retencao_iss")):
            if n.get(chave):
                _gravar(ws, f"{col}{r}", n[chave], origem if chave != "retencao_ret_fed" else
                        "bruto − INSS − ISS − líquido pago")
        pg = n.get("pagamento") or {}
        if _data(pg.get("data")):
            _gravar(ws, f"K{r}", _data(pg["data"]), pg.get("localizacao") or origem)
            ws[f"K{r}"].number_format = "dd/mm/yyyy"
        trib = (n.get("tributos") or {}).get("comprovante") or {}
        fl_trib = trib.get("folha") if trib.get("arquivo") == principal else None
        _gravar(ws, f"L{r}", str(fl_trib) if fl_trib else "n/t", trib.get("localizacao") or "comprovante de transferência dos tributos")
        guia = (n.get("guias") or {}).get("inss") or {}
        _gravar(ws, f"M{r}", str(guia.get("folha")) if guia.get("folha") else "n/t", guia.get("localizacao") or "guia de recolhimento")

    lay = dict(LAYOUT[False])
    for k in ("contrato", "devolvido"):
        lay[k] = pos(lay[k])
    for k in ("previsto", "repassado"):
        lay[k] = tuple(pos(x) for x in lay[k])
    return lay


def gerar_conciliacao(resultado: Dict[str, Any], inexecucao: bool = False) -> Tuple[bytes, str]:
    info = coletar_dados(resultado)
    lay = LAYOUT[bool(inexecucao)]
    wb = openpyxl.load_workbook(MODELOS_DIR / lay["arquivo"])
    ws = wb["CONCILIAÇÃO FINANCEIRA - GECOV"]
    dados = info["dados"]
    numero = _valor(dados, "numero_convenio")
    fonte_conv = (dados.get("numero_convenio") or {}).get("localizacao") or "dados do convênio"

    if resultado.get("parecer") and not inexecucao:
        lay = _preencher_parecer(ws, wb, resultado, info)
        _finalizar_valores(ws, lay, info)
        nota = ws[lay["nota"]]
        origem_mov = ("Movimentação lançada a partir do extrato da conta corrente" if (info["cruz"].get("extrato_cc_linhas"))
                      else "Lançados repasses, pagamentos das NFs e tributos; aplicações, resgates e tarifas ficam a cargo do analista")
        nota.value = (f"Pré-preenchida pelo sistema em {datetime.now().strftime('%d/%m/%Y %H:%M')}. {origem_mov}. "
                      "Células com comentário vieram do dossiê; em laranja, conferir.")
        nota.font = Font(bold=True, color="FFC00000")
        wb.calculation.fullCalcOnLoad = True
        buf = io.BytesIO()
        wb.save(buf)
        numero = resultado["parecer"]["dados"].get("numero") or numero
        rotulo = re.sub(r"[^\w.-]+", "_", f"Conciliacao_CV_{numero or 'sem_numero'}").strip("_")
        return buf.getvalue(), f"{rotulo}.xlsx"

    _gravar(ws, lay["convenio"], numero, fonte_conv)
    _gravar(ws, lay["convenente"], _valor(dados, "convenente"),
            (dados.get("convenente") or {}).get("localizacao") or "dados do convênio")
    ini, fim = _valor(dados, "vigencia_inicio"), _valor(dados, "vigencia_fim")
    _gravar(ws, lay["vigencia"], f"{ini or '---'} a {fim or '---'}",
            (dados.get("vigencia_fim") or {}).get("localizacao") or "dados do convênio", not (ini and fim))
    conta = _valor(dados, "banco_agencia_conta")
    _gravar(ws, lay["conta"], conta or "NÃO IDENTIFICADA", "dados do convênio",
            (dados.get("banco_agencia_conta") or {}).get("status") != "confirmado")

    ctr = (info["contrato"] or {}).get("extracao") or {}
    lic = (info["licitacao"] or {}).get("extracao") or {}
    empresa = _valor(ctr, "contratada") or _valor(lic, "vencedor")
    if empresa:
        _gravar(ws, lay["contrato"], f"{empresa} – {_valor(lic, 'modalidade') or ''}".strip(" –"),
                (info["contrato"] or info["licitacao"] or {}).get("localizacao") or "", True)

    linhas = list(lay["nf_linhas"])
    notas = info["notas"]
    excedentes = notas[len(linhas) - 1:] if len(notas) > len(linhas) else []
    for idx, n in enumerate(notas[:len(linhas) - 1] if excedentes else notas):
        r = linhas[idx]
        origem = f"{n.get('documento')} – {n.get('localizacao')}"
        _gravar(ws, f"B{r}", n.get("localizacao"), origem)
        if n.get("numero"):
            _gravar(ws, f"D{r}", n["numero"], origem)
        if _data(n.get("data_emissao")):
            _gravar(ws, f"E{r}", _data(n["data_emissao"]), origem)
            ws[f"E{r}"].number_format = "dd/mm/yyyy"
        _gravar(ws, f"F{r}", n.get("valor_bruto"), origem, n.get("valor_bruto") is None)
        for col, chave in (("G", "inss"), ("H", "ir"), ("I", "iss")):
            if n.get(chave) is not None:
                _gravar(ws, f"{col}{r}", n[chave], origem)
        pg = n.get("pagamento") or {}
        if _data(pg.get("data")):
            _gravar(ws, f"K{r}", _data(pg["data"]), pg.get("localizacao") or origem)
            ws[f"K{r}"].number_format = "dd/mm/yyyy"
    if excedentes:
        r = linhas[-1]
        _gravar(ws, f"B{r}", f"Demais {len(excedentes)} NF(s) – ver Relatório de Validação", "agregado", True)
        _gravar(ws, f"F{r}", sum(n.get("valor_bruto") or 0 for n in excedentes), "agregado", True)
        for col, chave in (("G", "inss"), ("H", "ir"), ("I", "iss")):
            _gravar(ws, f"{col}{r}", sum(n.get(chave) or 0 for n in excedentes), "agregado", True)

    _finalizar_valores(ws, lay, info)

    nota = ws[lay["nota"]]
    nota.value = (f"Pré-preenchida pelo sistema em {datetime.now().strftime('%d/%m/%Y %H:%M')}. Células com comentário "
                  "vieram do dossiê; em laranja, conferir. Movimentação bancária, valores não aplicados, tarifas e "
                  "nota técnica devem ser lançados pelo analista.")
    nota.font = Font(bold=True, color="FFC00000")

    wb.calculation.fullCalcOnLoad = True
    buf = io.BytesIO()
    wb.save(buf)
    rotulo = re.sub(r"[^\w.-]+", "_", f"Conciliacao_CV_{numero or 'sem_numero'}{'_inexecucao' if inexecucao else ''}").strip("_")
    return buf.getvalue(), f"{rotulo}.xlsx"
