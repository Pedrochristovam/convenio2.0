"""
Saída 1 – Relatório de Validação para o Analista (item 23 do PROMPT-MESTRE).

Classificações permitidas: ATENDE, ATENDE COM RESSALVAS, NÃO ATENDE, NÃO CONSTA.
Itens que dependem de juízo técnico/jurídico ou de base normativa ainda não
carregada ficam como PENDENTE DE VALIDAÇÃO HUMANA. NÃO ATENDE só é emitido nos
casos objetivos em que a GECOV também o marca na diligência: saldo residual sem
comprovante de devolução ou extratos que não chegam ao saldo zerado.
"""

from typing import Any, Dict, List, Optional

from backend.analise_documental.extratores import fonte_campo, valor_campo
from backend.analise_documental.inventario import Documento
from backend.analise_documental.regimes import (
    DEC_46319,
    REDACAO_46831,
    aplicar_regras,
    data_limite_pc,
    determinar_regime,
    eh_obra,
    fundamentar,
    montar_checklist_regime,
    parcelas_repasse,
    regime_de,
)
from backend.analise_documental.texto import NAO_IDENTIFICADO, PENDENTE_HUMANO, fmt_money, parse_date
from backend.analise_documental.varredura import resumo_licitacao

ATENDE = "ATENDE"
RESSALVAS = "ATENDE COM RESSALVAS"
NAO_ATENDE = "NÃO ATENDE"
NAO_CONSTA = "NÃO CONSTA"
PENDENTE = "PENDENTE DE VALIDAÇÃO HUMANA"
REGIME_IDENTIFICADO = "REGIME IDENTIFICADO"

# (rótulo, tipos, obrigatório)
CHECKLIST_DOCUMENTAL = [
    ("Termo de Convênio", ["TERMO_CONVENIO"], True),
    ("Plano de Trabalho", ["PLANO_TRABALHO"], True),
    ("Termos aditivos / apostilamentos", ["TERMO_ADITIVO"], False),
    ("Publicação", ["PUBLICACAO"], False),
    ("Prestação de contas final (demonstrativo de execução)", ["EXECUCAO_FISICO_FINANCEIRA"], True),
    ("Ofício de encaminhamento", ["OFICIO"], True),
    ("Processo licitatório", ["LICITACAO"], True),
    ("Contratos", ["CONTRATO"], True),
    ("Ordens de serviço", ["ORDEM_SERVICO"], True),
    ("Notas fiscais", ["NOTA_FISCAL"], True),
    ("Recibos", ["RECIBO"], False),
    ("Comprovantes de pagamento", ["COMPROVANTE_PAGAMENTO", "COPIA_CHEQUE"], True),
    ("Extratos bancários", ["EXTRATOS"], True),
    ("Medições", ["MEDICAO"], False),
    ("Relatório fotográfico", ["RELATORIO_FOTOGRAFICO"], False),
    ("ART/RRT", ["ART"], False),
    ("Termo de recebimento da obra", ["TERMO_RECEBIMENTO"], False),
    ("Parecer Técnico / Relatório de Vistoria", ["PARECER_TECNICO"], True),
    ("Notificações / diligências", ["NOTIFICACAO"], False),
    ("DAE / comprovantes de devolução", ["DAE_DEVOLUCAO"], False),
    ("Conciliação financeira", ["CONCILIACAO"], False),
    ("Conhecimentos de receita (rendimentos)", ["CONHECIMENTO_RECEITA"], False),
]


def _docs(por_tipo: Dict[str, List[Documento]], *tipos: str) -> List[Documento]:
    out: List[Documento] = []
    for t in tipos:
        out.extend(por_tipo.get(t, []))
    return out


def _locs(docs: List[Documento], limite: int = 4) -> str:
    if not docs:
        return "—"
    s = "; ".join(f"{d.id} ({d.localizacao})" for d in docs[:limite])
    return s + (f"; +{len(docs) - limite} documento(s)" if len(docs) > limite else "")


