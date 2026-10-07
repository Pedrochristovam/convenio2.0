import React, { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, ChevronDown, Download, FileSpreadsheet, FileText, HelpCircle, Loader2, Scale } from 'lucide-react'
import { api, baixar, fmtMoney, nomeLegivel } from '../lib/api'

const RESULTADOS = [
    ['ATENDE', 'Atende', 'bg-emerald-500', 'text-emerald-700 bg-emerald-50 ring-emerald-200'],
    ['ATENDE COM RESSALVAS', 'Com ressalvas', 'bg-amber-400', 'text-amber-800 bg-amber-50 ring-amber-200'],
    ['NÃO ATENDE', 'Não atende', 'bg-rose-500', 'text-rose-700 bg-rose-50 ring-rose-200'],
    ['NÃO CONSTA', 'Não consta', 'bg-slate-400', 'text-slate-700 bg-slate-100 ring-slate-200'],
    ['PENDENTE DE VALIDAÇÃO HUMANA', 'Validar', 'bg-sky-500', 'text-sky-800 bg-sky-50 ring-sky-200'],
    ['REGIME IDENTIFICADO', 'Regime', 'bg-indigo-500', 'text-indigo-700 bg-indigo-50 ring-indigo-200'],
]
const COR_RESULTADO = Object.fromEntries(RESULTADOS.map(([k, , , cor]) => [k, cor]))

const ROTULOS_CONVENIO = {
    numero_convenio: 'Número do convênio',
    concedente: 'Concedente',
    convenente: 'Convenente',
    cnpj_convenente: 'CNPJ do convenente',
    interveniente: 'Interveniente',
    objeto: 'Objeto',
    valor_concedente: 'Valor do concedente',
    valor_contrapartida: 'Contrapartida',
    valor_total: 'Valor total',
    data_assinatura: 'Assinatura',
    vigencia_inicio: 'Início da vigência',
    vigencia_fim: 'Fim da vigência',
    banco_agencia_conta: 'Banco / agência / conta',
}

function Pill({ resultado }) {
    const rot = RESULTADOS.find(([k]) => k === resultado)?.[1] || resultado
    return <span className={`inline-flex shrink-0 items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${COR_RESULTADO[resultado] || 'bg-slate-100 text-slate-600 ring-slate-200'}`}>{rot}</span>
}

