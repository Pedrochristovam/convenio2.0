"""
Tipos documentais do inventário (item 4 do PROMPT-MESTRE).

Os padrões são aplicados sobre texto normalizado (maiúsculo, sem acento) e
toleram trocas comuns do OCR (Ç→G, Ã→A, I→L, espaços no meio de palavras).
"""

from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class TipoDocumento:
    codigo: str
    nome: str
    padroes: Tuple[Tuple[str, float], ...]
    pagina_unica: bool = False
    # Grupo do checklist do Relatório de Validação a que o documento pertence
    grupo: str = "outros"


TIPOS: List[TipoDocumento] = [
    TipoDocumento("TERMO_CONVENIO", "Termo de Convênio", (
        (r"TERMO DE CONVENIO", 5), (r"CONVENIO DE SAIDA", 3), (r"CLAUSULA PRIMEIRA", 3),
        (r"\bDO OBJETO\b", 1.5), (r"\bCONCEDENTE\b", 2), (r"\bCONVENENTE\b", 1), (r"PARTICIPES", 2),
        (r"CELEBRAM ENTRE SI", 3), (r"ENTRE SI CELEBRAM", 3),
    ), grupo="convenio"),
    TipoDocumento("OFICIO_SOLICITACAO", "Ofício de solicitação / proposta de celebração", (
        (r"OF[IL]CIO DE SOLICITA[CG]AO", 6), (r"SOLICITA[CG]AO DE CELEBRA[CG]AO", 8),
        (r"CELEBRA[CG]AO D[OE] CONVENIO", 3),
    ), grupo="convenio"),
    TipoDocumento("QDD", "Quadro de Detalhamento da Despesa (QDD)", (
        (r"QUADRO DE DETALHAMENTO DA DESPESA", 4), (r"\bQDD\b", 1),
    ), grupo="convenio"),
    TipoDocumento("GUIA_CONFERENCIA", "Guia de conferência da documentação (concedente)", (
        (r"GUIA DE CONFERENCIA", 8),
    ), grupo="convenio"),
    TipoDocumento("PLANO_TRABALHO", "Plano de Trabalho", (
        (r"PLANO DE TRABALHO", 5), (r"CRONOGRAMA DE DESEMBOLSO", 4), (r"CRONOGRAMA DE EXECUCAO", 3),
        (r"PROPOSTA DE PLANO", 6), (r"REGISTRO (NO|DO) SIGCON", 3),
        (r"PLANO DE APLICACAO", 3), (r"\bMETAS?\b.*\bETAPAS?\b", 2),
    ), grupo="convenio"),
    TipoDocumento("TERMO_ADITIVO", "Termo Aditivo / Apostilamento", (
        (r"TERMO ADITIVO", 6), (r"\bADITAMENTO\b", 3), (r"APOSTILAMENTO", 5), (r"PRORROGACAO DE (PRAZO|VIGENCIA)", 3),
    ), grupo="convenio"),
    TipoDocumento("PUBLICACAO", "Publicação (Diário Oficial)", (
        (r"DIARIO OFICIAL", 4), (r"IMPRENSA OFICIAL", 3), (r"EXTRATO DO? (TERMO|CONVENIO|CONTRATO)", 4),
        (r"\bAVISO DE LICITACAO\b", 2), (r"FAZ SABER QUE", 2),
    )),
    TipoDocumento("OFICIO", "Ofício de encaminhamento da prestação de contas", (
        (r"\bOF[IL]CIO\s*(N|NO|Nº)", 5), (r"\bENCAMINHA(MOS)?\b", 1.5), (r"\bSENHOR[A]? (SECRETARI|DIRETOR|PREFEIT)", 2),
        (r"ATENCIOSAMENTE", 2), (r"PROTOCOLO", 1),
    ), grupo="prestacao"),
    TipoDocumento("PRESTACAO_CONTAS", "Formulário de Prestação de Contas (SETOP)", (
        (r"PRESTACAO DE CONTAS", 2), (r"DIRETORIA DE PRESTACAO DE CONTAS", 2), (r"\bANEXO [IVXL]+\b", 1.5),
        (r"ENTIDADE CONVENIADA", 1.5),
    ), grupo="prestacao"),
    TipoDocumento("EXECUCAO_FISICO_FINANCEIRA", "Relatório de Execução Físico-Financeira", (
        (r"EXECUCAO FISICO[ -]?FINANCEIRA", 6), (r"DEMONSTRATIVO DA EXECUCAO", 5), (r"RELATORIO DE EXECUCAO", 4),
        (r"DEMONSTRATIVO DE RECEITAS? E DESPESAS?", 5), (r"RECURSOS? DO CONCEDENTE", 2), (r"RENDIMENTOS? DE APLICACAO", 2),
        (r"\bPARCIAL\b.{0,40}\bFINAL\b", 3), (r"\bEXECUTOR\b", 1.5), (r"PERIODO:? \d{2}/\d{2}/\d{4} A \d{2}/\d{2}/\d{4}", 1.5),
    ), grupo="prestacao"),
    TipoDocumento("RELACAO_PAGAMENTOS", "Relação de Pagamentos", (
        (r"RELACAO DE? (DOS )?PAGAMENTOS", 6), (r"RELACAO DE? DESPESAS", 4), (r"RELACAO DE BENS", 3),
    ), grupo="despesas"),
    TipoDocumento("CONCILIACAO", "Conciliação Bancária", (
        (r"CONCILIACAO BANCARIA", 6), (r"CONCILIACAO FINANCEIRA", 5),
    ), grupo="banco"),
    TipoDocumento("COPIA_CHEQUE", "Cópia de Cheque / Comprovante (Anexo SETOP)", (
        (r"COPIA DE CHEQUE", 8), (r"ORDEM BANCARIA", 3), (r"CHEQUE N\.?\s?[º°O]?", 5),
        (r"RECEBI ?\(?EMOS\)? O CHEQUE", 8), (r"A FAVOR DE", 2),
    ), pagina_unica=True, grupo="despesas"),
    TipoDocumento("EXTRATO_CC", "Extrato de Conta Corrente", (
        (r"EXTRATO CONTA CORRENTE", 6), (r"EXTRATO DE CONTA CORRENTE", 6), (r"CONTA CORRENTE \d", 1.5),
        (r"DT\.? BALANCETE", 3), (r"PERIODO DO EXTRATO", 3), (r"LAN[CG]AMENTOS", 1.5), (r"MENSAGEM DE ERRO", 0.5),
    ), grupo="banco"),
    TipoDocumento("EXTRATO_APLICACAO", "Extrato de Aplicação Financeira", (
        (r"INVESTIMENTOS FUNDOS", 5), (r"INVESTIMENTOS FINANCEIROS", 5), (r"RESUMO DO MES", 4),
        (r"RENDIMENTO (BRUTO|LIQUIDO)", 2), (r"MES/?ANO REFERENCIA", 3), (r"BB RENDE FACIL", 4), (r"CNPJS PUBLICO", 2),
        (r"CONSULTAS\s*-\s*POUPAN[CG]A", 6), (r"POUPAN[CG]A[- ]OURO", 4), (r"APLIC\.? POUP", 2),
    ), grupo="banco"),
    TipoDocumento("CONHECIMENTO_RECEITA", "Conhecimento de Receita (rendimentos recolhidos)", (
        (r"CONHECIMENTO DA RECEITA", 8), (r"NUMERO CONHECIMENTO", 6),
        (r"REMUNERACAO DE (OUTROS )?DEPOSITOS", 4), (r"RECEITA DE REMUNERACAO", 4), (r"\bTESOUREIR[AO]\b", 1),
    ), pagina_unica=True, grupo="banco"),
    TipoDocumento("NOTA_FISCAL", "Nota Fiscal", (
        (r"NOTA FISCAL", 4), (r"NFS-?E", 3), (r"\bDANFE\b", 5), (r"PRESTADOR DE SERVI[CG]OS", 3),
        (r"TOMADOR DE SERVI[CG]OS", 3), (r"CODIGO (DE )?AUTENTICIDADE", 2), (r"DATA ?(E |/)?HORA DE EMISSAO", 2),
        (r"DISCRIMINACAO DOS SERVI[CG]OS", 3),
    ), pagina_unica=True, grupo="despesas"),
    TipoDocumento("CONTA_CONSUMO", "Conta de energia/água/telefone (não é despesa do convênio)", (
        (r"CONTA DE ENERGIA", 8), (r"CONTA DE AGUA", 8), (r"\bCEMIG\b", 4), (r"\bCOPASA\b", 4),
        (r"CONSUMO (EM )?KWH", 4), (r"DATAS? DE LEITURA", 3),
    ), pagina_unica=True),
    TipoDocumento("RECIBO", "Recibo", (
        (r"\bRECIBO\b", 4), (r"RECEB[IE](MOS)? D[AOE]", 3), (r"A IMPORTANCIA DE", 3),
    ), pagina_unica=True, grupo="despesas"),
    TipoDocumento("COMPROVANTE_PAGAMENTO", "Comprovante de Pagamento / Transferência", (
        (r"COMPROVANTE DE (PAGAMENTO|TRANSFERENCIA|AGENDAMENTO)", 6), (r"CUMPROVANTE DE", 4),
        (r"TRANSFERENCIA ENTRE CONTAS", 5), (r"PAGAMENTO DE (OUTROS )?CONVENIOS", 3), (r"\bTED\b", 1.5),
        (r"EMISSAO DE COMPROVANTES", 3), (r"SEGUNDA VIA", 1), (r"AUTO-?ATENDIMENTO", 1),
    ), pagina_unica=True, grupo="despesas"),
    TipoDocumento("NOTA_EMPENHO", "Nota de Empenho", (
        (r"NOTA DE EMPENHO", 6), (r"SUB-?EMPENHO", 2), (r"\bEMPENHO\b", 1.5), (r"FICHA\s+FONTE", 1.5),
    ), pagina_unica=True, grupo="despesas"),
    TipoDocumento("NOTA_LIQUIDACAO", "Nota de Liquidação / Ordem de Pagamento", (
        (r"NOTA DE LIQUIDA[CG]AO", 6), (r"LIQUIDA[CG]AO DE RESTOS A PAGAR", 3), (r"ORDEM DE PAGAMENTO", 5),
    ), pagina_unica=True, grupo="despesas"),
    TipoDocumento("NOTA_DESPESA_EXTRA", "Nota de Despesa Extraorçamentária (retenções)", (
        (r"DESPESA EXTRA", 6), (r"EXTRA-?\s?OR[CG]AMENTARIA", 5), (r"INSS EMPRESAS?", 2),
    ), pagina_unica=True, grupo="despesas"),
    TipoDocumento("GUIA_RECOLHIMENTO", "Guia de Recolhimento (GPS/DARF/ISS)", (
        (r"GUIA DA PREVIDENCIA SOCIAL", 6), (r"\bGPS\b", 2), (r"\bDARF\b", 5), (r"INSTITUTO NACIONAL DO SEGURO SOCIAL", 2),
        (r"RECEITA PREVIDENCIARIA", 2),
    ), pagina_unica=True, grupo="despesas"),
    TipoDocumento("LICITACAO", "Processo Licitatório", (
        (r"PROCESSO LICITATORIO", 4), (r"TOMADA DE PRE[CG]OS?", 4), (r"\bCONVITE\b", 2), (r"PREGAO", 3),
        (r"CONCORRENCIA", 3), (r"MAPA DE APURA[CG]AO", 5), (r"TERMO DE ADJUDICA[CG]AO", 6), (r"TERMO DE HOMOLOGA[CG]AO", 6),
        (r"ATA DE (JULGAMENTO|ABERTURA|SESSAO)", 5), (r"\bEDITAL\b", 3), (r"MODALIDADE DE LICITA", 3),
        (r"DISPENSA DE LICITA", 4), (r"INEXIGIBILIDADE", 4), (r"PROPOSTA (COMERCIAL|DE PRE[CG]OS)", 3),
    ), grupo="licitacao"),
    TipoDocumento("CONTRATO", "Contrato", (
        (r"CONTRATO DE (PRESTA[CG]AO DE SERVI[CG]OS|EMPREITADA|OBRA|FORNECIMENTO)", 6), (r"\bCONTRATO\s*(N|NO|Nº)", 3),
        (r"\bCONTRATANTE\b", 2), (r"\bCONTRATADA\b", 2), (r"CLAUSULA (PRIMEIRA|SEGUNDA|TERCEIRA|QUARTA|QUINTA|SEXTA)", 1.5),
        (r"OBRIGA[CG]OES DA CONTRATADA", 3), (r"JUSTOS E CONTRATAD", 4),
    ), grupo="licitacao"),
    TipoDocumento("ORDEM_SERVICO", "Ordem de Serviço", (
        (r"ORDEM DE (SERVI[CG]O|INICIO)", 6), (r"AUTORIZA[CG]AO (DE|PARA) INICIO", 5), (r"AUTORIZAMOS O INICIO", 5),
    ), grupo="ordem_servico"),
    TipoDocumento("MEDICAO", "Boletim de Medição", (
        (r"BOLETIM DE MEDI[CG]AO", 6), (r"PLANILHA DE MEDI[CG]AO", 6), (r"\bMEDI[CG]AO\s*(N|NO|Nº|\d)", 4),
        (r"ACUMULADO ATE", 2), (r"MEDIDO NO PERIODO", 3),
    ), grupo="execucao"),
    TipoDocumento("PLANILHA_ORCAMENTARIA", "Planilha Orçamentária", (
        (r"PLANILHA ORCAMENTARIA", 6), (r"\bBDI\b", 2), (r"SINAPI", 3), (r"SETOP.*(REFERENCIA|TABELA)", 2),
        (r"CUSTO UNITARIO", 2),
    ), grupo="execucao"),
    TipoDocumento("MEMORIAL_DESCRITIVO", "Memorial Descritivo / Especificações Técnicas", (
        (r"MEMORIAL DESCRITIVO", 6), (r"ESPECIFICA[CG]OES TECNICAS", 4), (r"CADERNO DE ENCARGOS", 5),
    ), grupo="execucao"),
    TipoDocumento("TERMO_RECEBIMENTO", "Termo de Recebimento da Obra", (
        (r"TERMO DE RECEBIMENTO", 6), (r"RECEBIMENTO (PROVISORIO|DEFINITIVO)", 5),
    ), grupo="execucao"),
    TipoDocumento("RELATORIO_FOTOGRAFICO", "Relatório Fotográfico", (
        (r"RELATORIO FOTOGRAFICO", 6), (r"INFORMA[CG]OES SOBRE A FOTOGRAFIA", 5), (r"\bFOTO\s*\d", 2),
    ), grupo="execucao"),
    TipoDocumento("ART", "ART / RRT", (
        (r"ANOTA[CG]AO DE RESPONSABILIDADE TECNICA", 6), (r"\bART\s*(N|NO|Nº)", 3), (r"\bCREA\b", 2), (r"\bRRT\b", 4),
    ), grupo="execucao"),
    TipoDocumento("PARECER_TECNICO", "Parecer Técnico / Vistoria / Monitoramento", (
        (r"PARECER TECNICO", 6), (r"LAUDO DE VISTORIA", 6), (r"RELATORIO DE (VISTORIA|MONITORAMENTO|VISITA)", 6),
        (r"NOTA TECNICA", 5), (r"VISTORIA", 2), (r"PERCENTUAL (DE )?EXECU", 3), (r"OBJETO (FOI )?(EXECUTADO|CONCLUIDO)", 3),
    ), grupo="parecer"),
    TipoDocumento("NOTA_TECNICA_ACOMPANHAMENTO", "Nota Técnica / vistoria de acompanhamento (celebração ou fase intermediária)", (
        (r"CONFORMIDADE TECNICA", 5), (r"FASE INICIAL", 5), (r"FASE INTERMEDIARIA", 5),
    ), grupo="execucao"),
    TipoDocumento("DAE_DEVOLUCAO", "DAE / Comprovante de Devolução", (
        (r"DOCUMENTO DE ARRECADA[CG]AO ESTADUAL", 6), (r"\bDAE\b", 3), (r"RESTITUI[CG]AO", 2), (r"DEVOLU[CG]AO DE SALDO", 5),
        (r"FAZENDA DE MINAS GERAIS", 2),
    ), pagina_unica=True, grupo="devolucao"),
    TipoDocumento("DECLARACAO", "Declaração", (
        (r"\bDECLARA[CG]AO\b", 4), (r"\bDECLAR(O|AMOS)\b", 3), (r"PARA OS DEVIDOS FINS", 2),
    ), pagina_unica=True),
    TipoDocumento("CERTIDAO", "Certidão", (
        (r"\bCERTIDAO\b", 5), (r"REGULARIDADE FISCAL", 3), (r"\bCND\b", 3), (r"\bCRF\b", 2),
    ), pagina_unica=True),
    TipoDocumento("NOTIFICACAO", "Notificação / Diligência", (
        (r"NOTIFICA[CG]AO", 5), (r"DILIGENCIA", 4), (r"PRAZO DE \d+ .{0,15}DIAS PARA", 2),
    )),
    TipoDocumento("DESPACHO", "Despacho / Memorando / Documento SEI", (
        (r"\bDESPACHO\b", 4), (r"\bMEMORANDO\b", 4), (r"COMUNICA[CG]AO INTERNA", 4), (r"PROCESSO SEI", 3),
        (r"DOCUMENTO ASSINADO ELETRONICAMENTE", 3),
    )),
    TipoDocumento("CORRESPONDENCIA", "Ofício / e-mail / correspondência (outros assuntos)", (
        (r"\bDE:.{0,120}ENVIADO EM:", 6), (r"ENVIADO EM:", 3),
    )),
]

TIPOS_POR_CODIGO = {t.codigo: t for t in TIPOS}

INDEFINIDO = "INDEFINIDO"
ILEGIVEL = "ILEGIVEL"

NOMES_ESPECIAIS = {
    INDEFINIDO: "Documento não classificado",
    ILEGIVEL: "Página ilegível / imagem sem texto",
}


def nome_tipo(codigo: str) -> str:
    t = TIPOS_POR_CODIGO.get(codigo)
    return t.nome if t else NOMES_ESPECIAIS.get(codigo, codigo)


def lista_para_prompt() -> str:
    return "\n".join(f"- {t.codigo}: {t.nome}" for t in TIPOS)