def _item(item: str, resultado: str, docs: str, loc: str, obs: str) -> Dict[str, str]:
    return {"item": item, "resultado": resultado, "documento": docs, "localizacao": loc, "observacao": obs}


def _ocorr(ocorrencias: List[Dict], item: str) -> List[Dict]:
    return [o for o in ocorrencias if o["item"] == item]


def _resultado(ocorrencias_item: List[Dict]) -> str:
    """Irregularidade/inconsistência gera ressalva; falta de informação gera pendência, não ressalva."""
    if any(o["categoria"] in ("a", "c", "d", "e", "f") for o in ocorrencias_item):
        return RESSALVAS
    if ocorrencias_item:
        return PENDENTE
    return ATENDE


def _cnpj(s: Optional[str]) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def montar_checklist(por_tipo: Dict[str, List[Documento]], docs: List[Documento]) -> List[Dict[str, Any]]:
    tem_aplicacao = any(d.subtipos.get("EXTRATO_APLICACAO") for d in docs)
    linhas = []
    for rotulo, tipos, obrigatorio in CHECKLIST_DOCUMENTAL:
        achados = _docs(por_tipo, *tipos)
        linhas.append({
            "documento": rotulo,
            "obrigatorio": obrigatorio,
            "situacao": "LOCALIZADO" if achados else (NAO_CONSTA if obrigatorio else "NÃO LOCALIZADO (pode não se aplicar)"),
            "referencias": [f"{d.id} – {d.localizacao}" for d in achados][:12],
            "quantidade": len(achados),
        })
    linhas.insert(13, {
        "documento": "Comprovantes de aplicação financeira",
        "obrigatorio": True,
        "situacao": "LOCALIZADO" if tem_aplicacao else NAO_CONSTA,
        "referencias": [f"{d.id} – {d.localizacao}" for d in docs if d.subtipos.get("EXTRATO_APLICACAO")][:12],
        "quantidade": sum(d.subtipos.get("EXTRATO_APLICACAO", 0) for d in docs),
    })
    return linhas


