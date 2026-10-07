import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
    AlertCircle, ArrowDown, ArrowUp, BarChart3, CheckCircle2, ChevronRight, ClipboardCheck, FileText, FolderOpen,
    Loader2, Pencil, RefreshCw, Sparkles, Trash2, UploadCloud, X,
} from 'lucide-react'
import { api, fmtData, nomeLegivel } from '../lib/api'
import AnaliseResultado from './AnaliseResultado'
import ExtratoFinanceiro from './ExtratoFinanceiro'
import PastaModal from './PastaModal'

const STATUS = {
    fila: ['Na fila', 'text-slate-500 bg-slate-100'],
    processando: ['Processando', 'text-indigo-700 bg-indigo-50'],
    concluido: ['Pronto', 'text-emerald-700 bg-emerald-50'],
    erro: ['Erro', 'text-rose-700 bg-rose-50'],
}

function StatusVolume({ status }) {
    const [rot, cor] = STATUS[status] || [status, 'text-slate-500 bg-slate-100']
    return (
        <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${cor}`}>
            {status === 'processando' && <Loader2 className="h-3 w-3 animate-spin" />}
            {status === 'concluido' && <CheckCircle2 className="h-3 w-3" />}
            {rot}
        </span>
    )
}

const ABAS_PASTA = ['volumes', 'analise', 'extrato']
const abaDoHash = (pastaId) => {
    const [, , id, a] = window.location.hash.split('/')
    return Number(id) === pastaId && ABAS_PASTA.includes(a) ? a : 'volumes'
}

export default function PastaView({ pastaId, progresso, sinal, onMudou, onExcluida }) {
    const [pasta, setPasta] = useState(null)
    const [erro, setErro] = useState(null)
    const [aba, setAba] = useState(() => abaDoHash(pastaId))

    useEffect(() => {
        window.history.replaceState(null, '', `#/pasta/${pastaId}${aba === 'volumes' ? '' : `/${aba}`}`)
    }, [pastaId, aba])
    const [enviando, setEnviando] = useState([])
    const [arrastando, setArrastando] = useState(false)
    const [editando, setEditando] = useState(false)
    const [analiseId, setAnaliseId] = useState(null)
    const [dossie, setDossie] = useState(null)
    const [extratoArquivo, setExtratoArquivo] = useState(null)
    const [extrato, setExtrato] = useState(null)
    const inputRef = useRef(null)

    const carregar = useCallback(async () => {
        try {
            setPasta(await api(`/pastas/${pastaId}`))
        } catch (e) {
            setErro(e.message)
        }
    }, [pastaId])

    useEffect(() => { carregar() }, [carregar])

    useEffect(() => { if (sinal) carregar() }, [sinal, carregar])

    const ocupado = pasta && (pasta.arquivos.some((a) => ['fila', 'processando'].includes(a.status)) || pasta.analises.some((a) => a.status === 'processando'))
    useEffect(() => {
        if (!ocupado) return undefined
        const t = setInterval(carregar, 4000)
        return () => clearInterval(t)
    }, [ocupado, carregar])

    const analiseSelecionada = pasta?.analises.find((a) => a.id === analiseId) || pasta?.analises[0]
    useEffect(() => {
        if (!analiseSelecionada) { setDossie(null); return }
        if (analiseSelecionada.status !== 'concluido') { setDossie(null); return }
        if (dossie?.id === analiseSelecionada.id && dossie.status === 'concluido') return
        api(`/dossies/${analiseSelecionada.id}`).then(setDossie).catch((e) => setErro(e.message))
    }, [analiseSelecionada?.id, analiseSelecionada?.status]) // eslint-disable-line react-hooks/exhaustive-deps

    const comExtrato = pasta?.arquivos.filter((a) => a.status === 'concluido' && (a.total_resumos > 0 || a.total_cc > 0)) || []
    const extratoAlvo = comExtrato.some((a) => a.arquivo_nome === extratoArquivo) ? extratoArquivo : comExtrato[0]?.arquivo_nome
    useEffect(() => {
        if (aba !== 'extrato' || !extratoAlvo) return
        setExtrato(null)
        api(`/resultados/${encodeURIComponent(extratoAlvo)}`).then(setExtrato).catch((e) => setErro(e.message))
    }, [aba, extratoAlvo])

    const enviarArquivos = async (lista) => {
        const arquivos = Array.from(lista || []).filter((f) => /\.(pdf|png|jpe?g)$/i.test(f.name))
        if (!arquivos.length) return
        setErro(null)
        setEnviando(arquivos.map((f) => f.name))
        for (const f of arquivos) {
            const form = new FormData()
            form.append('file', f)
            form.append('pasta_id', String(pastaId))
            try {
                await api('/extract', { method: 'POST', form })
            } catch (e) {
                setErro(`${f.name}: ${e.message}`)
            }
            setEnviando((prev) => prev.filter((n) => n !== f.name))
            await carregar()
        }
        onMudou()
    }

    const mover = async (idx, delta) => {
        const nomes = pasta.arquivos.map((a) => a.arquivo_nome)
        const [item] = nomes.splice(idx, 1)
        nomes.splice(idx + delta, 0, item)
        try {
            setPasta(await api(`/pastas/${pastaId}/ordem`, { method: 'PUT', body: { arquivos: nomes } }))
        } catch (e) {
            setErro(e.message)
        }
    }

    const remover = async (arquivo) => {
        if (!window.confirm(`Tirar "${nomeLegivel(arquivo)}" desta pasta?\n\nO arquivo vai para "Arquivos sem pasta" e os dados extraídos continuam salvos.`)) return
        try {
            setPasta(await api(`/pastas/${pastaId}/arquivos/${encodeURIComponent(arquivo)}`, { method: 'DELETE' }))
            onMudou()
        } catch (e) {
            setErro(e.message)
        }
    }

    const gerarAnalise = async () => {
        setErro(null)
        try {
            const r = await api(`/pastas/${pastaId}/analise`, { method: 'POST' })
            setAnaliseId(r.id)
            setAba('analise')
            await carregar()
            onMudou()
        } catch (e) {
            setErro(e.message)
        }
    }

    const reprocessarAnalise = async (id) => {
        try {
            await api(`/dossies/${id}/reprocessar`, { method: 'POST' })
            await carregar()
        } catch (e) {
            setErro(e.message)
        }
    }

    const excluirAnalise = async (id) => {
        if (!window.confirm('Excluir esta versão da análise?')) return
        await api(`/dossies/${id}`, { method: 'DELETE' }).catch((e) => setErro(e.message))
        setAnaliseId(null)
        await carregar()
        onMudou()
    }

    const excluirPasta = async () => {
        if (!window.confirm(`Excluir a pasta "${pasta.nome}"?\n\nOs volumes, os dados extraídos e as análises desta pasta serão apagados.`)) return
        try {
            await api(`/pastas/${pastaId}`, { method: 'DELETE' })
            onExcluida()
        } catch (e) {
            setErro(e.message)
        }
    }

    const salvarEdicao = async (form) => {
        setPasta(await api(`/pastas/${pastaId}`, { method: 'PATCH', body: form }))
        setEditando(false)
        onMudou()
    }

    if (!pasta) {
        return (
            <div className="flex h-full items-center justify-center text-slate-400">
                {erro ? <p className="text-rose-600">{erro}</p> : <Loader2 className="h-6 w-6 animate-spin" />}
            </div>
        )
    }

    const prontos = pasta.arquivos.filter((a) => a.status === 'concluido')
    const pendentes = pasta.arquivos.filter((a) => ['fila', 'processando'].includes(a.status))
    const analiseRodando = pasta.analises.some((a) => a.status === 'processando')
    const podeAnalisar = prontos.length > 0 && pendentes.length === 0 && !analiseRodando
    const totalPaginas = pasta.arquivos.reduce((s, a) => s + (a.total_paginas || 0), 0)
    const abas = [
        ['volumes', 'Volumes', FileText, pasta.arquivos.length],
        ['analise', 'Análise Documental', ClipboardCheck, pasta.analises.length || null],
        ['extrato', 'Extrato financeiro', BarChart3, comExtrato.length || null],
    ]

    return (
        <div className="mx-auto max-w-6xl px-10 pb-24 pt-10">
            {editando && <PastaModal inicial={pasta} onSalvar={salvarEdicao} onFechar={() => setEditando(false)} />}

            <nav className="flex items-center gap-1 text-xs text-slate-400">
                <span>Pastas</span><ChevronRight className="h-3 w-3" /><span className="text-slate-600">{pasta.nome}</span>
            </nav>

            <header className="mt-4 flex flex-wrap items-start justify-between gap-6">
                <div className="flex items-start gap-5">
                    <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-lg shadow-indigo-500/25">
                        <FolderOpen className="h-7 w-7" />
                    </div>
                    <div>
                        <h1 className="text-3xl font-semibold tracking-tight text-slate-900">{pasta.nome}</h1>
                        <p className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-500">
                            {pasta.numero_convenio && <span>Convênio nº <strong className="font-medium text-slate-700">{pasta.numero_convenio}</strong></span>}
                            {pasta.convenente && <span>{pasta.convenente}</span>}
                            <span>{pasta.arquivos.length} volume(s) · {totalPaginas} páginas</span>
                            <span>criada em {fmtData(pasta.created_at)}</span>
                        </p>
                        {pasta.observacao && <p className="mt-1 text-sm text-slate-400">{pasta.observacao}</p>}
                    </div>
                </div>
                <div className="flex items-center gap-1">
                    <button onClick={() => setEditando(true)} className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100">
                        <Pencil className="h-4 w-4" /> Editar
                    </button>
                    <button onClick={excluirPasta} className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-rose-600 hover:bg-rose-50">
                        <Trash2 className="h-4 w-4" /> Excluir
                    </button>
                </div>
            </header>

            <nav className="mt-10 flex gap-8 border-b border-slate-200">
                {abas.map(([k, rot, Icone, n]) => (
                    <button key={k} onClick={() => setAba(k)}
                        className={`-mb-px flex items-center gap-2 border-b-2 pb-3 text-sm font-medium transition ${aba === k ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-800'}`}>
                        <Icone className="h-4 w-4" /> {rot}
                        {n !== null && <span className={`rounded-full px-1.5 text-xs ${aba === k ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-500'}`}>{n}</span>}
                    </button>
                ))}
            </nav>

            {erro && (
                <div className="mt-6 flex items-start justify-between gap-4 border-l-4 border-rose-500 bg-rose-50/60 px-4 py-3 text-sm text-rose-800">
                    <span className="flex items-start gap-2"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /> {erro}</span>
                    <button onClick={() => setErro(null)}><X className="h-4 w-4" /></button>
                </div>
            )}

            {aba === 'volumes' && (
                <div className="mt-8 space-y-8">
                    <div
                        onClick={() => inputRef.current?.click()}
                        onDragOver={(e) => { e.preventDefault(); setArrastando(true) }}
                        onDragLeave={() => setArrastando(false)}
                        onDrop={(e) => { e.preventDefault(); setArrastando(false); enviarArquivos(e.dataTransfer.files) }}
                        className={`group flex cursor-pointer items-center gap-6 rounded-2xl border-2 border-dashed px-8 py-7 transition ${arrastando ? 'border-indigo-500 bg-indigo-50' : 'border-slate-200 hover:border-indigo-400 hover:bg-indigo-50/40'}`}
                    >
                        <input ref={inputRef} type="file" multiple accept=".pdf,.png,.jpg,.jpeg" className="hidden"
                            onChange={(e) => { enviarArquivos(e.target.files); e.target.value = '' }} />
                        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-indigo-600 text-white shadow-lg shadow-indigo-600/25 transition group-hover:scale-105">
                            {enviando.length ? <Loader2 className="h-6 w-6 animate-spin" /> : <UploadCloud className="h-6 w-6" />}
                        </div>
                        <div>
                            <p className="text-base font-semibold text-slate-900">
                                {enviando.length ? `Enviando ${enviando.length} arquivo(s) para esta pasta...` : `Adicionar volumes a "${pasta.nome}"`}
                            </p>
                            <p className="mt-0.5 text-sm text-slate-500">
                                Arraste os PDFs aqui ou clique para escolher (pode selecionar vários). Eles entram na ordem em que forem enviados, e o OCR processa um por vez.
                            </p>
                        </div>
                    </div>

                    {pasta.arquivos.length === 0 ? (
                        <p className="py-10 text-center text-sm text-slate-400">Esta pasta ainda não tem volumes.</p>
                    ) : (
                        <ol className="divide-y divide-slate-100 border-y border-slate-100">
                            {pasta.arquivos.map((a, idx) => {
                                const prog = progresso[a.arquivo_nome]
                                const rodando = a.status === 'processando'
                                return (
                                    <li key={a.arquivo_nome} className="group flex items-center gap-5 py-4">
                                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-sm font-semibold text-slate-600">{idx + 1}</span>
                                        <div className="min-w-0 flex-1">
                                            <p className="truncate font-medium text-slate-900" title={a.arquivo_nome}>{nomeLegivel(a.arquivo_nome)}</p>
                                            {rodando || a.status === 'fila' ? (
                                                <div className="mt-1.5 max-w-md">
                                                    <p className="truncate text-xs text-slate-500">{prog?.message || a.mensagem}</p>
                                                    {rodando && (
                                                        <div className="mt-1 h-1 overflow-hidden rounded-full bg-slate-100">
                                                            <div className="h-full bg-indigo-500 transition-all duration-500" style={{ width: `${Math.max(3, prog?.progress || 0)}%` }} />
                                                        </div>
                                                    )}
                                                </div>
                                            ) : (
                                                <p className={`mt-0.5 text-xs ${a.status === 'erro' ? 'text-rose-600' : 'text-slate-500'}`}>
                                                    {a.status === 'erro' ? a.mensagem : `${a.total_paginas} páginas · ${a.total_resumos} resumos mensais · ${a.total_cc} lançamentos de conta corrente`}
                                                </p>
                                            )}
                                        </div>
                                        <StatusVolume status={a.status} />
                                        <div className="flex items-center gap-0.5 opacity-60 transition group-hover:opacity-100">
                                            {a.status === 'concluido' && (a.total_resumos > 0 || a.total_cc > 0) && (
                                                <button onClick={() => { setExtratoArquivo(a.arquivo_nome); setAba('extrato') }}
                                                    className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-indigo-600 hover:bg-indigo-50">Ver extrato</button>
                                            )}
                                            <button disabled={idx === 0} onClick={() => mover(idx, -1)} title="Subir"
                                                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-30"><ArrowUp className="h-4 w-4" /></button>
                                            <button disabled={idx === pasta.arquivos.length - 1} onClick={() => mover(idx, 1)} title="Descer"
                                                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-30"><ArrowDown className="h-4 w-4" /></button>
                                            <button onClick={() => remover(a.arquivo_nome)} disabled={rodando || a.status === 'fila'} title="Tirar da pasta"
                                                className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600 disabled:opacity-30"><Trash2 className="h-4 w-4" /></button>
                                        </div>
                                    </li>
                                )
                            })}
                        </ol>
                    )}

                    {pasta.arquivos.length > 0 && (
                        <div className="flex flex-wrap items-center justify-between gap-4">
                            <p className="text-sm text-slate-500">
                                {pendentes.length > 0
                                    ? `Aguardando ${pendentes.length} volume(s) terminar o processamento.`
                                    : analiseRodando ? 'Há uma análise em andamento.'
                                        : 'A análise usa todos os volumes prontos, na ordem acima.'}
                            </p>
                            <button onClick={gerarAnalise} disabled={!podeAnalisar}
                                className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-900/10 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40">
                                <Sparkles className="h-4 w-4" /> {pasta.analises.length ? 'Gerar nova análise documental' : 'Gerar análise documental'}
                            </button>
                        </div>
                    )}
                </div>
            )}

            {aba === 'analise' && (
                <div className="mt-8">
                    {pasta.analises.length === 0 ? (
                        <div className="py-16 text-center">
                            <ClipboardCheck className="mx-auto h-10 w-10 text-slate-300" />
                            <p className="mt-3 text-base font-medium text-slate-700">Nenhuma análise gerada ainda</p>
                            <p className="mt-1 text-sm text-slate-500">Envie os volumes do convênio e gere a análise com todos eles, na ordem do processo.</p>
                            <button onClick={gerarAnalise} disabled={!podeAnalisar}
                                className="mt-6 inline-flex items-center gap-2 rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-40">
                                <Sparkles className="h-4 w-4" /> Gerar análise documental
                            </button>
                        </div>
                    ) : (
                        <>
                            <div className="mb-8 flex flex-wrap items-center gap-3">
                                {pasta.analises.length > 1 && (
                                    <select value={analiseSelecionada?.id} onChange={(e) => setAnaliseId(Number(e.target.value))}
                                        className="rounded-lg border-0 bg-slate-100 px-3 py-2 text-sm font-medium text-slate-700 outline-none">
                                        {pasta.analises.map((a, i) => (
                                            <option key={a.id} value={a.id}>{i === 0 ? 'Mais recente' : `Versão #${a.id}`} · {fmtData(a.created_at)}</option>
                                        ))}
                                    </select>
                                )}
                                <p className="text-sm text-slate-500">
                                    Análise #{analiseSelecionada.id} · {analiseSelecionada.arquivos.length} volume(s) · {fmtData(analiseSelecionada.updated_at)}
                                </p>
                                <div className="ml-auto flex gap-1">
                                    <button onClick={gerarAnalise} disabled={!podeAnalisar}
                                        className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-40">
                                        <RefreshCw className="h-4 w-4" /> Gerar de novo
                                    </button>
                                    <button onClick={() => excluirAnalise(analiseSelecionada.id)} disabled={analiseSelecionada.status === 'processando'}
                                        className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-rose-600 hover:bg-rose-50 disabled:opacity-40">
                                        <Trash2 className="h-4 w-4" /> Excluir versão
                                    </button>
                                </div>
                            </div>

                            {analiseSelecionada.status === 'processando' && (
                                <div className="py-16 text-center">
                                    <Loader2 className="mx-auto h-8 w-8 animate-spin text-indigo-500" />
                                    <p className="mt-4 font-medium text-slate-800">{analiseSelecionada.mensagem || 'Analisando...'}</p>
                                    <div className="mx-auto mt-4 h-1.5 max-w-sm overflow-hidden rounded-full bg-slate-100">
                                        <div className="h-full bg-indigo-500 transition-all duration-700" style={{ width: `${analiseSelecionada.progresso || 0}%` }} />
                                    </div>
                                    <p className="mt-3 text-xs text-slate-400">A extração com IA respeita o limite do Groq; dossiês grandes levam alguns minutos.</p>
                                </div>
                            )}
                            {analiseSelecionada.status === 'erro' && (
                                <div className="py-12 text-center">
                                    <AlertCircle className="mx-auto h-8 w-8 text-rose-500" />
                                    <p className="mt-3 font-medium text-slate-800">A análise não terminou</p>
                                    <p className="mt-1 text-sm text-slate-500">{analiseSelecionada.mensagem}</p>
                                    <button onClick={() => reprocessarAnalise(analiseSelecionada.id)}
                                        className="mt-5 inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800">
                                        <RefreshCw className="h-4 w-4" /> Tentar de novo
                                    </button>
                                </div>
                            )}
                            {analiseSelecionada.status === 'concluido' && (
                                dossie?.id === analiseSelecionada.id && dossie.resultado
                                    ? <AnaliseResultado dossie={dossie} onAtualizar={setDossie} />
                                    : <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
                            )}
                        </>
                    )}
                </div>
            )}

            {aba === 'extrato' && (
                <div className="mt-8">
                    {comExtrato.length === 0 ? (
                        <p className="py-16 text-center text-sm text-slate-400">Nenhum volume desta pasta tem extratos bancários reconhecidos.</p>
                    ) : (
                        <>
                            {comExtrato.length > 1 && (
                                <div className="mb-8 flex flex-wrap gap-2">
                                    {comExtrato.map((a) => (
                                        <button key={a.arquivo_nome} onClick={() => setExtratoArquivo(a.arquivo_nome)}
                                            className={`max-w-xs truncate rounded-full px-3.5 py-1.5 text-xs font-semibold ring-1 ring-inset ${extratoAlvo === a.arquivo_nome ? 'bg-slate-900 text-white ring-slate-900' : 'text-slate-600 ring-slate-200 hover:bg-slate-50'}`}>
                                            {nomeLegivel(a.arquivo_nome)}
                                        </button>
                                    ))}
                                </div>
                            )}
                            {extrato && extrato.arquivo === extratoAlvo
                                ? <ExtratoFinanceiro key={extratoAlvo} resultadoInicial={extrato} arquivo={extratoAlvo} />
                                : <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>}
                        </>
                    )}
                </div>
            )}
        </div>
    )
}
