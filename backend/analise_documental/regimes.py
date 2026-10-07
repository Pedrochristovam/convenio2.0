"""
Regimes jurídicos dos convênios de saída do Estado de Minas Gerais.

Cada regime reúne as regras verificáveis automaticamente (prazos, vedações,
documentos exigidos) com o dispositivo legal correspondente. A determinação do
regime segue o art. 82 c/c art. 87 do Decreto nº 46.319/2013: aplica-se aos
convênios celebrados a partir de 1º/8/2014; os anteriores seguem o Decreto
nº 43.635/2003 (revogado pelo art. 86, I, do Decreto nº 46.319/2013).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from backend.analise_documental.cruzamentos import CATEGORIAS
from backend.analise_documental.extratores import fonte_campo, valor_campo
from backend.analise_documental.inventario import Documento
from backend.analise_documental.texto import PENDENTE_HUMANO, fmt_date, fmt_money, norm, parse_date

INICIO_46319 = date(2014, 8, 1)
INICIO_48745 = date(2023, 12, 31)
PUBLICACAO_RES_004 = date(2015, 9, 16)
REDACAO_46831 = date(2015, 9, 14)

OBRA_RE = re.compile(r"\bOBRAS?\b|PAVIMENT|ASFALT|REFORMA|CONSTRU[CÇ]|ENGENHARIA|RECAPEAMENTO|CALCAMENTO|DRENAGEM")


@dataclass(frozen=True)
class ItemDocumental:
    rotulo: str
    tipos: Tuple[str, ...]
    fundamento: str
    obrigatorio: bool = True
    anexo: Optional[str] = None
    somente_obra: bool = False
    nota: str = ""


@dataclass(frozen=True)
class Regime:
    codigo: str
    nome: str
    normas: Tuple[str, ...]
    prazo_pc_dias: Optional[int]
    fundamentos: Dict[str, str]
    documentos: Tuple[ItemDocumental, ...] = field(default_factory=tuple)
    prazo_devolucao_dias: Optional[int] = None
    pagamento_pos_vigencia_admitido: bool = False
    nf_identifica: str = ""
    vigencia_max_meses: Optional[int] = None
    norma_carregada: bool = True


DEC_43635 = Regime(
    codigo="DEC_43635",
    nome="Decreto nº 43.635/2003 (com as alterações do Decreto nº 44.631/2007)",
    normas=("Decreto nº 43.635, de 20/10/2003", "Lei Federal nº 8.666/1993", "Lei Federal nº 4.320/1964"),
    prazo_pc_dias=60,
    nf_identifica="nome do convenente e número do convênio",
    fundamentos={
        "prazo_pc": "art. 26, § 5º, e art. 12, IV, do Decreto nº 43.635/2003 (até 60 dias após o término da vigência)",
        "despesa_fora_vigencia": "art. 15, V, e art. 17, parágrafo único, do Decreto nº 43.635/2003 (despesas fora da vigência devem ser glosadas)",
        "pagamento_pos_vigencia": "art. 15, V, e art. 17, parágrafo único, do Decreto nº 43.635/2003 (vedada despesa posterior à vigência; não há exceção para fato gerador anterior)",
        "tarifas": "art. 15, VII, do Decreto nº 43.635/2003 (vedadas despesas com taxas bancárias, multas, juros ou atualização monetária)",
        "rendimentos": "art. 25, §§ 2º e 3º, do Decreto nº 43.635/2003 (rendimentos aplicados no objeto e não computáveis como contrapartida)",
        "aplicacao": "art. 25, § 1º, do Decreto nº 43.635/2003 (saldos aplicados em poupança ou fundo de curto prazo)",
        "movimentacao": "art. 25, caput e § 4º, do Decreto nº 43.635/2003 (cheque nominativo/ordem de pagamento; vedada movimentação em espécie)",
        "contrapartida": "art. 12, XIV, do Decreto nº 43.635/2003 (recolher o valor atualizado da contrapartida pactuada não comprovada) e art. 26, § 4º (comprovação no Relatório de Execução Físico-Financeira)",
        "devolucao": "art. 12, XII, e art. 26, XV, do Decreto nº 43.635/2003 (restituição do saldo, inclusive rendimentos, por DAE)",
        "documento_fiscal": "art. 27 do Decreto nº 43.635/2003 (documentos em nome do convenente, identificados com o nome do convenente e o número do convênio)",
        "parcelas": "art. 31, §§ 1º e 2º, do Decreto nº 43.635/2003",
        "fotografias": "art. 21, parágrafo único, do Decreto nº 43.635/2003",
        "aprovacao": "arts. 29 e 30 do Decreto nº 43.635/2003",
        "saldo": "art. 12, XII, do Decreto nº 43.635/2003",
        "extratos": "art. 26, II, do Decreto nº 43.635/2003 (extratos da conta específica desde a 1ª parcela até o último)",
        "demonstrativo": "art. 26, III, do Decreto nº 43.635/2003 (demonstrativo de receita e despesa com recursos recebidos, contrapartida, rendimentos e saldos)",
    },
    documentos=(
        ItemDocumental("Ofício de encaminhamento", ("OFICIO",), "art. 26, I", anexo="II"),
        ItemDocumental("Conciliação bancária", ("CONCILIACAO",), "art. 26, II", anexo="III"),
        ItemDocumental("Extratos da conta específica (desde a 1ª parcela)", ("EXTRATO_CC",), "art. 26, II"),
        ItemDocumental("Extratos de aplicação financeira", ("EXTRATO_APLICACAO",), "art. 25, § 1º"),
        ItemDocumental("Demonstrativo de execução de receita e despesa", ("EXECUCAO_FISICO_FINANCEIRA",), "art. 26, III", anexo="IV"),
        ItemDocumental("Cópia de cheque ou comprovante de pagamento", ("COPIA_CHEQUE", "COMPROVANTE_PAGAMENTO"), "art. 26, IV", anexo="V"),
        ItemDocumental("Relação de pagamentos", ("RELACAO_PAGAMENTOS",), "art. 26, V", anexo="VI"),
        ItemDocumental("Demonstrativo de mão de obra própria", (), "art. 26, VI", obrigatorio=False, anexo="VII",
                       nota="exigível quando houver execução direta"),
        ItemDocumental("Demonstrativo de equipamentos utilizados", (), "art. 26, VII", obrigatorio=False, anexo="VIII",
                       nota="exigível quando houver execução direta"),
        ItemDocumental("Relatório de execução físico-financeira", ("EXECUCAO_FISICO_FINANCEIRA",), "art. 26, VIII", anexo="IX"),
        ItemDocumental("Boletim de medição", ("MEDICAO",), "art. 26, IX", anexo="X", somente_obra=True),
        ItemDocumental("Ordem de serviço", ("ORDEM_SERVICO",), "art. 26, X", anexo="XI", somente_obra=True),
        ItemDocumental("Relatório fotográfico", ("RELATORIO_FOTOGRAFICO",), "art. 26, XI, e art. 21, parágrafo único", anexo="XII"),
        ItemDocumental("Adjudicação e homologação da licitação (ou ato de dispensa/inexigibilidade), com publicidade",
                       ("LICITACAO",), "art. 26, XII"),
        ItemDocumental("Termo de aceitação definitiva da obra", ("TERMO_RECEBIMENTO",), "art. 26, XIII", anexo="XIII", somente_obra=True),
        ItemDocumental("Relação de bens permanentes adquiridos/produzidos", (), "art. 26, XIV", obrigatorio=False, anexo="XIV",
                       nota="exigível quando houver bens permanentes"),
        ItemDocumental("DAE de recolhimento de saldo", ("DAE_DEVOLUCAO",), "art. 26, XV", obrigatorio=False,
                       nota="exigível quando houver saldo"),
        ItemDocumental("Notas fiscais / documentos fiscais de despesa", ("NOTA_FISCAL", "RECIBO"), "art. 27"),
        ItemDocumental("Contrato com a executora", ("CONTRATO",), "art. 20 do Decreto nº 43.635/2003 c/c Lei nº 8.666/1993", somente_obra=True),
        ItemDocumental("Termo de Convênio", ("TERMO_CONVENIO",), "art. 12", obrigatorio=False,
                       nota="instrumento de celebração; não integra a lista do art. 26"),
        ItemDocumental("Plano de Trabalho", ("PLANO_TRABALHO",), "art. 2º, II, e art. 3º", obrigatorio=False,
                       nota="instrumento de celebração; não integra a lista do art. 26"),
        ItemDocumental("Termos aditivos", ("TERMO_ADITIVO",), "art. 16", obrigatorio=False),
        ItemDocumental("Parecer Técnico / vistoria", ("PARECER_TECNICO",), "art. 29, § 1º, I", obrigatorio=False,
                       nota="emitido pelo concedente"),
    ),
)

DEC_46319 = Regime(
    codigo="DEC_46319",
    nome="Decreto nº 46.319/2013 e Resolução Conjunta SEGOV/AGE nº 004/2015 (alterada pelas Res. 005/2015 e 006/2017)",
    normas=("Decreto nº 46.319, de 26/9/2013 (vigente a partir de 1º/8/2014)",
            "Resolução Conjunta SEGOV/AGE nº 004, de 16/9/2015", "Lei Federal nº 8.666/1993", "Lei Federal nº 10.520/2002"),
    prazo_pc_dias=90,
    prazo_devolucao_dias=30,
    pagamento_pos_vigencia_admitido=True,
    nf_identifica="nome do concedente e número do convênio",
    vigencia_max_meses=60,
    fundamentos={
        "prazo_pc": "art. 54, § 3º, do Decreto nº 46.319/2013, na redação do Decreto nº 46.831/2015 (até 90 dias após o término da vigência); contagem pelo art. 74 da Res. Conjunta 004/2015",
        "despesa_fora_vigencia": "art. 35, II, a, do Decreto nº 46.319/2013 (vedada despesa em data anterior ou posterior à vigência)",
        "pagamento_pos_vigencia": "art. 35, III, a, do Decreto nº 46.319/2013 (pagamento após a vigência só se o fato gerador ocorreu na vigência, com justificativa, aprovação do concedente e dentro do prazo da prestação de contas)",
        "tarifas": "art. 35, II, c, do Decreto nº 46.319/2013 e art. 55, VII, da Res. Conjunta 004/2015 (tarifas bancárias somadas ao saldo a devolver)",
        "rendimentos": "art. 38, §§ 2º a 4º, do Decreto nº 46.319/2013 (rendimentos devolvidos ou aplicados no objeto com justificativa; não computáveis como contrapartida)",
        "aplicacao": "art. 38, § 1º, do Decreto nº 46.319/2013 e art. 60, III e IV, da Res. Conjunta 004/2015",
        "movimentacao": "art. 49, parágrafo único, do Decreto nº 46.319/2013 (cheque nominativo, ordem bancária ou transferência eletrônica identificando o credor)",
        "contrapartida": "art. 20, § 1º, e art. 55, § 4º, do Decreto nº 46.319/2013; arts. 31 e 60, V e § 2º, da Res. Conjunta 004/2015 (depósito até o fim do mês subsequente ao repasse; devolução proporcional)",
        "devolucao": "art. 55, §§ 3º e 4º, do Decreto nº 46.319/2013 (saldos devolvidos em até 30 dias após a vigência, observada a proporcionalidade) e art. 58 da Res. Conjunta 004/2015",
        "documento_fiscal": "art. 55, § 1º, do Decreto nº 46.319/2013 (documentos em nome do convenente, identificados com o nome do concedente e o número do convênio) e art. 55, § 5º, da Res. Conjunta 004/2015",
        "parcelas": "arts. 39 e 40 do Decreto nº 46.319/2013",
        "licitacao": "art. 50, § 1º, do Decreto nº 46.319/2013 e arts. 44 e 57 da Res. Conjunta 004/2015",
        "vigencia": "art. 17 do Decreto nº 46.319/2013 (vigência limitada a 60 meses, incluídas as prorrogações)",
        "aprovacao": "art. 61, §§ 1º e 2º, do Decreto nº 46.319/2013 e arts. 60 e 62 da Res. Conjunta 004/2015",
        "tributos": "art. 62, § 1º, da Res. Conjunta 004/2015 (falta de comprovação de recolhimento de tributos gera aprovação com ressalvas)",
        "saldo": "art. 55, § 3º, do Decreto nº 46.319/2013 e art. 55, VII a IX, da Res. Conjunta 004/2015 (extratos até saldo zero)",
        "extratos": "art. 55, VIII e IX, da Res. Conjunta 004/2015 (extratos de conta corrente e de aplicação até saldo zero)",
        "demonstrativo": "art. 55, XII, da Res. Conjunta 004/2015 (demonstrativo de receita e despesa com recursos recebidos, contrapartida, rendimentos e saldos)",
    },
    documentos=(
        ItemDocumental("Ofício de encaminhamento", ("OFICIO",), "Res. 004/2015, art. 55, I"),
        ItemDocumental("Processo de contratação (licitação, adjudicação/homologação, publicidade)", ("LICITACAO",),
                       "Res. 004/2015, art. 55, II, e art. 57, I e II"),
        ItemDocumental("Contrato, publicidade e aditivos", ("CONTRATO",), "Res. 004/2015, art. 57, IV", somente_obra=True),
        ItemDocumental("Ordem de serviço", ("ORDEM_SERVICO",), "Res. 004/2015, art. 55, III", somente_obra=True),
        ItemDocumental("Nota de empenho (redação original) ou declaração de autenticidade (Res. 006/2017)",
                       ("NOTA_EMPENHO", "DECLARACAO"), "Res. 004/2015, art. 55, IV"),
        ItemDocumental("Notas fiscais / documentos fiscais de despesa", ("NOTA_FISCAL", "RECIBO"), "Res. 004/2015, art. 55, V"),
        ItemDocumental("Comprovante de ordem bancária/transferência ou cópia de cheque nominativo",
                       ("COMPROVANTE_PAGAMENTO", "COPIA_CHEQUE"), "Res. 004/2015, art. 55, VI"),
        ItemDocumental("Comprovante de devolução de saldos (DAE)", ("DAE_DEVOLUCAO",), "Res. 004/2015, art. 55, VII", obrigatorio=False,
                       nota="exigível quando houver saldo em conta"),
        ItemDocumental("Extratos da conta corrente específica até saldo zero", ("EXTRATO_CC",), "Res. 004/2015, art. 55, VIII"),
        ItemDocumental("Extratos de aplicação financeira até saldo zero", ("EXTRATO_APLICACAO",), "Res. 004/2015, art. 55, IX"),
        ItemDocumental("Demonstrativos de mão de obra, bens e serviços utilizados", (), "Res. 004/2015, art. 55, X", obrigatorio=False,
                       nota="exigível quando houver execução direta"),
        ItemDocumental("Relação de pagamentos", ("RELACAO_PAGAMENTOS",), "Res. 004/2015, art. 55, XI"),
        ItemDocumental("Demonstrativo de execução de receita e despesa", ("EXECUCAO_FISICO_FINANCEIRA",), "Res. 004/2015, art. 55, XII"),
        ItemDocumental("Relatório de monitoramento de metas final (com fotografias)", ("RELATORIO_FOTOGRAFICO",),
                       "Res. 004/2015, art. 55, XIII e § 4º"),
        ItemDocumental("Boletim de medição final", ("MEDICAO",), "Res. 004/2015, art. 55, XIV", somente_obra=True),
        ItemDocumental("Termo de entrega da obra com laudo técnico", ("TERMO_RECEBIMENTO",), "Res. 004/2015, art. 55, XV", somente_obra=True),
        ItemDocumental("Relação de bens permanentes", (), "Res. 004/2015, art. 55, XVII", obrigatorio=False,
                       nota="exigível quando houver bens permanentes"),
        ItemDocumental("Termo de Convênio", ("TERMO_CONVENIO",), "Decreto 46.319/2013, arts. 26 e 27", obrigatorio=False,
                       nota="instrumento de celebração; não integra a lista do art. 55 da Res. 004/2015"),
        ItemDocumental("Plano de Trabalho", ("PLANO_TRABALHO",), "Decreto 46.319/2013, art. 25", obrigatorio=False,
                       nota="instrumento de celebração"),
        ItemDocumental("Termos aditivos", ("TERMO_ADITIVO",), "Decreto 46.319/2013, art. 51", obrigatorio=False),
        ItemDocumental("Parecer Técnico / vistoria", ("PARECER_TECNICO",), "Decreto 46.319/2013, art. 58, I", obrigatorio=False,
                       nota="emitido pelo concedente"),
    ),
)

DEC_48745 = Regime(
    codigo="DEC_48745",
    nome="Decreto nº 48.745/2023",
    normas=("Decreto nº 48.745, de 29/12/2023 (vigente a partir de 31/12/2023)",),
    prazo_pc_dias=None,
    fundamentos={},
    norma_carregada=False,
)

REGIMES = {r.codigo: r for r in (DEC_43635, DEC_46319, DEC_48745)}

CITACOES = (
    (re.compile(r"43\.?635"), "DEC_43635", "Decreto 43.635/2003"),
    (re.compile(r"44\.?631"), "DEC_43635", "Decreto 44.631/2007 (altera o 43.635/2003)"),
    (re.compile(r"46\.?319"), "DEC_46319", "Decreto 46.319/2013"),
    (re.compile(r"RESOLUCAO CONJUNTA[^\n]{0,30}004"), "DEC_46319", "Resolução Conjunta 004/2015"),
    (re.compile(r"48\.?745"), "DEC_48745", "Decreto 48.745/2023"),
)


def _regime_por_data(d: date) -> Regime:
    if d >= INICIO_48745:
        return DEC_48745
    if d >= INICIO_46319:
        return DEC_46319
    return DEC_43635


def _citacoes(docs: List[Documento]) -> List[Dict[str, str]]:
    achados, vistos = [], set()
    for d in docs:
        texto = norm(d.texto)
        for padrao, codigo, rotulo in CITACOES:
            n = len(padrao.findall(texto))
            if n and (codigo, d.id) not in vistos:
                vistos.add((codigo, d.id))
                achados.append({"regime": codigo, "norma": rotulo, "documento": d.id, "localizacao": d.localizacao,
                                "ocorrencias": n})
    return achados


def _regime_por_citacao(citacoes: List[Dict[str, Any]]) -> Tuple[Optional[Regime], str]:
    """Sem data de celebração: aceita a norma citada com exclusividade ou com ampla predominância."""
    votos: Dict[str, int] = {}
    for c in citacoes:
        votos[c["regime"]] = votos.get(c["regime"], 0) + c["ocorrencias"]
    if not votos:
        return None, ""
    lider, n = max(votos.items(), key=lambda kv: kv[1])
    total = sum(votos.values())
    if len(votos) == 1:
        return REGIMES[lider], "citação normativa nos documentos"
    if n >= 5 and n >= 0.8 * total:
        resumo = "; ".join(f"{REGIMES[k].nome}: {v}" for k, v in sorted(votos.items(), key=lambda kv: -kv[1]))
        return REGIMES[lider], f"citação normativa predominante nos documentos ({resumo} citações)"
    return None, ""


def eh_obra(convenio: Dict[str, Any], por_tipo: Dict[str, List[Documento]]) -> bool:
    textos = [valor_campo(convenio, "objeto") or ""]
    for d in por_tipo.get("LICITACAO", []) + por_tipo.get("CONTRATO", []):
        textos.append(valor_campo(d.extracao or {}, "objeto") or "")
    return bool(por_tipo.get("MEDICAO")) or any(OBRA_RE.search(norm(t)) for t in textos)


def _ano_numero_convenio(numero: Optional[str]) -> Optional[int]:
    m = re.search(r"/\s*(\d{4})\b", str(numero or ""))
    return int(m.group(1)) if m and 1990 <= int(m.group(1)) <= 2100 else None


def determinar_regime(convenio: Dict[str, Any], docs: List[Documento], vigencia_inicio: Optional[str]) -> Dict[str, Any]:
    assinatura = parse_date(valor_campo(convenio, "data_assinatura"))
    status_assinatura = (convenio.get("data_assinatura") or {}).get("status")
    if assinatura:
        data_ref, base = assinatura, "data de assinatura"
        fonte = fonte_campo(convenio, "data_assinatura")
        confianca = "alta" if status_assinatura == "confirmado" else "media"
    elif parse_date(vigencia_inicio):
        data_ref, base, fonte, confianca = parse_date(vigencia_inicio), "início da vigência", None, "media"
    else:
        data_ref = base = fonte = None
        confianca = "baixa"

    citacoes = _citacoes(docs)
    regime = _regime_por_data(data_ref) if data_ref else None
    ano_numero = _ano_numero_convenio(valor_campo(convenio, "numero_convenio"))
    if regime is None and ano_numero and ano_numero not in (2014, 2023):
        # Anos de transição (2014 e 2023) não definem o regime sozinhos
        data_ano = date(ano_numero, 7, 1)
        regime = _regime_por_data(data_ano)
        if regime:
            base, confianca = f"ano do número do convênio ({ano_numero})", "media"
            fonte = fonte_campo(convenio, "numero_convenio")
    if regime is None:
        regime, base_citacao = _regime_por_citacao(citacoes)
        if regime:
            base = base_citacao

    conflitantes = [c for c in citacoes if regime and c["regime"] != regime.codigo]
    concordantes = [c for c in citacoes if regime and c["regime"] == regime.codigo]
    if conflitantes:
        confianca = "baixa" if confianca != "alta" else "media"

    motivo = ""
    if regime and data_ref:
        if regime is DEC_43635:
            motivo = (f"Convênio celebrado em {fmt_date(data_ref)} ({base}), antes de 1º/8/2014: aplica-se o Decreto nº 43.635/2003, "
                      "pois o Decreto nº 46.319/2013 alcança apenas os convênios celebrados a partir de sua vigência (arts. 82 e 87).")
        elif regime is DEC_46319:
            motivo = (f"Convênio celebrado em {fmt_date(data_ref)} ({base}), entre 1º/8/2014 e 30/12/2023: aplica-se o Decreto nº "
                      "46.319/2013 (arts. 82 e 87), regulamentado pela Resolução Conjunta SEGOV/AGE nº 004/2015.")
        else:
            motivo = (f"Convênio celebrado em {fmt_date(data_ref)} ({base}), a partir de 31/12/2023: aplica-se o Decreto nº 48.745/2023, "
                      "que revogou o Decreto nº 46.319/2013. Essa norma ainda não foi carregada na ferramenta.")
    elif regime and base and base.startswith("ano do número"):
        motivo = (f"Data de assinatura não identificada; regime inferido pelo {base}: {regime.nome}. "
                  "Conferir a data de celebração no termo.")
    elif regime:
        motivo = f"Data de celebração não identificada; regime inferido pela {base}."
    else:
        motivo = "Data de celebração não identificada e sem citação normativa conclusiva nos documentos."

    return {
        "codigo": regime.codigo if regime else None,
        "nome": regime.nome if regime else "REGIME JURÍDICO A VALIDAR",
        "normas": list(regime.normas) if regime else [],
        "norma_carregada": bool(regime and regime.norma_carregada),
        "data_referencia": fmt_date(data_ref) if data_ref else None,
        "base": base,
        "fonte": fonte,
        "confianca": confianca,
        "motivo": motivo,
        "citacoes_concordantes": concordantes[:6],
        "citacoes_conflitantes": conflitantes[:6],
    }


def regime_de(info: Dict[str, Any]) -> Optional[Regime]:
    return REGIMES.get(info.get("codigo") or "")


def data_limite_pc(regime: Optional[Regime], vig_fim: Optional[date]) -> Optional[date]:
    """Exclui-se o dia do início e inclui-se o do vencimento, em dias corridos (art. 74 da Res. 004/2015)."""
    if not regime or not regime.prazo_pc_dias or not vig_fim:
        return None
    return vig_fim + timedelta(days=regime.prazo_pc_dias)


def _oc(categoria: str, item: str, titulo: str, descricao: str, valor, fontes, fundamento: str) -> Dict[str, Any]:
    return {"categoria": categoria, "categoria_nome": CATEGORIAS[categoria], "item": item, "titulo": titulo,
            "descricao": descricao, "valor": valor, "fontes": [f for f in fontes if f], "fundamento": fundamento}


FUNDAMENTO_POR_TITULO = (
    ("pagamento após o fim da vigência", "pagamento_pos_vigencia"),
    ("emitida fora da vigência", "despesa_fora_vigencia"),
    ("contrapartida declarada inferior", "contrapartida"),
    ("rendimentos", "rendimentos"),
    ("saldo apurado", "saldo"),
    ("dae não comprovado", "devolucao"),
    ("total do demonstrativo", "demonstrativo"),
    ("pagamento sem nota fiscal", "documento_fiscal"),
    ("pagamento da nf", "movimentacao"),
    ("repasses contabilizados", "parcelas"),
    ("meses sem extrato", "extratos"),
)


def fundamentar(ocorrencias: List[Dict[str, Any]], regime: Optional[Regime]) -> None:
    if not regime or not regime.fundamentos:
        return
    for o in ocorrencias:
        if o.get("fundamento"):
            continue
        titulo = o["titulo"].lower()
        for trecho, chave in FUNDAMENTO_POR_TITULO:
            if trecho in titulo and chave in regime.fundamentos:
                o["fundamento"] = regime.fundamentos[chave]
                break
        if "pagamento após o fim da vigência" in titulo:
            o["descricao"] += (" O regime admite o pagamento se o fato gerador ocorreu na vigência, mediante justificativa e aprovação."
                               if regime.pagamento_pos_vigencia_admitido else
                               " No regime aplicável a despesa posterior à vigência é vedada e deve ser glosada.")


def aplicar_regras(
    regime: Optional[Regime],
    convenio: Dict[str, Any],
    por_tipo: Dict[str, List[Documento]],
    cruz: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Verificações que dependem do regime e que os cruzamentos genéricos não cobrem."""
    if not regime or not regime.fundamentos:
        return []
    f = regime.fundamentos
    out: List[Dict[str, Any]] = []
    vig_ini = parse_date(cruz["vigencia"]["inicio"])
    vig_fim = parse_date(cruz["vigencia"]["fim"])

    tarifas = cruz["evidencias_bancarias"]["tarifas"]
    if tarifas:
        total = round(sum(t["valor"] or 0 for t in tarifas), 2)
        out.append(_oc(
            "c", "Movimentação bancária", "Tarifas bancárias debitadas na conta do convênio",
            f"{len(tarifas)} débito(s) classificados como tarifa, total {fmt_money(total)}. Despesa vedada com recursos do convênio; "
            f"conferir se houve ressarcimento pelo convenente. Leitura de extrato por OCR – {PENDENTE_HUMANO}",
            total, [t["localizacao"] for t in tarifas][:6], f["tarifas"]))

    # Cópias da mesma NF em outros volumes: basta uma delas trazer a identificação do convênio
    por_id = {d.id: d for d in por_tipo.get("NOTA_FISCAL", [])}
    sem_mencao = []
    for n in cruz.get("notas_fiscais") or []:
        copias = [por_id[i] for i in n.get("documentos") or [n["documento"]] if i in por_id]
        if copias and all((d.extracao or {}).get("mencao_convenio", {}).get("status") == "nao_identificado" for d in copias):
            sem_mencao.append((n.get("numero") or n["documento"], copias[0]))
    if sem_mencao:
        out.append(_oc(
            "a", "Comprovantes de despesas", "Documento fiscal sem identificação do convênio",
            f"{len(sem_mencao)} nota(s) fiscal(is) sem menção identificável ao convênio ({regime.nf_identifica} exigidos): "
            + ", ".join(f"NF {num}" for num, _ in sem_mencao[:12]) + f". {PENDENTE_HUMANO}",
            None, [d.localizacao for _, d in sem_mencao][:6], f["documento_fiscal"]))

    if regime.prazo_devolucao_dias and vig_fim:
        limite = vig_fim + timedelta(days=regime.prazo_devolucao_dias)
        for dv in cruz["devolucoes"]:
            data_dv = parse_date(dv.get("data"))
            if data_dv and data_dv > limite:
                out.append(_oc(
                    "c", "Devoluções", "Devolução de saldo após o prazo",
                    f"DAE de {fmt_money(dv['valor'])} com data {fmt_date(data_dv)}; limite {fmt_date(limite)} "
                    f"({regime.prazo_devolucao_dias} dias após o fim da vigência). Pode haver incidência de atualização. {PENDENTE_HUMANO}",
                    dv["valor"], [dv["localizacao"]], f["devolucao"]))

    if regime.vigencia_max_meses and vig_ini and vig_fim:
        meses = (vig_fim.year - vig_ini.year) * 12 + (vig_fim.month - vig_ini.month)
        if meses > regime.vigencia_max_meses:
            out.append(_oc(
                "a", "Prazo da prestação de contas", "Vigência superior ao limite",
                f"Vigência de {fmt_date(vig_ini)} a {fmt_date(vig_fim)} ({meses} meses), acima de {regime.vigencia_max_meses} meses.",
                None, [cruz["vigencia"]["fonte"]], f["vigencia"]))
    return out


