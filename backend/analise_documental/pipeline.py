import logging
import re
import time
from copy import deepcopy
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

from backend.analise_documental.classificador import (
    Pagina,
    aplicar_continuacoes,
    classificar_com_ia,
    classificar_por_regras,
)
from backend.analise_documental.cruzamentos import executar_cruzamentos
from backend.analise_documental.extratores import extrair_tudo
from backend.analise_documental.inventario import Documento, agrupar_documentos, marcar_duplicados
from backend.analise_documental.parecer import VERSAO as PARECER_VERSAO
from backend.analise_documental.parecer import montar_parecer
from backend.analise_documental.relatorio import montar_relatorio
from backend.analise_documental.texto import norm
from backend.analise_documental.tipos import ILEGIVEL, INDEFINIDO, nome_tipo
from backend.analise_documental.varredura import completar_convenio, varrer_licitacao

logger = logging.getLogger(__name__)

Progress = Optional[Callable[[str, int], Awaitable[None]]]


async def executar_analise(
    db,
    arquivos: List[str],
    llm=None,
    progress: Progress = None,
) -> Dict[str, Any]:
    """
    Monta o dossiê a partir do OCR já gravado (tabela ocr_paginas) dos arquivos,
    na ordem informada, e devolve inventário, dados extraídos, cruzamentos e o
    Relatório de Validação.
    """
    t0 = time.time()
    # O cliente Groq é compartilhado entre análises: medir só o consumo desta
    calls0 = getattr(llm, "calls", 0) if llm else 0
    tokens0 = getattr(llm, "tokens_used", 0) if llm else 0

    async def step(msg: str, pct: int):
        logger.info("[Dossiê %s%%] %s", pct, msg)
        if progress:
            await progress(msg, pct)

    await step("Carregando OCR dos arquivos", 3)
    paginas: List[Pagina] = []
    faltantes = []
    for arquivo in arquivos:
        linhas = db.obter_ocr_texto(arquivo)
        if not linhas:
            faltantes.append(arquivo)
            continue
        for r in linhas:
            paginas.append(Pagina(arquivo=arquivo, pagina=int(r["pagina"]), texto=r["texto"] or "", engine=r["engine"]))
    if faltantes:
        raise ValueError(f"Arquivo(s) sem OCR processado: {', '.join(faltantes)}. Faça o upload/processamento antes.")

    await step(f"Classificando {len(paginas)} páginas por regras", 8)
    classificar_por_regras(paginas)

    async def sub(msg: str):
        await step(msg, 15)

    enviados_ia = await classificar_com_ia(paginas, llm, sub)
    aplicar_continuacoes(paginas)

    await step("Agrupando páginas em documentos", 25)
    docs = agrupar_documentos(paginas)
    duplicados = marcar_duplicados(docs)
    ref_por_ordem = {p.ordem: p.ref for p in paginas}

    async def sub_extr(msg: str):
        await step(msg, 50)

    extr = await extrair_tudo(docs, llm, ref_por_ordem, sub_extr)
    convenio = extr.get("convenio") or {}

    await step("Cruzando documentos com extratos e comprovantes", 85)
    convenio, cruz, relatorio, parecer, varredura = _etapas_deterministicas(db, arquivos, docs, paginas, convenio)

    contagem: Dict[str, int] = {}
    for p in paginas:
        contagem[p.tipo] = contagem.get(p.tipo, 0) + 1

    resultado = {
        "gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "arquivos": arquivos,
        "total_paginas": len(paginas),
        "total_documentos": len(docs),
        "duplicados": duplicados,
        "paginas_por_tipo": {nome_tipo(k): v for k, v in sorted(contagem.items(), key=lambda kv: -kv[1])},
        "paginas_nao_classificadas": [p.ref for p in paginas if p.tipo in (INDEFINIDO, ILEGIVEL)],
        "dados_convenio": convenio,
        "dados_convenio_fontes": extr.get("convenio_fontes", []),
        "inventario": [d.to_dict() for d in docs],
        "cruzamentos": cruz,
        "relatorio_validacao": relatorio,
        "erros_extracao": extr.get("erros", []),
        "uso_ia": {
            "habilitada": bool(llm and llm.enabled),
            "paginas_classificadas_por_ia": enviados_ia,
            "chamadas": (getattr(llm, "calls", 0) - calls0) if llm else 0,
            "tokens": (getattr(llm, "tokens_used", 0) - tokens0) if llm else 0,
        },
        "regime_juridico": relatorio["regime"]["nome"],
        "parecer": parecer,
        "varredura": varredura,
        "duracao_segundos": round(time.time() - t0, 1),
    }
    await step("Análise documental concluída", 100)
    return resultado


