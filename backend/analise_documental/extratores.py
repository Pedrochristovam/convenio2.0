"""
Extração de dados por tipo documental com rastreabilidade obrigatória.

A IA devolve cada campo como {"valor", "trecho"}; o código confirma que o trecho
existe no OCR (e que o valor aparece nele) antes de aceitar o dado. Campos que
não passam na conferência ficam marcados para validação humana.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.analise_documental.inventario import Documento
from backend.analise_documental.texto import (
    NAO_IDENTIFICADO,
    fmt_date,
    locate_excerpt,
    parse_date,
    parse_money,
    select_windows,
    value_in_excerpt,
)

logger = logging.getLogger(__name__)

TEXTO, VALOR, DATA = "texto", "valor", "data"


@dataclass(frozen=True)
class Esquema:
    instrucao: str
    campos: Tuple[Tuple[str, str, str], ...]
    palavras_chave: Tuple[str, ...] = ()
    max_chars: int = 5000
    rapido: bool = False


ESQUEMAS: Dict[str, Esquema] = {
    "CONVENIO": Esquema(
        "Dados do convênio (instrumento, partes, objeto, valores, vigência, conta específica).",
        (
            ("numero_convenio", TEXTO, "número do convênio, ex.: 624/2014"),
            ("concedente", TEXTO, "quem repassa os recursos, qualificado no termo como CONCEDENTE "
                                  "(ex.: MGI – Minas Gerais Participações S/A ou a secretaria); não confundir com o interveniente"),
            ("convenente", TEXTO, "município/entidade que recebe os recursos, qualificado como CONVENENTE"),
            ("cnpj_convenente", TEXTO, "CNPJ do CONVENENTE (não o CNPJ da concedente nem do interveniente)"),
            ("interveniente", TEXTO, "quem participa como INTERVENIENTE (ex.: Estado por intermédio da SETOP), se houver"),
            ("objeto", TEXTO, "objeto do convênio (cláusula 'do objeto'), transcrição resumida fiel da obra/ação"),
            ("valor_concedente", VALOR, "valor do repasse do concedente"),
            ("valor_contrapartida", VALOR, "valor da contrapartida do convenente"),
            ("valor_total", VALOR, "valor total pactuado"),
            ("data_assinatura", DATA, "data de celebração/assinatura"),
            ("vigencia_inicio", DATA, "início da vigência"),
            ("vigencia_fim", DATA, "fim da vigência (considerando a última prorrogação citada)"),
            ("banco_agencia_conta", TEXTO, "banco, agência e conta específica do convênio"),
        ),
        (r"CONVENIO", r"VIGENCIA", r"VIGORARA", r"OBJETO", r"CONTRAPARTIDA", r"CONCEDENTE", r"REPASSE", r"PERIODO",
         r"VALOR TOTAL", r"RECURSOS FINANCEIROS", r"A TITULO DE", r"CNPJ", r"AGENCIA", r"ASSINATURA",
         r"ENTRE SI CELEBRAM|CELEBRAM ENTRE SI", r"INTERVENI", r"DO OBJETO", r"DORAVANTE",
         r"\b\d{1,2}\s+DE\s+[A-Z]{4,9}\s+DE\s+\d{4}"),
        max_chars=8000,
    ),
    "OFICIO": Esquema(
        "Ofício de encaminhamento da prestação de contas.",
        (
            ("numero", TEXTO, "número do ofício"),
            ("data", DATA, "data do ofício"),
            ("destinatario", TEXTO, "órgão destinatário"),
            ("assunto", TEXTO, "assunto / finalidade"),
            ("data_protocolo", DATA, "data do carimbo de recebimento/protocolo (SIGED/SEI), se houver"),
            ("numero_protocolo", TEXTO, "número de protocolo SIGED/SEI, se houver"),
        ),
        rapido=True, max_chars=3000,
    ),
    "EXECUCAO_FISICO_FINANCEIRA": Esquema(
        "Relatório de execução físico-financeira / demonstrativo da prestação de contas.",
        (
            ("tipo_prestacao", TEXTO, "parcial ou final"),
            ("periodo", TEXTO, "período abrangido"),
            ("valor_concedente", VALOR, "recursos do concedente executados/recebidos"),
            ("valor_contrapartida", VALOR, "contrapartida executada/aportada"),
            ("rendimentos_aplicacao", VALOR, "rendimentos de aplicação financeira declarados"),
            ("valor_total", VALOR, "total executado/declarado"),
            ("saldo_devolvido", VALOR, "saldo devolvido/a devolver, se declarado"),
            ("data_documento", DATA, "data de assinatura do demonstrativo"),
        ),
        (r"TOTAL", r"RENDIMENTO", r"CONCEDENTE", r"CONTRAPARTIDA", r"SALDO", r"PERIODO"),
    ),
    "NOTA_FISCAL": Esquema(
        "Nota fiscal de serviço/produto.",
        (
            ("numero", TEXTO, "número da nota fiscal"),
            ("data_emissao", DATA, "data de emissão"),
            ("emitente", TEXTO, "razão social do prestador/emitente"),
            ("cnpj_emitente", TEXTO, "CNPJ do prestador/emitente"),
            ("tomador", TEXTO, "tomador/destinatário"),
            ("descricao", TEXTO, "discriminação do serviço/produto (resumo fiel)"),
            ("valor_bruto", VALOR, "valor total/bruto da nota"),
            ("retencao_inss", VALOR, "INSS retido"),
            ("retencao_iss", VALOR, "ISS retido"),
            ("retencao_ir", VALOR, "IR retido"),
            ("valor_liquido", VALOR, "valor líquido, se informado"),
            ("mencao_convenio", TEXTO, "menção ao convênio/obra no corpo da nota"),
        ),
        rapido=True, max_chars=3500,
    ),
    "CONTRATO": Esquema(
        "Contrato administrativo.",
        (
            ("numero", TEXTO, "número do contrato"),
            ("processo_licitatorio", TEXTO, "processo/modalidade de licitação citado"),
            ("contratada", TEXTO, "empresa contratada"),
            ("cnpj_contratada", TEXTO, "CNPJ da contratada"),
            ("objeto", TEXTO, "objeto do contrato"),
            ("valor", VALOR, "valor global do contrato"),
            ("prazo_execucao", TEXTO, "prazo de execução/vigência"),
            ("data_assinatura", DATA, "data de assinatura"),
        ),
        (r"CONTRATADA", r"OBJETO", r"VALOR", r"PRAZO", r"VIGENCIA", r"CNPJ"),
    ),
    "LICITACAO": Esquema(
        "Processo licitatório (mapa de apuração, adjudicação, homologação, edital, atas).",
        (
            ("numero_processo", TEXTO, "número do processo licitatório"),
            ("modalidade", TEXTO, "modalidade e número (ex.: Tomada de Preços 003/2014)"),
            ("tipo", TEXTO, "tipo (menor preço etc.)"),
            ("objeto", TEXTO, "objeto licitado"),
            ("vencedor", TEXTO, "adjudicatário/vencedor"),
            ("cnpj_vencedor", TEXTO, "CNPJ do vencedor"),
            ("valor_adjudicado", VALOR, "valor adjudicado/homologado"),
            ("data_adjudicacao", DATA, "data da adjudicação"),
            ("data_homologacao", DATA, "data da homologação"),
        ),
        (r"ADJUDICA", r"HOMOLOGA", r"VENCEDOR", r"MODALIDADE", r"OBJETO", r"VALOR", r"CNPJ"),
    ),
    "ORDEM_SERVICO": Esquema(
        "Ordem de serviço / autorização de início.",
        (
            ("numero", TEXTO, "número da ordem de serviço"),
            ("data_emissao", DATA, "data de emissão"),
            ("data_inicio", DATA, "data autorizada para início"),
            ("contratada", TEXTO, "contratada"),
            ("objeto", TEXTO, "objeto"),
        ),
        rapido=True, max_chars=3000,
    ),
    "MEDICAO": Esquema(
        "Boletim/planilha de medição de obra.",
        (
            ("numero_medicao", TEXTO, "número da medição"),
            ("periodo", TEXTO, "período medido"),
            ("valor_medicao", VALOR, "valor desta medição"),
            ("valor_acumulado", VALOR, "valor acumulado"),
            ("percentual_executado", TEXTO, "percentual executado acumulado"),
        ),
        (r"TOTAL", r"ACUMULAD", r"MEDI", r"PERIODO"),
        rapido=True, max_chars=3500,
    ),
    "PARECER_TECNICO": Esquema(
        "Parecer técnico / relatório de vistoria ou monitoramento. Transcreva a conclusão literalmente.",
        (
            ("numero", TEXTO, "número do parecer/relatório"),
            ("data", DATA, "data"),
            ("responsavel", TEXTO, "responsável técnico"),
            ("percentual_execucao", TEXTO, "percentual/nível de execução informado"),
            ("conclusao", TEXTO, "conclusão sobre o cumprimento do objeto (transcrição literal)"),
            ("glosas_ou_irregularidades", TEXTO, "irregularidades/itens glosados citados"),
            ("valor_glosado", VALOR, "valor glosado ou a restituir, se citado"),
        ),
        (r"CONCLU", r"PERCENTUAL", r"EXECU", r"GLOSA", r"IRREGULAR", r"VISTORIA"),
    ),
    "DAE_DEVOLUCAO": Esquema(
        "DAE / comprovante de devolução de recursos ao Estado.",
        (
            ("valor", VALOR, "valor total recolhido"),
            ("data_vencimento_ou_pagamento", DATA, "data de pagamento ou vencimento"),
            ("natureza", TEXTO, "natureza (devolução de saldo, rendimentos, restituição)"),
            ("identificacao", TEXTO, "número/identificação do documento"),
        ),
        rapido=True, max_chars=3000,
    ),
    "TERMO_RECEBIMENTO": Esquema(
        "Termo de recebimento de obra.",
        (
            ("tipo", TEXTO, "provisório ou definitivo"),
            ("data", DATA, "data do recebimento"),
            ("objeto", TEXTO, "objeto recebido"),
            ("responsavel", TEXTO, "responsável"),
        ),
        rapido=True, max_chars=3000,
    ),
    "TERMO_ADITIVO": Esquema(
        "Termo aditivo / apostilamento.",
        (
            ("numero", TEXTO, "número do aditivo"),
            ("data_assinatura", DATA, "data de assinatura"),
            ("alteracao", TEXTO, "o que foi alterado"),
            ("nova_vigencia_fim", DATA, "nova data final de vigência, se prorrogada"),
            ("novo_valor", VALOR, "novo valor, se alterado"),
        ),
        (r"PRORROG", r"VIGENCIA", r"VALOR", r"CLAUSULA"),
    ),
}

TIPOS_EXTRAIVEIS = [k for k in ESQUEMAS if k != "CONVENIO"]
# Tipos agregados numa única chamada (vários documentos formam um só processo)
TIPOS_AGREGADOS = {"LICITACAO", "MEDICAO"}


def _prompt(esquema: Esquema, texto: str) -> str:
    campos = "\n".join(f'- "{n}" ({t}): {d}' for n, t, d in esquema.campos)
    return (
        f"Documento: {esquema.instrucao}\n\n"
        "TEXTO (OCR, pode conter ruído; marcadores [[PAG n]] indicam a página):\n"
        f"<<<\n{texto}\n>>>\n\n"
        f"CAMPOS:\n{campos}\n\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "1. Use SOMENTE o texto acima. Nunca deduza, complete ou invente valores, datas, números ou nomes.\n"
        "2. Para cada campo devolva {\"valor\": ..., \"trecho\": \"...\"}; \"trecho\" é a cópia literal "
        "(10 a 160 caracteres) do texto onde o valor aparece.\n"
        "3. Se o campo não estiver no texto, devolva {\"valor\": null, \"trecho\": null}.\n"
        "4. Valores monetários como número (ex.: 1234.56). Datas como DD/MM/AAAA.\n"
        '5. Responda apenas JSON: {"campos": {"<campo>": {"valor": ..., "trecho": ...}}}'
    )


def _texto_com_marcadores(docs: List[Documento], esquema: Esquema) -> Tuple[str, List[Tuple[int, str]]]:
    partes, pares = [], []
    for d in docs:
        for p in d.paginas:
            partes.append(f"[[PAG {p.ordem}]]\n{p.texto}")
            pares.append((p.ordem, p.texto))
    completo = "\n".join(partes)
    return select_windows(completo, list(esquema.palavras_chave), max_chars=esquema.max_chars), pares


def _normalizar_valor(tipo: str, valor: Any) -> Any:
    if valor is None or valor == "":
        return None
    if tipo == VALOR:
        return parse_money(valor)
    if tipo == DATA:
        d = parse_date(valor)
        return fmt_date(d) if d else None
    return str(valor).strip() or None


def validar_campos(esquema: Esquema, bruto: Dict[str, Any], pares: List[Tuple[int, str]], ref_por_ordem: Dict[int, str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    campos = (bruto or {}).get("campos") or {}
    for nome, tipo, _ in esquema.campos:
        item = campos.get(nome) or {}
        if not isinstance(item, dict):
            item = {"valor": item, "trecho": None}
        valor = _normalizar_valor(tipo, item.get("valor"))
        trecho = (item.get("trecho") or "").strip() or None
        if valor is None:
            out[nome] = {"valor": None, "status": "nao_identificado", "observacao": NAO_IDENTIFICADO}
            continue
        ordem = locate_excerpt(trecho, pares) if trecho else None
        if ordem is None:
            status = "trecho_nao_localizado"
        elif tipo in (VALOR, DATA) and not value_in_excerpt(parse_date(valor) if tipo == DATA else valor, trecho):
            status = "valor_nao_consta_no_trecho"
        else:
            status = "confirmado"
        out[nome] = {
            "valor": valor,
            "trecho": trecho,
            "localizacao": ref_por_ordem.get(ordem) if ordem is not None else None,
            "status": status,
        }
    return out


async def extrair(
    esquema: Esquema,
    docs: List[Documento],
    llm,
    ref_por_ordem: Dict[int, str],
) -> Dict[str, Any]:
    texto, pares = _texto_com_marcadores(docs, esquema)
    bruto = await llm.acomplete_json(
        "Você extrai dados de documentos de prestação de contas com rastreabilidade. "
        "Nunca invente informação. Responda apenas JSON.",
        _prompt(esquema, texto),
        max_tokens=1400,
        fast=esquema.rapido,
    )
    return validar_campos(esquema, bruto, pares, ref_por_ordem)


def _candidatos_convenio(docs: List[Documento]) -> List[Documento]:
    prioridade = ["TERMO_CONVENIO", "GUIA_CONFERENCIA", "TERMO_ADITIVO", "PLANO_TRABALHO", "EXECUCAO_FISICO_FINANCEIRA",
                  "OFICIO", "PRESTACAO_CONTAS", "PUBLICACAO", "RELATORIO_FOTOGRAFICO"]
    escolhidos: List[Documento] = []
    for tipo in prioridade:
        for d in docs:
            if d.tipo == tipo and not d.duplicado_de:
                escolhidos.append(d)
                if tipo == "RELATORIO_FOTOGRAFICO":
                    break
    return escolhidos


async def extrair_tudo(
    docs: List[Documento],
    llm,
    ref_por_ordem: Dict[int, str],
    progress: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Executa todas as extrações; devolve dados do convênio e grava `extracao` em cada documento."""
    resultado: Dict[str, Any] = {"convenio": {}, "erros": []}
    if not llm or not llm.enabled:
        resultado["erros"].append("IA desativada (GROQ_API_KEY ausente): extração de campos não executada.")
        return resultado

    fila: List[Tuple[str, Esquema, List[Documento]]] = []
    candidatos = _candidatos_convenio(docs)
    if candidatos:
        fila.append(("CONVENIO", ESQUEMAS["CONVENIO"], candidatos))
    for tipo in TIPOS_EXTRAIVEIS:
        alvo = [d for d in docs if d.tipo == tipo and not d.duplicado_de]
        if not alvo:
            continue
        if tipo in TIPOS_AGREGADOS:
            fila.append((tipo, ESQUEMAS[tipo], alvo))
        else:
            fila.extend((tipo, ESQUEMAS[tipo], [d]) for d in alvo)

    for i, (tipo, esquema, alvo) in enumerate(fila, start=1):
        if progress:
            await progress(f"Extraindo dados com IA: {tipo} ({i}/{len(fila)})")
        try:
            campos = await extrair(esquema, alvo, llm, ref_por_ordem)
        except Exception as exc:
            msg = f"{tipo} ({', '.join(d.id for d in alvo)}): {exc}"
            logger.warning("Extração falhou: %s", msg)
            resultado["erros"].append(msg)
            continue
        if tipo == "CONVENIO":
            resultado["convenio"] = campos
            resultado["convenio_fontes"] = [d.id for d in alvo]
        else:
            for d in alvo:
                d.extracao = campos
    return resultado


def valor_campo(campos: Dict[str, Any], nome: str, aceitar_nao_confirmado: bool = True) -> Optional[Any]:
    item = (campos or {}).get(nome) or {}
    if item.get("valor") is None:
        return None
    if not aceitar_nao_confirmado and item.get("status") != "confirmado":
        return None
    return item["valor"]


def fonte_campo(campos: Dict[str, Any], nome: str) -> Optional[str]:
    item = (campos or {}).get(nome) or {}
    return item.get("localizacao")


def limpar_texto(s: Optional[str]) -> Optional[str]:
    return re.sub(r"\s+", " ", s).strip() if s else s