def parcelas_repasse(cruz: Dict[str, Any], regime: Optional[Regime]) -> Optional[str]:
    itens = [c for c in cruz.get("conhecimentos_receita", {}).get("itens", []) if c["natureza"] == "repasse" and c["valor"]]
    if not itens:
        return None
    n = len(itens)
    resumo = f"{n} parcela(s) de repasse identificada(s): " + "; ".join(f"{fmt_money(c['valor'])} em {c['data'] or '—'}" for c in itens)
    if regime is DEC_43635:
        regra = (" Até duas parcelas: prestação de contas final globalizada (art. 31, § 2º)." if n <= 2 else
                 " Três ou mais parcelas: exigida prestação de contas parcial para liberar a terceira (art. 31, § 1º) – conferir.")
    elif regime is DEC_46319:
        regra = (" Até duas parcelas: a segunda depende da comprovação da contrapartida e de relatório de monitoramento (art. 39)."
                 if n <= 2 else " Três ou mais parcelas: prestações de contas parciais exigidas (art. 40) – conferir.")
    else:
        regra = ""
    return resumo + "." + regra


def montar_checklist_regime(
    regime: Regime,
    por_tipo: Dict[str, List[Documento]],
    docs: List[Documento],
    obra: bool,
) -> List[Dict[str, Any]]:
    linhas = []
    for item in regime.documentos:
        obrigatorio = item.obrigatorio and (obra or not item.somente_obra)
        achados: List[Documento] = []
        for t in item.tipos:
            achados.extend(por_tipo.get(t, []))
            if t in ("EXTRATO_CC", "EXTRATO_APLICACAO"):
                achados.extend(d for d in docs if d.subtipos.get(t) and d not in achados)
        # O número do anexo é só rótulo: formulários do concedente e editais usam numeração própria
        if achados:
            situacao = "LOCALIZADO"
        elif not item.tipos:
            situacao = "VERIFICAR MANUALMENTE"
        elif obrigatorio:
            situacao = "NÃO CONSTA"
        else:
            situacao = "NÃO LOCALIZADO (pode não se aplicar)"
        nota = item.nota
        if item.somente_obra and not obra:
            nota = (nota + "; " if nota else "") + "exigível em obras e serviços de engenharia"
        fundamento = item.fundamento
        if "Decreto" not in fundamento and "Res." not in fundamento:
            fundamento += f" do {regime.normas[0].split(',')[0]}"
        linhas.append({
            "documento": item.rotulo + (f" (Anexo {item.anexo})" if item.anexo else ""),
            "obrigatorio": obrigatorio,
            "fundamento": fundamento,
            "situacao": situacao,
            "referencias": [f"{d.id} – {d.localizacao}" for d in achados][:12],
            "quantidade": sum(d.subtipos.get(t, 0) for d in achados for t in item.tipos if t.startswith("EXTRATO_")) or len(achados),
            "nota": nota,
        })
    return linhas