function Tabela({ colunas, linhas, vazio = 'Nenhum registro.' }) {
    if (!linhas?.length) return <p className="py-6 text-sm text-slate-400">{vazio}</p>
    return (
        <div className="overflow-x-auto">
            <table className="w-full text-sm">
                <thead>
                    <tr className="border-b border-slate-200 text-left text-[11px] uppercase tracking-wider text-slate-400">
                        {colunas.map((c) => <th key={c} className="py-2 pr-4 font-medium">{c}</th>)}
                    </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                    {linhas.map((l, i) => (
                        <tr key={i} className="align-top hover:bg-slate-50/70">
                            {l.map((cel, j) => <td key={j} className="py-2.5 pr-4 text-slate-700">{cel}</td>)}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    )
}

function ItemRelatorio({ item }) {
    const [aberto, setAberto] = useState(false)
    const longo = (item.observacao || '').length > 180
    return (
        <li className="grid grid-cols-[130px_1fr] gap-x-6 gap-y-1 py-4 md:grid-cols-[150px_1fr_240px]">
            <div className="pt-0.5"><Pill resultado={item.resultado} /></div>
            <div className="min-w-0">
                <p className="font-medium text-slate-900">{item.item}</p>
                <p className={`mt-1 text-sm leading-relaxed text-slate-600 ${!aberto && longo ? 'line-clamp-2' : ''}`}>{item.observacao}</p>
                {longo && (
                    <button onClick={() => setAberto(!aberto)} className="mt-1 text-xs font-medium text-indigo-600 hover:text-indigo-800">
                        {aberto ? 'ver menos' : 'ver mais'}
                    </button>
                )}
            </div>
            <div className="col-start-2 text-xs text-slate-400 md:col-start-auto md:text-right">
                <p className="text-slate-500">{item.documento}</p>
                <p>{item.localizacao}</p>
            </div>
        </li>
    )
}

function ListaAtencao({ titulo, descricao, itens, cor, icone: Icone }) {
    if (!itens.length) return null
    return (
        <section>
            <div className="flex items-center gap-2">
                <Icone className={`h-4 w-4 ${cor}`} />
                <h4 className="font-semibold text-slate-900">{titulo}</h4>
                <span className="text-sm text-slate-400">{itens.length}</span>
            </div>
            {descricao && <p className="mt-0.5 text-xs text-slate-500">{descricao}</p>}
            <ol className="mt-3 divide-y divide-slate-100">
                {itens.map((o, i) => (
                    <li key={i} className="py-3 text-sm">
                        {typeof o === 'string' ? <p className="text-slate-700">{o}</p> : (
                            <>
                                <p className="font-medium text-slate-800">
                                    {o.titulo}
                                    {o.valor !== null && o.valor !== undefined && <span className="ml-2 font-mono text-slate-500">{fmtMoney(o.valor)}</span>}
                                </p>
                                <p className="mt-0.5 text-slate-600">{o.descricao}</p>
                                <p className="mt-1 text-xs text-slate-400">
                                    {o.item && <span>{o.item}</span>}
                                    {o.fundamento && <span className="text-indigo-500"> · {o.fundamento}</span>}
                                    {o.fontes?.filter(Boolean).length > 0 && <span> · {o.fontes.filter(Boolean).join(' | ')}</span>}
                                </p>
                            </>
                        )}
                    </li>
                ))}
            </ol>
        </section>
    )
}

export default function AnaliseResultado({ dossie, onAtualizar }) {
    const res = dossie.resultado
    const rel = res.relatorio_validacao
    const cruz = res.cruzamentos
    const [tct, setTct] = useState(null)
    const [modelo, setModelo] = useState('')
    const [baixando, setBaixando] = useState(null)
    const [erro, setErro] = useState(null)
    const [aba, setAba] = useState('itens')
    const [filtro, setFiltro] = useState(null)
    const [detalhesAbertos, setDetalhesAbertos] = useState(false)

    useEffect(() => {
        setTct(null)
        api(`/dossies/${dossie.id}/saida-tct`).then((d) => { setTct(d); setModelo(d.modelo_sugerido) }).catch(() => {})
    }, [dossie.id])

    const contagem = useMemo(() => {
        const c = {}
        rel.itens.forEach((i) => { c[i.resultado] = (c[i.resultado] || 0) + 1 })
        return c
    }, [rel.itens])

    const validacao = [...rel.questoes_validacao_humana, ...rel.itens_pendentes_validacao, ...rel.campos_nao_confirmados]
    const nAtencao = rel.possiveis_danos.length + rel.ressalvas_sem_dano.length + rel.pendencias_documentais.length + validacao.length
    const itensFiltrados = filtro ? rel.itens.filter((i) => i.resultado === filtro) : rel.itens

    const gerar = async (tipo) => {
        setErro(null)
        setBaixando(tipo)
        try {
            if (tipo === 'ad') await baixar(`/dossies/${dossie.id}/minuta-ad?modelo=${modelo}&formato=pdf`, 'analise_documental.pdf')
            else if (tipo === 'docx') await baixar(`/dossies/${dossie.id}/minuta-ad?modelo=${modelo}&formato=docx`, 'analise_documental.docx')
            else if (tipo === 'solicitacao') await baixar(`/dossies/${dossie.id}/solicitacao?formato=pdf`, 'solicitacao_documentos.pdf')
            else if (tipo === 'solicitacao_docx') await baixar(`/dossies/${dossie.id}/solicitacao?formato=docx`, 'solicitacao_documentos.docx')
            else if (tipo === 'oficio') await baixar(`/dossies/${dossie.id}/oficio?formato=docx`, 'oficio_diligencia.docx')
            else if (tipo === 'recalcular') onAtualizar?.(await api(`/dossies/${dossie.id}/recalcular`, { method: 'POST' }))
            else await baixar(`/dossies/${dossie.id}/conciliacao?inexecucao=${modelo === 'INEXECUCAO'}`, 'conciliacao.xlsx')
        } catch (e) {
            setErro(`${tipo === 'recalcular' ? 'Falha ao recalcular' : 'Falha ao gerar o arquivo'}: ${e.message}`)
        } finally {
            setBaixando(null)
        }
    }

    const baixarJson = () => {
        const a = document.createElement('a')
        a.href = URL.createObjectURL(new Blob([JSON.stringify(res, null, 2)], { type: 'application/json' }))
        a.download = `analise_documental_${dossie.id}.json`
        a.click()
        URL.revokeObjectURL(a.href)
    }

    const abas = [
        ['itens', 'Itens do relatório', rel.itens.length],
        ['atencao', 'Pontos de atenção', nAtencao],
        ['documentos', 'Documentos', res.total_documentos],
        ['notas', 'Notas fiscais', cruz.notas_fiscais.length],
        ['financeiro', 'Financeiro', null],
    ]

    return (
        <div className="space-y-10">
            {/* Resumo do parecer + regime */}
            <div className="grid gap-10 lg:grid-cols-[1fr_340px]">
                <div>
                    <p className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Resultado dos {rel.itens.length} itens analisados</p>
                    <div className="mt-4 flex flex-wrap gap-x-8 gap-y-4">
                        {RESULTADOS.filter(([k]) => contagem[k]).map(([k, rot, dot]) => (
                            <button key={k} onClick={() => { setAba('itens'); setFiltro(filtro === k ? null : k) }} className="group text-left">
                                <p className="text-4xl font-semibold tabular-nums text-slate-900 group-hover:text-indigo-700">{contagem[k]}</p>
                                <p className="mt-1 flex items-center gap-1.5 text-sm text-slate-500">
                                    <span className={`h-2 w-2 rounded-full ${dot}`} /> {rot}
                                </p>
                            </button>
                        ))}
                    </div>
                    <div className="mt-5 flex h-2 overflow-hidden rounded-full bg-slate-100">
                        {RESULTADOS.filter(([k]) => contagem[k]).map(([k, , dot]) => (
                            <div key={k} className={dot} style={{ width: `${(contagem[k] / rel.itens.length) * 100}%` }} title={`${k}: ${contagem[k]}`} />
                        ))}
                    </div>
                </div>
                {rel.regime && (
                    <div className="border-l-2 border-indigo-200 pl-6">
                        <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-slate-400">
                            <Scale className="h-3.5 w-3.5" /> Regime jurídico
                        </p>
                        <p className="mt-2 font-semibold leading-snug text-slate-900">{rel.regime.nome}</p>
                        {rel.regime.codigo && (
                            <p className="mt-1 text-xs text-slate-500">
                                Confiança {rel.regime.confianca}{rel.regime.base ? ` · por ${rel.regime.base}` : ''}{rel.regime.data_referencia ? ` (${rel.regime.data_referencia})` : ''}
                            </p>
                        )}
                        <p className="mt-2 text-xs leading-relaxed text-slate-500 line-clamp-4" title={rel.regime.motivo}>{rel.regime.motivo}</p>
                    </div>
                )}
            </div>

            {/* Documentos de saída */}
            {tct && (
                <section className="rounded-2xl bg-gradient-to-br from-indigo-600 to-violet-600 px-7 py-6 text-white shadow-xl shadow-indigo-600/20">
                    <div className="flex flex-wrap items-start justify-between gap-6">
                        <div className="max-w-xl">
                            <h3 className="text-lg font-semibold">Documentos de saída — Novo TCT</h3>
                            <p className="mt-1 text-sm text-indigo-100">{tct.motivo}</p>
                            <div className="mt-4 inline-flex flex-wrap rounded-lg bg-white/10 p-1">
                                {Object.entries(tct.modelos).map(([k, rot]) => (
                                    <button key={k} onClick={() => setModelo(k)}
                                        className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${modelo === k ? 'bg-white text-indigo-700 shadow' : 'text-indigo-50 hover:bg-white/10'}`}>
                                        {rot}{k === tct.modelo_sugerido ? ' · sugerido' : ''}
                                    </button>
                                ))}
                            </div>
                        </div>
                        <div className="flex flex-col gap-2 sm:flex-row">
                            <button onClick={() => gerar('ad')} disabled={!!baixando}
                                className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-5 py-3 text-sm font-semibold text-indigo-700 shadow hover:bg-indigo-50 disabled:opacity-70">
                                {baixando === 'ad' ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
                                {baixando === 'ad' ? 'Gerando PDF...' : 'Análise Documental (PDF)'}
                            </button>
                            <button onClick={() => gerar('conciliacao')} disabled={!!baixando}
                                className="inline-flex items-center justify-center gap-2 rounded-xl bg-white/15 px-5 py-3 text-sm font-semibold text-white ring-1 ring-white/30 hover:bg-white/25 disabled:opacity-70">
                                {baixando === 'conciliacao' ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileSpreadsheet className="h-4 w-4" />}
                                Conciliação (Excel)
                            </button>
                        </div>
                    </div>
                    <p className="mt-5 text-xs text-indigo-100/90">
                        Minuta de apoio: trechos em amarelo na AD e células em laranja no Excel devem ser conferidos pelo analista.
                        <button onClick={() => gerar('docx')} disabled={!!baixando} className="ml-2 underline decoration-indigo-300 underline-offset-2 hover:text-white">
                            {baixando === 'docx' ? 'gerando...' : 'Versão editável (Word)'}
                        </button>
                        <button onClick={baixarJson} className="ml-3 underline decoration-indigo-300 underline-offset-2 hover:text-white">Dados brutos (JSON)</button>
                        <button onClick={() => gerar('recalcular')} disabled={!!baixando} title="Refaz cruzamentos, relatório e parecer sem chamar a IA de novo"
                            className="ml-3 underline decoration-indigo-300 underline-offset-2 hover:text-white">
                            {baixando === 'recalcular' ? 'recalculando...' : 'Recalcular (sem IA)'}
                        </button>
                    </p>
                    {res.parecer?.diligencia && res.parecer?.solicitacao?.length > 0 && (
                        <div className="mt-5 flex flex-wrap items-center justify-between gap-4 rounded-xl bg-white/10 px-4 py-3">
                            <div className="max-w-md">
                                <p className="text-sm font-semibold">Diligência ao convenente</p>
                                <p className="mt-0.5 text-xs text-indigo-100">
                                    {res.parecer.solicitacao.length} {res.parecer.solicitacao.length === 1 ? 'item' : 'itens'} a solicitar. No Ofício, os campos do SEI (número, prefeito, endereço, analista) ficam em amarelo.
                                </p>
                            </div>
                            <div className="flex flex-wrap gap-2">
                                <button onClick={() => gerar('solicitacao')} disabled={!!baixando}
                                    className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-xs font-semibold text-indigo-700 shadow hover:bg-indigo-50 disabled:opacity-70">
                                    {baixando === 'solicitacao' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileText className="h-3.5 w-3.5" />}
                                    Anexo – Solicitação (PDF)
                                </button>
                                <button onClick={() => gerar('solicitacao_docx')} disabled={!!baixando}
                                    className="inline-flex items-center gap-2 rounded-lg bg-white/15 px-4 py-2 text-xs font-semibold text-white ring-1 ring-white/30 hover:bg-white/25 disabled:opacity-70">
                                    {baixando === 'solicitacao_docx' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                                    Solicitação (Word)
                                </button>
                                <button onClick={() => gerar('oficio')} disabled={!!baixando}
                                    className="inline-flex items-center gap-2 rounded-lg bg-white/15 px-4 py-2 text-xs font-semibold text-white ring-1 ring-white/30 hover:bg-white/25 disabled:opacity-70">
                                    {baixando === 'oficio' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                                    Ofício de diligência (Word)
                                </button>
                            </div>
                        </div>
                    )}
                    {tct.inexecucao_sugerida && modelo !== 'INEXECUCAO' && (
                        <p className="mt-3 flex items-center gap-2 rounded-lg bg-amber-400/20 px-3 py-2 text-xs text-amber-50">
                            <AlertTriangle className="h-4 w-4 shrink-0" /> Possível inexecução ({tct.motivo_inexecucao}). Avalie usar o modelo de Inexecução.
                        </p>
                    )}
                </section>
            )}
            {erro && <p className="text-sm text-rose-600">{erro}</p>}
            {res.erros_extracao?.length > 0 && (
                <p className="flex items-start gap-2 text-sm text-amber-700">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> Falhas de extração: {res.erros_extracao.join(' | ')}
                </p>
            )}

            {/* Ficha do convênio */}
            <section>
                <h3 className="text-lg font-semibold tracking-tight text-slate-900">Ficha do convênio</h3>
                <p className="text-sm text-slate-500">Dados extraídos do termo e conferidos contra o texto. <span className="text-amber-600">Âmbar</span> = conferir no documento.</p>
                <dl className="mt-5 grid gap-x-10 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
                    {Object.entries(res.dados_convenio || {}).map(([k, v]) => {
                        const ok = v.status === 'confirmado'
                        const vazio = v.valor === null || v.valor === undefined || v.valor === ''
                        const valor = typeof v.valor === 'number' ? fmtMoney(v.valor) : v.valor
                        return (
                            <div key={k} className={k === 'objeto' ? 'sm:col-span-2 lg:col-span-3' : ''}>
                                <dt className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-slate-400">
                                    {ROTULOS_CONVENIO[k] || k}
                                    {!vazio && (ok
                                        ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                                        : <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />)}
                                </dt>
                                <dd className={`mt-1 text-sm ${vazio ? 'italic text-slate-400' : ok ? 'text-slate-900' : 'text-amber-800'}`}
                                    title={[v.trecho, v.localizacao].filter(Boolean).join(' — ')}>
                                    {vazio ? 'não identificado' : valor}
                                </dd>
                            </div>
                        )
                    })}
                </dl>
            </section>

            {/* Abas de detalhe */}
            <section>
                <nav className="flex flex-wrap gap-6 border-b border-slate-200">
                    {abas.map(([k, rot, n]) => (
                        <button key={k} onClick={() => setAba(k)}
                            className={`-mb-px border-b-2 pb-3 text-sm font-medium transition ${aba === k ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-800'}`}>
                            {rot}{n !== null && <span className="ml-1.5 text-slate-400">{n}</span>}
                        </button>
                    ))}
                </nav>

                <div className="pt-6">
                    {aba === 'itens' && (
                        <>
                            <div className="flex flex-wrap gap-2">
                                <button onClick={() => setFiltro(null)} className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset ${!filtro ? 'bg-slate-900 text-white ring-slate-900' : 'text-slate-600 ring-slate-200 hover:bg-slate-50'}`}>
                                    Todos {rel.itens.length}
                                </button>
                                {RESULTADOS.filter(([k]) => contagem[k]).map(([k, rot]) => (
                                    <button key={k} onClick={() => setFiltro(filtro === k ? null : k)}
                                        className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset ${filtro === k ? 'bg-slate-900 text-white ring-slate-900' : 'text-slate-600 ring-slate-200 hover:bg-slate-50'}`}>
                                        {rot} {contagem[k]}
                                    </button>
                                ))}
                            </div>
                            <ul className="mt-2 divide-y divide-slate-100">
                                {itensFiltrados.map((i, idx) => <ItemRelatorio key={`${i.item}-${idx}`} item={i} />)}
                            </ul>
                            <p className="mt-4 text-xs text-slate-400">{rel.aviso}</p>
                        </>
                    )}

                    {aba === 'atencao' && (
                        <div className="grid gap-10 lg:grid-cols-2">
                            <ListaAtencao titulo="Possíveis danos / valores a ressarcir" itens={rel.possiveis_danos} cor="text-rose-500" icone={AlertTriangle} />
                            <ListaAtencao titulo="Ressalvas sem dano identificado" itens={rel.ressalvas_sem_dano} cor="text-amber-500" icone={AlertTriangle} />
                            <ListaAtencao titulo="Pendências documentais" itens={rel.pendencias_documentais} cor="text-slate-500" icone={FileText} />
                            <ListaAtencao titulo="Exigem validação humana" descricao="Leituras incertas do OCR ou conclusões que dependem do analista."
                                itens={validacao} cor="text-sky-500" icone={HelpCircle} />
                            {nAtencao === 0 && <p className="text-sm text-slate-400">Nenhum ponto de atenção.</p>}
                            <section className="lg:col-span-2">
                                <h4 className="font-semibold text-slate-900">Controle de qualidade</h4>
                                <dl className="mt-3 divide-y divide-slate-100 text-sm">
                                    {rel.controle_qualidade.map((q, i) => (
                                        <div key={i} className="grid gap-2 py-2.5 md:grid-cols-[1fr_1fr]">
                                            <dt className="text-slate-500">{q.pergunta}</dt>
                                            <dd className="text-slate-800">{q.resposta}</dd>
                                        </div>
                                    ))}
                                </dl>
                            </section>
                        </div>
                    )}

                    {aba === 'documentos' && (
                        <div className="space-y-10">
                            <div>
                                <h4 className="font-semibold text-slate-900">Checklist documental</h4>
                                <ul className="mt-3 divide-y divide-slate-100">
                                    {rel.checklist_documental.map((c, i) => {
                                        const ok = c.situacao === 'LOCALIZADO'
                                        return (
                                            <li key={i} className="flex items-start gap-3 py-2.5 text-sm">
                                                {ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                                                    : <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${c.situacao === 'NÃO CONSTA' ? 'bg-rose-400' : 'bg-slate-300'}`} />}
                                                <div className="min-w-0 flex-1">
                                                    <p className={ok ? 'text-slate-800' : 'text-slate-600'}>
                                                        {c.documento}{!c.obrigatorio && <span className="text-slate-400"> (se aplicável)</span>}
                                                    </p>
                                                    <p className="text-xs text-slate-400">
                                                        {c.fundamento}{c.referencias.length > 0 && ` · ${c.referencias.join('; ')}`}{c.nota && ` · ${c.nota}`}
                                                    </p>
                                                </div>
                                                <span className={`shrink-0 text-xs font-medium ${ok ? 'text-emerald-600' : c.situacao === 'NÃO CONSTA' ? 'text-rose-600' : 'text-slate-400'}`}>{c.situacao}</span>
                                            </li>
                                        )
                                    })}
                                </ul>
                            </div>
                            <div>
                                <button onClick={() => setDetalhesAbertos(!detalhesAbertos)} className="flex items-center gap-2 font-semibold text-slate-900">
                                    Matriz de documentos
                                    <span className="text-sm font-normal text-slate-400">{res.total_documentos} documentos em {res.total_paginas} páginas · {res.duplicados} duplicado(s)</span>
                                    <ChevronDown className={`h-4 w-4 text-slate-400 transition-transform ${detalhesAbertos ? 'rotate-180' : ''}`} />
                                </button>
                                {detalhesAbertos && (
                                    <div className="mt-3">
                                        <Tabela
                                            colunas={['ID', 'Documento', 'Localização', 'Datas / período', 'Maior valor', 'Duplicado']}
                                            linhas={res.inventario.map((d) => [
                                                <span className="font-mono text-xs text-slate-400">{d.id}</span>,
                                                <span>{d.nome}{d.titulo_anexo && <span className="block text-xs text-slate-400">{d.titulo_anexo}</span>}</span>,
                                                <span className="text-xs text-slate-500">{d.localizacao}</span>,
                                                <span className="text-xs">{d.periodo_detectado || d.datas_detectadas.join(', ') || '—'}</span>,
                                                <span className="font-mono text-xs">{fmtMoney(d.maior_valor_detectado)}</span>,
                                                d.duplicado_de ? <span className="text-xs text-amber-600">de {d.duplicado_de}</span> : '—',
                                            ])}
                                        />
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {aba === 'notas' && (
                        <>
                            <p className="mb-4 text-sm text-slate-500">Total bruto das notas fiscais: <strong className="text-slate-900">{fmtMoney(cruz.total_notas_fiscais)}</strong></p>
                            <Tabela
                                colunas={['NF', 'Emissão', 'Emitente', 'Bruto', 'Retenções', 'Líquido', 'Pagamento', 'Localização']}
                                vazio="Nenhuma nota fiscal identificada."
                                linhas={cruz.notas_fiscais.map((n) => [
                                    n.numero || '—',
                                    n.data_emissao || '—',
                                    <span>{n.emitente || '—'}<span className="block text-xs text-slate-400">{n.cnpj || ''}</span></span>,
                                    <span className="font-mono">{fmtMoney(n.valor_bruto)}</span>,
                                    <span className="font-mono">{fmtMoney(n.retencoes)}</span>,
                                    <span className="font-mono">{fmtMoney(n.valor_liquido)}</span>,
                                    n.pagamento
                                        ? <span className="text-emerald-700">{fmtMoney(n.pagamento.valor)} em {n.pagamento.data}</span>
                                        : <span className="text-amber-600">não localizado</span>,
                                    <span className="text-xs text-slate-400">{n.localizacao}</span>,
                                ])}
                            />
                        </>
                    )}

                    {aba === 'financeiro' && <Financeiro cruz={cruz} />}
                </div>
            </section>

            <p className="border-t border-slate-100 pt-4 text-xs text-slate-400">
                {res.total_paginas} páginas · {res.total_documentos} documentos · {res.paginas_nao_classificadas.length} página(s) não classificada(s) ·
                IA {res.uso_ia.habilitada ? `${res.uso_ia.chamadas} chamadas / ${res.uso_ia.tokens} tokens` : 'desativada'} ·
                gerado em {res.gerado_em} ({res.duracao_segundos}s) · volumes: {res.arquivos.map(nomeLegivel).join(' → ')}
            </p>
        </div>
    )
}

function Linha({ rotulo, valor, forte }) {
    return (
        <div className={`flex justify-between gap-4 py-1.5 text-sm ${forte ? 'border-t border-slate-200 pt-2.5 font-semibold text-slate-900' : 'text-slate-600'}`}>
            <span>{rotulo}</span><span className="font-mono tabular-nums">{valor}</span>
        </div>
    )
}

function Financeiro({ cruz }) {
    const c = cruz.controle
    const ext = cruz.extratos_aplicacao
    const dem = cruz.demonstrativo
    return (
        <div className="space-y-10">
            <div className="grid gap-12 md:grid-cols-2">
                <div>
                    <h4 className="font-semibold text-slate-900">Fórmula de controle</h4>
                    <div className="mt-3">
                        <Linha rotulo={`Repasses (${c.repasse_origem || 'origem não identificada'})`} valor={fmtMoney(c.repasses)} />
                        <Linha rotulo="Contrapartida" valor={fmtMoney(c.contrapartida)} />
                        <Linha rotulo="Rendimentos (extratos)" valor={fmtMoney(c.rendimentos_extratos)} />
                        <Linha rotulo="Despesas (notas fiscais)" valor={fmtMoney(c.despesas_notas_fiscais)} />
                        <Linha rotulo="Devoluções" valor={fmtMoney(c.devolucoes)} />
                        <Linha rotulo="Saldo apurado" valor={fmtMoney(c.saldo_apurado)} forte />
                        <Linha rotulo="Último saldo de aplicação" valor={fmtMoney(c.saldo_final_extrato_aplicacao)} />
                    </div>
                    {c.memoria && <p className="mt-2 text-xs italic text-slate-400">{c.memoria}</p>}
                </div>
                <div>
                    <h4 className="font-semibold text-slate-900">Demonstrativo declarado</h4>
                    {dem ? (
                        <div className="mt-3">
                            <Linha rotulo="Concedente" valor={fmtMoney(dem.valor_concedente)} />
                            <Linha rotulo="Contrapartida" valor={fmtMoney(dem.valor_contrapartida)} />
                            <Linha rotulo="Rendimentos" valor={fmtMoney(dem.rendimentos_aplicacao)} />
                            <Linha rotulo="Total declarado" valor={fmtMoney(dem.valor_total)} forte />
                            <Linha rotulo="Soma calculada" valor={fmtMoney(dem.soma_calculada)} />
                            <p className={`mt-2 text-xs font-medium ${dem.confere ? 'text-emerald-600' : 'text-amber-600'}`}>
                                {dem.confere ? '✓ A soma confere com o total declarado' : 'A soma não confere com o total declarado'} · {dem.localizacao}
                            </p>
                        </div>
                    ) : <p className="mt-3 text-sm text-slate-400">Demonstrativo não localizado ou sem valores legíveis.</p>}
                    <div className="mt-4 text-sm text-slate-600">
                        <p>Vigência: <strong className="text-slate-900">{cruz.vigencia.inicio || '—'} a {cruz.vigencia.fim || '—'}</strong></p>
                        <p>Rendimentos declarados × extratos: <strong className="text-slate-900">{fmtMoney(ext.rendimentos_declarados)}</strong> × <strong className="text-slate-900">{fmtMoney(ext.rendimentos_liquidos_total)}</strong></p>
                    </div>
                </div>
            </div>

            <div>
                <h4 className="mb-2 font-semibold text-slate-900">Devoluções</h4>
                <Tabela
                    colunas={['Valor', 'Data', 'Natureza', 'Comprovação', 'Localização']}
                    vazio="Nenhuma devolução identificada."
                    linhas={cruz.devolucoes.map((d) => [
                        <span className="font-mono">{fmtMoney(d.valor)}</span>, d.data || '—', d.natureza || '—',
                        d.comprovada
                            ? <span className="text-emerald-700">{d.comprovacao.map((x) => `${fmtMoney(x.valor)} em ${x.data}`).join('; ')}</span>
                            : <span className="text-amber-600">não comprovada</span>,
                        <span className="text-xs text-slate-400">{d.localizacao}</span>,
                    ])}
                />
            </div>

            {cruz.conhecimentos_receita?.itens?.length > 0 && (
                <div>
                    <h4 className="mb-2 font-semibold text-slate-900">
                        Conhecimentos de receita
                        <span className="ml-2 text-sm font-normal text-slate-400">repasses {fmtMoney(cruz.conhecimentos_receita.total_repasses)} · rendimentos {fmtMoney(cruz.conhecimentos_receita.total_rendimentos)}</span>
                    </h4>
                    <Tabela
                        colunas={['Natureza', 'Valor', 'Data', 'Localização']}
                        linhas={cruz.conhecimentos_receita.itens.map((k) => [k.natureza, <span className="font-mono">{fmtMoney(k.valor)}</span>, k.data || '—',
                            <span className="text-xs text-slate-400">{k.localizacao}</span>])}
                    />
                </div>
            )}

            <div>
                <h4 className="mb-2 font-semibold text-slate-900">Extratos de aplicação <span className="text-sm font-normal text-slate-400">{ext.meses} meses</span></h4>
                <Tabela
                    colunas={['Mês', 'Saldo anterior', 'Aplicações', 'Resgates', 'Rend. líquido', 'Saldo atual', 'Localização']}
                    vazio="Nenhum extrato de aplicação identificado."
                    linhas={ext.serie.map((s) => [
                        s.mes || '—',
                        <span className="font-mono">{fmtMoney(s.saldo_anterior)}</span>,
                        <span className="font-mono">{fmtMoney(s.aplicacoes)}</span>,
                        <span className="font-mono">{fmtMoney(s.resgates)}</span>,
                        <span className={`font-mono ${s.leitura_suspeita ? 'text-amber-600' : ''}`} title={s.leitura_suspeita ? 'Leitura suspeita do OCR' : ''}>{fmtMoney(s.rendimento_liquido)}{s.leitura_suspeita ? ' ?' : ''}</span>,
                        <span className="font-mono">{fmtMoney(s.saldo_atual)}</span>,
                        <span className="text-xs text-slate-400">{s.localizacao}</span>,
                    ])}
                />
            </div>
        </div>
    )
}