def montar_relatorio(
    docs: List[Documento],
    convenio: Dict[str, Any],
    cruz: Dict[str, Any],
) -> Dict[str, Any]:
    ativos = [d for d in docs if not d.duplicado_de]
    por_tipo: Dict[str, List[Documento]] = {}
    for d in ativos:
        por_tipo.setdefault(d.tipo, []).append(d)
    ocorrencias: List[Dict] = list(cruz["ocorrencias"])
    itens: List[Dict[str, str]] = []

    # 1. Regime jurídico
    regime_info = determinar_regime(convenio, ativos, cruz["vigencia"]["inicio"])
    regime = regime_de(regime_info)
    obs_regime = regime_info["motivo"]
    if regime_info["citacoes_concordantes"]:
        obs_regime += " Os documentos citam a mesma norma: " + "; ".join(
            f"{c['norma']} em {c['localizacao']}" for c in regime_info["citacoes_concordantes"][:3]) + "."
    if regime_info["citacoes_conflitantes"]:
        obs_regime += " ATENÇÃO – há citação de outra norma: " + "; ".join(
            f"{c['norma']} em {c['localizacao']}" for c in regime_info["citacoes_conflitantes"][:3]) + f". {PENDENTE_HUMANO}"
    if regime and not regime.norma_carregada:
        obs_regime += " Regras específicas não verificadas automaticamente."
    parcelas = parcelas_repasse(cruz, regime)
    if parcelas:
        obs_regime += " " + parcelas
    obs_regime += " O TCT/termo do convênio pode conter cláusulas específicas que prevalecem e devem ser conferidas."
    regime_seguro = regime is not None and regime.norma_carregada and regime_info["confianca"] == "alta" \
        and not regime_info["citacoes_conflitantes"]
    itens.append(_item(
        "Regime jurídico", REGIME_IDENTIFICADO if regime_seguro else PENDENTE,
        "Data de celebração / legislação aplicável", regime_info["fonte"] or _locs(_docs(por_tipo, "TERMO_CONVENIO")),
        f"{regime_info['nome']}. {obs_regime}"))
    ocorrencias.extend(aplicar_regras(regime, convenio, por_tipo, cruz))
    fundamentar(ocorrencias, regime)

    # 2. Prazo
    oficios = _docs(por_tipo, "OFICIO")
    ofi = oficios[0].extracao if oficios else {}
    data_protocolo = parse_date(valor_campo(ofi, "data_protocolo"))
    data_oficio = parse_date(valor_campo(ofi, "data"))
    fonte_apres = fonte_campo(ofi, "data_protocolo") if data_protocolo else fonte_campo(ofi, "data")
    nota_protocolo = ""
    if data_protocolo and data_oficio and data_protocolo < data_oficio:
        nota_protocolo = (f" Data de protocolo lida ({data_protocolo.strftime('%d/%m/%Y')}) é anterior à do ofício "
                          f"({data_oficio.strftime('%d/%m/%Y')}); considerada a data do ofício. {PENDENTE_HUMANO}")
        data_protocolo, fonte_apres = None, fonte_campo(ofi, "data")
    data_apres = data_protocolo or data_oficio
    vig_fim = parse_date(cruz["vigencia"]["fim"])
    if not oficios:
        res, obs = NAO_CONSTA, "Ofício/protocolo de apresentação da prestação de contas não localizado."
        outros = _docs(por_tipo, "OFICIO_SOLICITACAO", "CORRESPONDENCIA")
        if outros:
            obs += (f" Há {len(outros)} ofício(s)/correspondência(s) que não tratam do encaminhamento da prestação "
                    f"de contas e não foram usados para o prazo: {_locs(outros)}.")
    elif not vig_fim or not data_apres:
        res = PENDENTE
        obs = (f"Fim da vigência: {cruz['vigencia']['fim'] or 'não identificado'}; data de apresentação: "
               f"{data_apres.strftime('%d/%m/%Y') if data_apres else 'não identificada'}. {NAO_IDENTIFICADO}{nota_protocolo}")
    else:
        dias = (data_apres - vig_fim).days
        quando = f"{dias} dias após o fim da vigência" if dias >= 0 else f"{-dias} dias antes do fim da vigência"
        base_apres = "protocolo" if data_protocolo else "data do ofício (o recebimento pelo concedente deve ser conferido)"
        obs = (f"Vigência encerrada em {vig_fim.strftime('%d/%m/%Y')} [{cruz['vigencia']['fonte'] or '—'}]; apresentação em "
               f"{data_apres.strftime('%d/%m/%Y')} pela {base_apres} [{fonte_apres or oficios[0].localizacao}] — {quando}.")
        limite = data_limite_pc(regime, vig_fim)
        if limite:
            fund_prazo = regime.fundamentos["prazo_pc"]
            if regime is DEC_46319 and limite < REDACAO_46831:
                fund_prazo += "; prazo vencido antes de 14/9/2015 – conferir a redação original do art. 54, § 3º"
            atraso = (data_apres - limite).days
            obs += f" Prazo legal: {regime.prazo_pc_dias} dias ({fund_prazo}), limite em {limite.strftime('%d/%m/%Y')}."
            if atraso > 0:
                res = RESSALVAS
                obs += f" Apresentada com {atraso} dia(s) de atraso."
                ocorrencias.append({
                    "categoria": "a", "categoria_nome": "Irregularidade formal sem dano identificado",
                    "item": "Prazo da prestação de contas", "titulo": "Prestação de contas apresentada fora do prazo",
                    "descricao": (f"Limite {limite.strftime('%d/%m/%Y')}; apresentação em {data_apres.strftime('%d/%m/%Y')} "
                                  f"({base_apres}) – {atraso} dia(s) de atraso."),
                    "valor": None, "fontes": [fonte_apres or oficios[0].localizacao, cruz["vigencia"]["fonte"]],
                    "fundamento": fund_prazo})
            elif data_protocolo:
                res = ATENDE
                obs += " Apresentada dentro do prazo."
            else:
                res = PENDENTE
                obs += " Dentro do prazo pela data do ofício; confirmar a data de recebimento."
        else:
            res = PENDENTE
            obs += " Prazo legal não verificado: regime não identificado ou norma não carregada."
        obs += nota_protocolo
    itens.append(_item("Prazo da prestação de contas", res, "Ofício de encaminhamento / protocolo", _locs(oficios), obs))

    # 3. Licitação
    lic_docs = _docs(por_tipo, "LICITACAO")
    contratos = _docs(por_tipo, "CONTRATO")
    lv = cruz.get("licitacao_varredura") or {}
    if not lic_docs and not lv.get("processo"):
        itens.append(_item("Processo licitatório", NAO_CONSTA, "Processo licitatório", "—", NAO_IDENTIFICADO))
    else:
        lic = (lic_docs[0].extracao or {}) if lic_docs else {}
        ctr = contratos[0].extracao if contratos else {}
        cnpjs = {
            "vencedor": _cnpj(valor_campo(lic, "cnpj_vencedor", aceitar_nao_confirmado=False)),
            "contratada": _cnpj(valor_campo(ctr, "cnpj_contratada", aceitar_nao_confirmado=False)),
        }
        emitentes = {_cnpj(n.get("cnpj")) for n in cruz["notas_fiscais"] if n.get("cnpj")}
        divergencias = []
        if cnpjs["vencedor"] and cnpjs["contratada"] and cnpjs["vencedor"] != cnpjs["contratada"]:
            divergencias.append("CNPJ do vencedor difere do CNPJ da contratada")
        base = cnpjs["contratada"] or cnpjs["vencedor"]
        if base and emitentes and any(e and e != base for e in emitentes):
            divergencias.append("há nota fiscal emitida por CNPJ diferente do contratado")
        resumo = (f"Modalidade: {valor_campo(lic, 'modalidade') or '—'}; processo: {valor_campo(lic, 'numero_processo') or '—'}; "
                  f"vencedor: {valor_campo(lic, 'vencedor') or '—'}; valor adjudicado: {fmt_money(valor_campo(lic, 'valor_adjudicado'))}; "
                  f"homologação: {valor_campo(lic, 'data_homologacao') or '—'}. Contrato: "
                  f"{valor_campo(ctr, 'numero') or ('localizado' if contratos else 'NÃO CONSTA')}, valor {fmt_money(valor_campo(ctr, 'valor'))}.")
        if lv.get("processo"):
            resumo = f"Varredura do processo: {resumo_licitacao(lv)}. Extração por documento: " + resumo
        total_nf = cruz.get("total_notas_fiscais")
        if lv.get("valor_contrato") and total_nf and total_nf > lv["valor_contrato"] + 1:
            divergencias.append(f"total das notas fiscais ({fmt_money(total_nf)}) supera o valor do contrato "
                                f"({fmt_money(lv['valor_contrato'])})")
        if divergencias:
            for dv in divergencias:
                ocorrencias.append({"categoria": "c", "categoria_nome": "Inconsistência financeira", "item": "Processo licitatório",
                                    "titulo": "Incompatibilidade entre contratado e emissor/vencedor", "descricao": dv,
                                    "valor": None, "fontes": [d.localizacao for d in lic_docs + contratos][:4]})
            res = RESSALVAS
        elif lv.get("processo") and lv.get("contrato"):
            res = ATENDE
        else:
            res = PENDENTE
        itens.append(_item("Processo licitatório", res, "Licitação / contrato", _locs(lic_docs + contratos),
                           resumo + " Regularidade do procedimento depende de conferência do analista conforme o regime jurídico."))

    # 4. Ordem de serviço
    os_docs = _docs(por_tipo, "ORDEM_SERVICO")
    os_paginas = lv.get("ordem_servico_paginas") or []
    if not os_docs and not os_paginas:
        itens.append(_item("Ordem de serviço", NAO_CONSTA, "Ordem de serviço", "—", NAO_IDENTIFICADO))
    elif not os_docs:
        itens.append(_item("Ordem de serviço", ATENDE, "Ordem de serviço",
                           "; ".join(f"{a}, p. {p}" for a, p in os_paginas[:3]),
                           "Ordem de serviço localizada pela varredura do texto (página classificada com outro tipo)."))
    else:
        e = os_docs[0].extracao or {}
        itens.append(_item("Ordem de serviço", ATENDE, "Ordem de serviço", _locs(os_docs),
                           f"Emissão {valor_campo(e, 'data_emissao') or '—'}; início autorizado {valor_campo(e, 'data_inicio') or '—'}; "
                           f"contratada {valor_campo(e, 'contratada') or '—'}. Conferir compatibilidade com contrato e vigência."))

    # 5. Comprovantes de despesas
    notas = cruz["notas_fiscais"]
    oc_desp = _ocorr(ocorrencias, "Comprovantes de despesas")
    contas = _docs(por_tipo, "CONTA_CONSUMO")
    obs_contas = (f" {len(contas)} conta(s) de energia/água/telefone ({_locs(contas)}) não foram tratadas como despesa "
                  f"do convênio (em geral são comprovante de endereço); se o objeto prevê esse gasto, incluir manualmente."
                  if contas else "")
    if not notas:
        itens.append(_item("Comprovantes de despesas", NAO_CONSTA, "Notas fiscais", "—", NAO_IDENTIFICADO + obs_contas))
    else:
        pagas = sum(1 for n in notas if n["pagamento"])
        sem_guia = cruz.get("notas_sem_guia") or []
        res_desp = _resultado(oc_desp)
        if sem_guia and res_desp in (ATENDE, PENDENTE):
            res_desp = RESSALVAS
        itens.append(_item(
            "Comprovantes de despesas", res_desp, "Notas fiscais / comprovantes",
            _locs(_docs(por_tipo, "NOTA_FISCAL")),
            f"{len(notas)} nota(s) fiscal(is) (cópias entre volumes contadas uma vez), total bruto "
            f"{fmt_money(cruz['total_notas_fiscais'])}; {pagas} com pagamento localizado. "
            + (f"Sem guia de recolhimento das retenções: NF {', '.join(sem_guia)}. " if sem_guia else "")
            + f"{len(oc_desp)} ocorrência(s).{obs_contas}"))

    # 6. Movimentação bancária
    extratos = _docs(por_tipo, "EXTRATOS")
    oc_banco = _ocorr(ocorrencias, "Movimentação bancária")
    ctrl = cruz["controle"]
    if not extratos:
        itens.append(_item("Movimentação bancária", NAO_CONSTA, "Extratos bancários", "—", NAO_IDENTIFICADO))
    else:
        conferido = bool(ctrl["memoria"] and ctrl["despesas_notas_fiscais"]
                         and ctrl["saldo_final_extrato_aplicacao"] is not None)
        res_banco = _resultado(oc_banco) if oc_banco or conferido else PENDENTE
        ult = cruz.get("extrato_cc_ultimo") or {}
        extrato_aberto = bool(ult and (ult.get("saldo") is None or abs(ult["saldo"]) > 0.01))
        motivos_na = []
        if cruz.get("devolucao_pendente"):
            motivos_na.append(f"saldo residual de {fmt_money(cruz['residual'])} sem comprovante de devolução")
        if extrato_aberto and cruz.get("devolucao_pendente"):
            motivos_na.append(f"extratos apresentados só até {ult.get('data')}, sem chegar ao saldo zerado")
        if motivos_na:
            res_banco = NAO_ATENDE
            for m in motivos_na:
                ocorrencias.append({"categoria": "b", "categoria_nome": "Pendência documental", "item": "Movimentação bancária",
                                    "titulo": m[0].upper() + m[1:], "descricao": m[0].upper() + m[1:] + ".",
                                    "valor": cruz.get("residual") if "residual" in m else None,
                                    "fontes": [ult.get("localizacao") or ""]})
        itens.append(_item(
            "Movimentação bancária", res_banco, "Extratos de conta corrente e aplicação",
            _locs(extratos),
            f"{sum(d.subtipos.get('EXTRATO_CC', 0) for d in extratos)} página(s) de conta corrente e "
            f"{sum(d.subtipos.get('EXTRATO_APLICACAO', 0) for d in extratos)} de aplicação. "
            f"Fórmula de controle: {ctrl['memoria'] or 'dados insuficientes'}. "
            + (f"Não atende: {'; '.join(motivos_na)}. " if motivos_na else "")
            + f"{len(oc_banco)} ocorrência(s)."))

    # 7. Contrapartida
    cp = cruz["contrapartida"]
    oc_cp = _ocorr(ocorrencias, "Contrapartida")
    if not cp:
        itens.append(_item("Contrapartida", NAO_CONSTA, "Termo / demonstrativo", "—", NAO_IDENTIFICADO))
    else:
        if oc_cp:
            res = _resultado(oc_cp)
        elif cp["pactuada"] is not None and cp["declarada_executada"] is not None:
            res = ATENDE
        else:
            res = PENDENTE
        itens.append(_item(
            "Contrapartida", res, "Termo de Convênio / demonstrativo", cp.get("pactuada_fonte") or "—",
            f"Pactuada {fmt_money(cp['pactuada'])}; declarada {fmt_money(cp['declarada_executada'])}; "
            f"concedente {cp['percentual_concedente'] or '—'}% / convenente {cp['percentual_convenente'] or '—'}%. "
            f"{cp['memoria_calculo'] or ''} Aporte efetivo em conta deve ser confirmado nos extratos."))

    # 8. Aplicações/rendimentos
    ext = cruz["extratos_aplicacao"]
    oc_rend = _ocorr(ocorrencias, "Aplicações/rendimentos")
    if not ext["meses"]:
        itens.append(_item("Aplicações/rendimentos", NAO_CONSTA, "Extratos de aplicação", "—", NAO_IDENTIFICADO))
    else:
        itens.append(_item(
            "Aplicações/rendimentos", _resultado(oc_rend), "Extratos de aplicação",
            f"{ext['serie'][0]['localizacao']} a {ext['serie'][-1]['localizacao']}",
            f"{ext['meses']} mês(es) lidos; rendimentos líquidos somados {fmt_money(ext['rendimentos_liquidos_total'])}; "
            f"declarados {fmt_money(ext['rendimentos_declarados'])}; {ext['quebras_continuidade']} quebra(s) de continuidade."))

    # 9/10. Parecer técnico e irregularidades técnicas
    pareceres = _docs(por_tipo, "PARECER_TECNICO")
    if not pareceres:
        acomp = _docs(por_tipo, "NOTA_TECNICA_ACOMPANHAMENTO")
        obs_acomp = (f" Localizada(s) {len(acomp)} nota(s) técnica(s)/vistoria(s) de celebração ou fase intermediária "
                     f"({_locs(acomp)}), que não substituem o Parecer Técnico final." if acomp else "")
        itens.append(_item("Parecer Técnico", NAO_CONSTA, "Parecer Técnico / Relatório de Vistoria", "—",
                           NAO_IDENTIFICADO + " A execução física não pode ser declarada sem o Parecer Técnico." + obs_acomp))
        itens.append(_item("Irregularidades técnicas", NAO_CONSTA, "Parecer Técnico", "—",
                           "Dependem do Parecer Técnico, não localizado."))
        ocorrencias.append({"categoria": "g", "categoria_nome": "Depende de manifestação técnica", "item": "Parecer Técnico",
                            "titulo": "Parecer Técnico não localizado",
                            "descricao": "Conclusão sobre execução física depende de manifestação técnica.", "valor": None, "fontes": []})
    else:
        e = pareceres[0].extracao or {}
        itens.append(_item("Parecer Técnico", PENDENTE, "Parecer Técnico", _locs(pareceres),
                           f"Conclusão (transcrição): {valor_campo(e, 'conclusao') or NAO_IDENTIFICADO} "
                           f"Execução: {valor_campo(e, 'percentual_execucao') or '—'}."))
        glosas = valor_campo(e, "glosas_ou_irregularidades")
        conclusao = valor_campo(e, "conclusao")
        if glosas:
            res_tec, obs_tec = PENDENTE, glosas
        elif conclusao:
            res_tec, obs_tec = ATENDE, "Nenhuma irregularidade técnica citada no parecer lido."
        else:
            res_tec = PENDENTE
            obs_tec = f"Conclusão do parecer não foi lida com segurança; não é possível afirmar ausência de irregularidades. {PENDENTE_HUMANO}"
        itens.append(_item("Irregularidades técnicas", res_tec, "Parecer Técnico", _locs(pareceres), obs_tec))

    # 11. Irregularidades financeiras
    fin = [o for o in ocorrencias if o["categoria"] in ("c", "e", "f")]
    itens.append(_item(
        "Irregularidades financeiras", RESSALVAS if fin else ATENDE, "Cruzamentos automáticos", "ver ocorrências",
        f"{len(fin)} inconsistência(s) financeira(s) para validação." if fin else
        "Nenhuma inconsistência financeira identificada nos documentos lidos."))

    # 12. Devoluções
    devol = cruz["devolucoes"]
    if not devol:
        itens.append(_item("Devoluções", NAO_CONSTA, "DAE / comprovante", "—", "Nenhum DAE/comprovante de devolução localizado."))
    else:
        nao_comp = [d for d in devol if d["valor"] is not None and not d["comprovada"]]
        sem_valor = [d for d in devol if d["valor"] is None]
        res_devol = RESSALVAS if nao_comp else (PENDENTE if sem_valor else ATENDE)
        itens.append(_item(
            "Devoluções", res_devol, "DAE / comprovante",
            "; ".join(d["localizacao"] for d in devol),
            "; ".join(
                f"{d['localizacao']}: valor não legível no documento – {PENDENTE_HUMANO}" if d["valor"] is None else
                f"{fmt_money(d['valor'])} ({d['natureza'] or 'natureza não identificada'}) – "
                f"{'pagamento comprovado' if d['comprovada'] else 'pagamento não comprovado'}" for d in devol)))

    # 13. Saldo
    oc_saldo = _ocorr(ocorrencias, "Saldo")
    if ctrl["saldo_apurado"] is None:
        itens.append(_item("Saldo", PENDENTE, "Fórmula de controle", "—",
                           "Dados insuficientes para apurar o saldo (repasse não identificado com segurança)."))
    else:
        faltas = []
        if not ctrl["despesas_notas_fiscais"]:
            faltas.append("nenhuma despesa (nota fiscal) lida")
        if ctrl["saldo_final_extrato_aplicacao"] is None:
            faltas.append("saldo final de extrato não lido")
        res_saldo = _resultado(oc_saldo) if oc_saldo else (PENDENTE if faltas else ATENDE)
        obs_saldo = (f"Saldo apurado {fmt_money(ctrl['saldo_apurado'])}; último saldo de aplicação "
                     f"{fmt_money(ctrl['saldo_final_extrato_aplicacao'])}.")
        if faltas and not oc_saldo:
            obs_saldo += f" Não conferível: {'; '.join(faltas)}. {PENDENTE_HUMANO}"
        itens.append(_item(
            "Saldo", res_saldo, "Fórmula de controle × extratos", ctrl["saldo_final_localizacao"] or "—", obs_saldo))

    # Checklist documental
    if regime and regime.documentos:
        checklist = montar_checklist_regime(regime, por_tipo, ativos, eh_obra(convenio, por_tipo))
    else:
        checklist = montar_checklist(por_tipo, docs)
    for linha in checklist:
        if linha["situacao"] == NAO_CONSTA:
            ocorrencias.append({"categoria": "b", "categoria_nome": "Pendência documental", "item": "Inventário documental",
                                "titulo": f"{linha['documento']} não localizado", "descricao": NAO_IDENTIFICADO,
                                "valor": None, "fontes": [], "fundamento": linha.get("fundamento", "")})

    # Campos extraídos pela IA que não passaram na conferência de trecho
    nao_conf = []
    for origem, campos in [("Dados do convênio", convenio)] + [(f"{d.id} {d.nome}", d.extracao) for d in ativos if d.extracao]:
        for nome, info in (campos or {}).items():
            if info.get("status") in ("trecho_nao_localizado", "valor_nao_consta_no_trecho"):
                nao_conf.append(f"{origem}: campo '{nome}' = {info.get('valor')} ({info['status'].replace('_', ' ')})")

    vistos, unicas = set(), []
    for o in ocorrencias:
        chave = (o["categoria"], o["titulo"], o["descricao"])
        if chave not in vistos:
            vistos.add(chave)
            unicas.append(o)
    ocorrencias = unicas

    pendencias = [o for o in ocorrencias if o["categoria"] == "b"]
    ressalvas = [o for o in ocorrencias if o["categoria"] == "a"]
    danos = [o for o in ocorrencias if o["categoria"] in ("e", "f")]
    validacao = [o for o in ocorrencias if o["categoria"] in ("c", "d", "g", "h", "i", "j")]
    validacao_extra = [i["item"] + ": " + i["observacao"] for i in itens if i["resultado"] == PENDENTE]

    qa = [
        {"pergunta": "Todos os valores foram recalculados?", "resposta": "Sim – aritmética feita pelo sistema, não pela IA."},
        {"pergunta": "Receitas menos despesas correspondem ao saldo?",
         "resposta": "Sem divergência" if ctrl["saldo_apurado"] is not None and not oc_saldo else
         ("Divergência apontada" if oc_saldo else "Dados insuficientes")},
        {"pergunta": "Notas fiscais correspondem aos pagamentos?",
         "resposta": f"{sum(1 for n in notas if n['pagamento'])}/{len(notas)} com pagamento localizado" if notas else "Sem NF"},
        {"pergunta": "Pagamentos correspondem aos débitos bancários?",
         "resposta": f"{len([o for o in oc_banco if 'sem nota' in o['titulo'].lower()])} pagamento(s) sem NF identificada"},
        {"pergunta": "Contrapartida foi conferida?", "resposta": "Sim" if cp else "Dados não localizados"},
        {"pergunta": "Vigência foi conferida?", "resposta": "Sim" if cruz["vigencia"]["fim"] else "Vigência não identificada"},
        {"pergunta": "Prazo da prestação de contas foi calculado?",
         "resposta": ("Sim – prazo legal do regime aplicado" if data_limite_pc(regime, vig_fim) and data_apres else
                      "Dias decorridos calculados; prazo legal não aplicado") if vig_fim and data_apres else "Não – dados ausentes"},
        {"pergunta": "Parecer Técnico foi corretamente reproduzido?", "resposta": "Transcrito para conferência" if pareceres else "Parecer não localizado"},
        {"pergunta": "Devoluções foram comprovadas?",
         "resposta": ("Sim" if devol and all(d["comprovada"] for d in devol) else "Parcialmente/Não") if devol else "Sem devoluções localizadas"},
        {"pergunta": "Dispositivos legais pertencem ao regime correto?",
         "resposta": (f"Sim – fundamentos citados de: {regime.nome}" if regime and regime.norma_carregada else
                      "Não verificável – regime não identificado ou norma não carregada")},
        {"pergunta": "Todas as informações não comprovadas foram sinalizadas?",
         "resposta": f"Sim – {len(nao_conf)} campo(s) extraído(s) sem conferência literal sinalizado(s)"},
    ]

    return {
        "regime": regime_info,
        "itens": itens,
        "checklist_documental": checklist,
        "ocorrencias": ocorrencias,
        "pendencias_documentais": pendencias,
        "ressalvas_sem_dano": ressalvas,
        "possiveis_danos": danos,
        "questoes_validacao_humana": validacao,
        "itens_pendentes_validacao": validacao_extra,
        "campos_nao_confirmados": nao_conf,
        "controle_qualidade": qa,
        "aviso": ("Minuta técnica de apoio gerada automaticamente. Não substitui a análise do analista, "
                  "da área técnica, da Controladoria ou da assessoria jurídica."),
    }
