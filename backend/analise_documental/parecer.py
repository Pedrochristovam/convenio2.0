"""
Parecer no formato da GECOV.

Converte o Relatório de Validação e os cruzamentos nas frases, cabeçalhos e
marcações que o analista usa na AD, no Anexo de Solicitação de Documentos e no
Ofício de diligência. Tudo aqui é determinístico e fica gravado no resultado do
dossiê (chave "parecer") para que os geradores de documentos só leiam.
"""

import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from backend.analise_documental.extratores import valor_campo
from backend.analise_documental.inventario import Documento
from backend.analise_documental.texto import fmt_money, norm, parse_date
from backend.analise_documental.varredura import faixa_folhas, folha, mes_extenso, volume

VERSAO = 3

ATENDE = "ATENDE"
RESSALVAS = "ATENDE COM RESSALVAS"
NAO_ATENDE = "NÃO ATENDE"
NAO_CONSTA = "NÃO CONSTA"

RESSALVA_PRAZO = {
    "DEC_43635": "Encaminhamento da Prestação de Contas Final após o prazo estabelecido no §5º do art. 26, do Decreto 43.635/2003.",
    "DEC_46319": "Encaminhamento da Prestação de Contas Final após o prazo estabelecido no art.54, §3º do Decreto 46.319/2013.",
}
ARTIGO_DILIGENCIA = {
    "DEC_43635": "conforme disposto no Decreto Estadual nº 43.635/2003",
    "DEC_46319": "conforme disposto no artigo 60 do Decreto Estadual nº 46.319/2013",
}
CONTA_MGI = ["BANCO DO BRASIL", "Agência: 1615-2", "Conta: 20.800-0", "CNPJ MGI: 19.296.342/0001-29"]
PARCELAS_EXTENSO = {1: "Parcela Única", 2: "Duas Parcelas", 3: "Três Parcelas", 4: "Quatro Parcelas", 5: "Cinco Parcelas"}

ACENTOS = {
    "CONSTRUCOES": "Construções", "CONSTRUCAO": "Construção", "SERVICOS": "Serviços", "SERVICO": "Serviço",
    "COMERCIO": "Comércio", "PAVIMENTACAO": "Pavimentação", "INCORPORACOES": "Incorporações", "TERRAPLANAGEM": "Terraplanagem",
    "ELETRICA": "Elétrica", "HIDRAULICA": "Hidráulica", "LOCACAO": "Locação", "LOCACOES": "Locações",
}
MINUSCULAS = {"E", "DE", "DA", "DO", "DAS", "DOS"}

Parte = List[Any]  # [texto, destacar, negrito]


def _p(texto: str, destacar: bool = False, negrito: Optional[bool] = True) -> Parte:
    return [texto, destacar, negrito]