def _etapas_deterministicas(db, arquivos: List[str], docs: List[Documento], paginas: List[Pagina], convenio: Dict[str, Any]):
    """Varredura, cruzamentos, relatório e parecer: tudo o que não usa IA."""
    alterados = completar_convenio(convenio, paginas, arquivos)
    resumos = {a: db.listar_resumos_mensais(a) for a in arquivos}
    cc = {a: db.listar_movimentacoes_cc(a) for a in arquivos}
    cruz = executar_cruzamentos(docs, paginas, convenio, resumos, cc)
    cruz["licitacao_varredura"] = varrer_licitacao(paginas, docs, cruz.get("total_notas_fiscais"))
    relatorio = montar_relatorio(docs, convenio, cruz)
    parecer = montar_parecer(docs, convenio, cruz, relatorio)
    return convenio, cruz, relatorio, parecer, {"dados_convenio_corrigidos": alterados}


def _carregar_paginas(db, arquivos: List[str]) -> List[Pagina]:
    paginas: List[Pagina] = []
    for arquivo in arquivos:
        for r in db.obter_ocr_texto(arquivo) or []:
            paginas.append(Pagina(arquivo=arquivo, pagina=int(r["pagina"]), texto=r["texto"] or "", engine=r["engine"]))
    return paginas


EXTRATO_APLIC_RE = re.compile(r"INVESTIMENTO|APLICAC|POUPAN|RENDE FACIL|SUPREMO|FUNDO|RESUMO DO MES")


def recalcular_analise(db, resultado: Dict[str, Any]) -> Dict[str, Any]:
    """
    Refaz as etapas determinísticas sobre a classificação e as extrações já gravadas,
    sem chamar a IA de novo (segundos em vez de minutos).
    """
    arquivos = resultado["arquivos"]
    paginas = _carregar_paginas(db, arquivos)
    if not paginas:
        raise ValueError("OCR dos arquivos do dossiê não encontrado.")
    classificar_por_regras(paginas)
    por_ref = {(p.arquivo, p.pagina): p for p in paginas}
    docs: List[Documento] = []
    for item in resultado.get("inventario") or []:
        pags = [por_ref[(x["arquivo"], int(x["pagina"]))] for x in item.get("paginas") or [] if (x["arquivo"], int(x["pagina"])) in por_ref]
        if not pags:
            continue
        for p in pags:
            if item["tipo"] == "EXTRATOS":
                if p.tipo not in ("EXTRATO_CC", "EXTRATO_APLICACAO"):
                    p.tipo = "EXTRATO_APLICACAO" if EXTRATO_APLIC_RE.search(norm(p.texto)) else "EXTRATO_CC"
            else:
                p.tipo = item["tipo"]
        docs.append(Documento(
            id=item["id"], tipo=item["tipo"], nome=item.get("nome") or nome_tipo(item["tipo"]), paginas=pags,
            titulo_anexo=item.get("titulo_anexo"), duplicado_de=item.get("duplicado_de"),
            extracao=item.get("extracao") or {}, subtipos=item.get("subtipos") or {},
        ))
    convenio = deepcopy(resultado.get("dados_convenio") or {})
    convenio, cruz, relatorio, parecer, varredura = _etapas_deterministicas(db, arquivos, docs, paginas, convenio)
    novo = dict(resultado)
    novo.update({
        "dados_convenio": convenio,
        "cruzamentos": cruz,
        "relatorio_validacao": relatorio,
        "regime_juridico": relatorio["regime"]["nome"],
        "parecer": parecer,
        "varredura": varredura,
        "recalculado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    return novo


def precisa_recalcular(resultado: Optional[Dict[str, Any]]) -> bool:
    return bool(resultado and resultado.get("inventario")
                and (resultado.get("parecer") or {}).get("versao") != PARECER_VERSAO)