def _municipio(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    return re.sub(r"^(munic[ií]pio|prefeitura municipal)\s+de\s+", "", str(v), flags=re.IGNORECASE).strip()


def empresa_curta(nome: Optional[str]) -> Optional[str]:
    """'VTCR ENGENHARIA E CONSTRUCOES LTDA - ME' → 'VTCR Engenharia e Construções'."""
    if not nome:
        return None
    base = re.split(r"\s*[-–]?\s*\b(LTDA|EIRELI|S/?A|ME|EPP|MEI)\b", str(nome).strip(), flags=re.IGNORECASE)[0]
    base = re.sub(r"^EMPRESA\s*:?\s*", "", base, flags=re.IGNORECASE).strip(" -–.,")
    palavras = []
    for i, w in enumerate(base.split()):
        n = norm(w)
        if n in ACENTOS:
            palavras.append(ACENTOS[n])
        elif i and n in MINUSCULAS:
            palavras.append(w.lower())
        elif len(w) <= 4 and w.isupper() and not re.search(r"[AEIOU]{2}", n) and i == 0:
            palavras.append(w)  # sigla no início do nome ("VTCR")
        else:
            palavras.append(w.capitalize())
    return " ".join(palavras) or None


def _numero_oficio(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    m = re.search(r"(\d{1,5})\s*/\s*(\d{4}|\d{2})\b", str(v))
    if not m:
        return str(v).strip()
    ano = m.group(2) if len(m.group(2)) == 4 else f"20{m.group(2)}"
    return f"{int(m.group(1))}/{ano}"


def _lista_pt(itens: List[str]) -> str:
    itens = [i for i in itens if i]
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


def _proximo_mes(mes_ano: Optional[str]) -> Optional[Tuple[int, int]]:
    if not mes_ano:
        return None
    m = re.match(r"(\d{1,2})/(\d{4})", mes_ano)
    if not m:
        return None
    mes, ano = int(m.group(1)), int(m.group(2))
    return (1, ano + 1) if mes == 12 else (mes + 1, ano)


def _refs_docs(docs: List[Documento], tipos: Tuple[str, ...], principal: Optional[str]) -> List[Tuple[str, int]]:
    refs = [(p.arquivo, p.pagina) for d in docs if d.tipo in tipos and not d.duplicado_de for p in d.paginas]
    no_principal = [r for r in refs if r[0] == principal]
    return no_principal or refs


def _faixa_bloco(refs: List[Tuple[str, int]], principal: Optional[str], folga: int = 4,
                 desde_inicio: int = 0) -> Tuple[str, bool]:
    """Faixa do maior bloco contínuo de páginas (cópias soltas mais adiante no volume não esticam a faixa)."""
    if not refs:
        return "", False
    arq = principal if any(a == principal for a, _ in refs) else refs[0][0]
    pags = sorted({p for a, p in refs if a == arq})
    blocos, atual = [], [pags[0]]
    for p in pags[1:]:
        if p - atual[-1] <= folga:
            atual.append(p)
        else:
            blocos.append(atual)
            atual = [p]
    blocos.append(atual)
    maior = max(blocos, key=len)
    ini = 1 if maior[0] <= desde_inicio else maior[0]
    return faixa_folhas([(arq, ini), (arq, maior[-1])], principal)


def _fls_ref(ref: Optional[Dict], principal: Optional[str]) -> Optional[str]:
    if not ref or ref.get("folha") is None:
        return None
    f = f"{ref['folha']:02d}"
    if ref.get("arquivo") == principal:
        return f
    vol = volume(ref.get("arquivo") or "")
    return f"{f} (Vol. {vol})" if vol else f


def montar_parecer(docs: List[Documento], convenio: Dict[str, Any], cruz: Dict[str, Any],
                   relatorio: Dict[str, Any]) -> Dict[str, Any]:
    principal = cruz.get("principal")
    itens = {i["item"]: i for i in relatorio.get("itens") or []}
    regime = (relatorio.get("regime") or {}).get("codigo")
    lv = cruz.get("licitacao_varredura") or {}
    notas = cruz.get("notas_fiscais") or []
    ativos = [d for d in docs if not d.duplicado_de]

    # ── I – Dados do convênio ──
    conta_info = convenio.get("banco_agencia_conta") or {}
    banco, agencia, conta = conta_info.get("banco"), conta_info.get("agencia"), conta_info.get("conta")
    parcelas = cruz.get("parcelas_repasse") or []
    interv = convenio.get("interveniente") or {}
    dados = {
        "numero": valor_campo(convenio, "numero_convenio"),
        "municipio": _municipio(valor_campo(convenio, "convenente")),
        "interveniente": interv.get("valor"),
        "interveniente_nome": interv.get("nome_completo"),
        "interveniente_sigla": interv.get("sigla_atual"),
        "objeto": valor_campo(convenio, "objeto"),
        "vigencia_fim": (cruz.get("vigencia") or {}).get("fim") or valor_campo(convenio, "vigencia_fim"),
        "valor_concedente": valor_campo(convenio, "valor_concedente"),
        "valor_contrapartida": valor_campo(convenio, "valor_contrapartida"),
        "valor_total": valor_campo(convenio, "valor_total"),
        "parcelas": PARCELAS_EXTENSO.get(len(parcelas)) if parcelas else None,
        "parcelas_detalhe": parcelas,
        "banco": banco, "agencia": agencia, "conta": conta,
    }

    # ── Prestação de contas ──
    oficio = next((d for d in ativos if d.tipo == "OFICIO"), None)
    ofi = oficio.extracao if oficio else {}
    item_prazo = itens.get("Prazo da prestação de contas") or {}
    atraso = any(o.get("titulo") == "Prestação de contas apresentada fora do prazo" for o in relatorio.get("ocorrencias") or [])
    pc = {
        "oficio": _numero_oficio(valor_campo(ofi, "numero")),
        "data": valor_campo(ofi, "data"),
        "resultado": item_prazo.get("resultado"),
        "ressalvas": [RESSALVA_PRAZO.get(regime) or " OU ".join(RESSALVA_PRAZO.values())] if atraso else [],
        "fls": _fls_ref({"arquivo": oficio.paginas[0].arquivo, "folha": folha(oficio.paginas[0].arquivo, oficio.paginas[0].pagina)}, principal) if oficio else None,
    }

    blocos: Dict[str, Dict[str, Any]] = {}

    # ── Processo licitatório ──
    refs_lic = _refs_docs(docs, ("LICITACAO", "CONTRATO", "TERMO_ADITIVO"), principal)
    # O volume da prestação abre com os ofícios e segue com a licitação: a GECOV cita a faixa desde a 1ª folha
    fl_lic, ok_lic = _faixa_bloco(refs_lic, principal, folga=8, desde_inicio=3)
    emitentes = [n.get("emitente") for n in notas if n.get("emitente")]
    emitente = max(set(emitentes), key=emitentes.count) if emitentes else None
    contrato_doc = next((d for d in ativos if d.tipo == "CONTRATO" and valor_campo(d.extracao or {}, "contratada")), None)
    empresa_lida = emitente or (valor_campo(contrato_doc.extracao, "contratada") if contrato_doc else None)
    empresa = empresa_curta(empresa_lida)
    empresa_completa = " ".join(ACENTOS[norm(w)].upper() if norm(w) in ACENTOS else w
                                for w in (empresa_lida or "").split()) or None
    valor_ctr = lv.get("valor_contrato") or (valor_campo(contrato_doc.extracao, "valor") if contrato_doc else None)
    cab_lic = [_p("Processo Licitatório nº "), _p(lv.get("processo") or "---", not lv.get("processo"))]
    if lv.get("modalidade"):
        cab_lic += [_p(" – "), _p(lv["modalidade"])]
    cab_lic += [_p(" – Contrato nº "), _p(lv.get("contrato") or "---", not lv.get("contrato")),
                _p(" – Empresa: "), _p(empresa or "---", not empresa),
                _p(" - "), _p(fmt_money(valor_ctr) if valor_ctr else "R$ ---", not valor_ctr),
                _p(" – Vigência: "), _p(lv.get("vigencia_contrato") or "---", not lv.get("vigencia_contrato")),
                _p(" (Fls.: "), _p(fl_lic or "---", not ok_lic), _p(")")]
    item_lic = itens.get("Processo licitatório") or {}
    linhas_lic = [[o["descricao"], True] for o in relatorio.get("ocorrencias") or []
                  if o["item"] == "Processo licitatório" and o["categoria"] in ("a", "c", "e", "f")]
    blocos["licitacao"] = {"resultado": item_lic.get("resultado"), "cabecalho": cab_lic, "fls": fl_lic, "linhas": linhas_lic}

    # ── Ordem de serviço ──
    refs_os = [tuple(r) for r in lv.get("ordem_servico_paginas") or []]
    refs_os = [r for r in refs_os if r[0] == principal] or refs_os or _refs_docs(docs, ("ORDEM_SERVICO",), principal)
    fl_os, ok_os = faixa_folhas(refs_os[:1], principal) if refs_os else ("", False)
    item_os = itens.get("Ordem de serviço") or {}
    blocos["ordem_servico"] = {
        "resultado": item_os.get("resultado"),
        "cabecalho": [_p("Ordem de Serviço (Fls.: "), _p(fl_os or "---", not ok_os), _p(")")],
        "fls": fl_os, "linhas": [],
    }

    # ── Comprovantes de despesas ──
    refs_desp = []
    for n in notas:
        for chave in ("pagina_ref", "pagamento_comprovante"):
            r = n.get(chave)
            if r and r.get("arquivo") == principal:
                refs_desp.append((r["arquivo"], r["pagina"]))
        r = (n.get("tributos") or {}).get("comprovante")
        if r and r.get("arquivo") == principal:
            refs_desp.append((r["arquivo"], r["pagina"]))
    if not refs_desp:
        refs_desp = [(n["pagina_ref"]["arquivo"], n["pagina_ref"]["pagina"]) for n in notas if n.get("pagina_ref")]
    fl_desp, ok_desp = _faixa_bloco(refs_desp, principal, folga=8)
    sem_guia = [n for n in notas if n.get("guias_faltantes")]
    linhas_desp: List[List[Any]] = []
    providencia_desp = None
    if sem_guia:
        tributos_nomes = []
        if any(n.get("retencao_iss") for n in sem_guia):
            tributos_nomes.append("ISSQN")
        if any(n.get("retencao_inss") for n in sem_guia):
            tributos_nomes.append("INSS")
        if any(n.get("retencao_ret_fed") for n in sem_guia):
            tributos_nomes.append("demais Retenções Federais" if tributos_nomes else "Retenções Federais")
        tributos_txt = _lista_pt(tributos_nomes)
        todas = len(sem_guia) == len(notas)
        numeros_sem = [n.get("numero") or n["documento"] for n in sem_guia]
        alvo = "em todas as Notas Fiscais" if todas else f"nas Notas Fiscais nº {_lista_pt(numeros_sem)}"
        texto = f"Ausência de guia de recolhimento ou comprovante de pagamento do recolhimento de {tributos_txt} destacadas {alvo}."
        com_transf = [(n.get("numero") or n["documento"], _fls_ref((n.get("tributos") or {}).get("comprovante"), principal))
                      for n in sem_guia]
        com_transf = [(num, f) for num, f in com_transf if f]
        if com_transf:
            plural = len(com_transf) > 1
            texto += (f" Os comprovantes de transferências dos valores dos tributos {'das' if plural else 'da'} "
                      f"{'Notas Fiscais' if plural else 'Nota Fiscal'} nº {_lista_pt([c[0] for c in com_transf])} "
                      f"{'constam' if plural else 'consta'} na Prestação de Contas {'nas fls.' if plural else 'na fl.'} "
                      f"{_lista_pt([c[1] for c in com_transf])}{', respectivamente' if plural else ''}, contudo, os "
                      "comprovantes de recolhimento/quitação não foram enviados.")
        linhas_desp.append([texto, False])
        providencia_desp = (f"Guia de recolhimento ou comprovante de pagamento do recolhimento de {tributos_txt} destacadas "
                            f"nas Notas Fiscais nº {_lista_pt(numeros_sem)}"
                            + (f" emitidas pela empresa {empresa_completa.upper()}." if empresa_completa else "."))
    for o in relatorio.get("ocorrencias") or []:
        if o["item"] == "Comprovantes de despesas" and o["categoria"] in ("c", "e", "f"):
            linhas_desp.append([o["descricao"], True])
    item_desp = itens.get("Comprovantes de despesas") or {}
    blocos["despesas"] = {
        "resultado": item_desp.get("resultado"),
        "cabecalho": [_p("Comprovantes de Despesas (Fls.: "), _p(fl_desp or "---", not ok_desp), _p(")")],
        "fls": fl_desp, "linhas": linhas_desp,
    }

    # ── Movimentação bancária ──
    refs_ext = _refs_docs(docs, ("EXTRATOS", "EXTRATO_CC", "EXTRATO_APLICACAO"), principal)
    fl_ext, ok_ext = _faixa_bloco(refs_ext, principal, folga=6)
    conta_txt = f"{banco or 'Banco ---'} / Ag: {agencia or '---'} / CC: {conta or '---'}"
    conta_ok = bool(banco and agencia and conta)
    item_mov = itens.get("Movimentação bancária") or {}
    ult = cruz.get("extrato_cc_ultimo") or {}
    prox_cc = (ult["mes"] + 1, ult["ano"]) if ult and ult.get("mes") and ult["mes"] < 12 else \
        ((1, ult["ano"] + 1) if ult and ult.get("mes") else None)
    linhas_mov: List[List[Any]] = []
    situacoes_mov: List[str] = []
    providencias_mov: List[Any] = []
    if item_mov.get("resultado") == NAO_ATENDE:
        conta_longa = f"Conta Corrente nº {conta or '---'} / Ag.: {agencia or '---'} / {banco or 'Banco ---'}"
        if cruz.get("devolucao_pendente"):
            linhas_mov.append(["Não foi localizado o comprovante de devolução de saldo residual do Convênio;", False])
            situacoes_mov.append("Não foi localizado o comprovante de devolução de saldo residual do Convênio;")
            providencias_mov.append({"texto": "Efetuar a devolução do Saldo do Convênio por meio de Depósito Bancário em favor da Concedente MGI:",
                                     "sub": CONTA_MGI + ["", "Enviar o Comprovante de Devolução do Saldo"]})
        if prox_cc:
            mm = f"{prox_cc[0]:02d}/{prox_cc[1]}"
            linhas_mov.append([f"Não foram apresentados extratos de Conta Corrente a partir do mês {mm} até o saldo zerado;", False])
            situacoes_mov.append(f"Não foram apresentados extratos da {conta_longa} a partir do mês {mm} até o saldo zerado;")
            providencias_mov.append(f"Enviar os extratos bancários da {conta_longa} a partir de {mes_extenso(*prox_cc)} até o saldo zerado;")
        produtos = [p["produto"] for p in cruz.get("aplicacoes_produtos") or []]
        if "Poupança Ouro" in produtos and "Poupança" in produtos:
            produtos.remove("Poupança")
        meses_prod = {p["produto"]: p.get("ultimo_mes") for p in cruz.get("aplicacoes_produtos") or []}
        for nome in produtos:
            # A data impressa no extrato de poupança costuma ser a da emissão; o mês da conta corrente é a referência
            prox = prox_cc or _proximo_mes(meses_prod.get(nome))
            prod = {"produto": nome}
            if not prox:
                continue
            mm = f"{prox[0]:02d}/{prox[1]}"
            linhas_mov.append([f"Não foram apresentados extratos da Conta de Investimentos ({prod['produto']}) a partir do mês "
                               f"{mm} até o saldo zerado;", False])
            situacoes_mov.append(f"Não foram apresentados extratos da Conta de Investimentos vinculada ({prod['produto']}) "
                                 f"a partir do mês {mm} até o saldo zerado;")
            providencias_mov.append(f"Enviar os extratos bancários da Conta de Investimentos vinculada ({prod['produto']}) "
                                    f"a partir do mês {mm} até o saldo zerado;")
        if linhas_mov:
            linhas_mov[-1][0] = linhas_mov[-1][0].rstrip(";") + "."
        if situacoes_mov:
            situacoes_mov[-1] = situacoes_mov[-1].rstrip(";") + "."
        if providencias_mov and isinstance(providencias_mov[-1], str):
            providencias_mov[-1] = providencias_mov[-1].rstrip(";") + "."
    blocos["movimentacao"] = {
        "resultado": item_mov.get("resultado"),
        "cabecalho": [_p("Movimentação Bancária: "), _p(conta_txt, not conta_ok), _p(" (Fls.: "), _p(fl_ext or "---", not ok_ext), _p(")")],
        "fls": fl_ext, "linhas": linhas_mov,
    }

    # ── Anexo – Solicitação de Documentos ──
    solicitacao = []
    if linhas_desp and providencia_desp:
        solicitacao.append({"titulo": "Comprovantes de Despesas (Notas Fiscais):",
                            "situacao": [linhas_desp[0][0]], "providencia": [providencia_desp]})
    if situacoes_mov:
        solicitacao.append({"titulo": "Movimentação Bancária:", "situacao": situacoes_mov, "providencia": providencias_mov})

    diligencia = bool(solicitacao) or any(b["resultado"] in (NAO_ATENDE, NAO_CONSTA) for b in blocos.values())

    return {
        "versao": VERSAO,
        "principal": principal,
        "regime": regime,
        "dados": dados,
        "pc": pc,
        "blocos": blocos,
        "diligencia": diligencia,
        "solicitacao": solicitacao,
        "artigo_diligencia": ARTIGO_DILIGENCIA.get(regime) or ARTIGO_DILIGENCIA["DEC_46319"],
        "empresa": empresa_completa,
    }
