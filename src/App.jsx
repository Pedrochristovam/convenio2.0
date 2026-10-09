import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
    AlertTriangle, ArrowRight, BookOpen, CheckCircle2, Folder, FolderOpen, FolderPlus, Inbox, Layers, Loader2, LogOut, Search, Sparkles, UploadCloud,
} from 'lucide-react'
import { api, EVENTO_SAIR, fmtData, nomeLegivel, obterToken, salvarToken, wsUrl } from './lib/api'
import PastaView from './components/PastaView'
import PastaModal from './components/PastaModal'
import ComoUsar from './components/ComoUsar'

function IndicadorPasta({ pasta }) {
    if (pasta.processando > 0 || pasta.analise?.status === 'processando') return <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400" />
    if (pasta.com_erro > 0 || pasta.analise?.status === 'erro') return <span className="h-2 w-2 rounded-full bg-rose-400" />
    if (pasta.analise?.status === 'concluido') return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
    return null
}

function situacaoPasta(p) {
    if (p.processando > 0) return ['Processando volumes', 'text-indigo-600']
    if (p.analise?.status === 'processando') return ['Analisando', 'text-indigo-600']
    if (p.com_erro > 0) return ['Volume com erro', 'text-rose-600']
    if (p.analise?.status === 'concluido') return ['Análise pronta', 'text-emerald-600']
    if (p.total_arquivos === 0) return ['Vazia', 'text-slate-400']
    return ['Pronta para analisar', 'text-amber-600']
}

function Inicio({ pastas, semPasta, stats, onNova, onAbrir, onSemPasta, onAjuda }) {
    return (
        <div className="mx-auto max-w-6xl px-10 pb-24 pt-14">
            <p className="text-sm font-medium text-indigo-600">Convênio 2.0</p>
            <h1 className="mt-2 text-4xl font-semibold tracking-tight text-slate-900">Pastas de convênio</h1>
            <p className="mt-3 max-w-2xl text-base text-slate-500">
                Cada convênio tem a sua pasta. Os volumes enviados ficam guardados nela, na ordem do processo, e a Análise Documental é gerada a partir da pasta inteira.
            </p>

            <div className="mt-10 flex flex-wrap gap-x-14 gap-y-6">
                {[
                    ['Pastas', pastas.length],
                    ['Volumes', pastas.reduce((s, p) => s + p.total_arquivos, 0)],
                    ['Páginas lidas', pastas.reduce((s, p) => s + p.total_paginas, 0).toLocaleString('pt-BR')],
                    ['Lançamentos extraídos', (stats?.total_registros ?? 0).toLocaleString('pt-BR')],
                ].map(([rot, v]) => (
                    <div key={rot}>
                        <p className="text-3xl font-semibold tabular-nums text-slate-900">{v}</p>
                        <p className="mt-1 text-sm text-slate-500">{rot}</p>
                    </div>
                ))}
            </div>

            <ol className="mt-14 grid gap-8 border-y border-slate-100 py-8 md:grid-cols-3">
                {[
                    [FolderPlus, 'Crie a pasta', 'Dê o nome do convênio; é o destino de tudo o que for enviado.'],
                    [UploadCloud, 'Envie os volumes', 'Arraste os PDFs para a pasta. O OCR lê um por vez para não pesar no computador.'],
                    [Sparkles, 'Gere a análise', 'Relatório de validação, minuta da AD em Word e conciliação em Excel.'],
                ].map(([Icone, t, d], i) => (
                    <li key={t} className="flex gap-4">
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600"><Icone className="h-5 w-5" /></div>
                        <div>
                            <p className="font-semibold text-slate-900"><span className="text-slate-300">{i + 1}.</span> {t}</p>
                            <p className="mt-1 text-sm text-slate-500">{d}</p>
                        </div>
                    </li>
                ))}
            </ol>
            <button onClick={onAjuda} className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-indigo-600 hover:text-indigo-800">
                <BookOpen className="h-4 w-4" /> Ver o guia completo de uso
            </button>

            {semPasta.length > 0 && (
                <button onClick={onSemPasta} className="mt-8 flex w-full items-center gap-4 border-l-4 border-amber-400 bg-amber-50/60 px-5 py-4 text-left hover:bg-amber-50">
                    <Inbox className="h-5 w-5 shrink-0 text-amber-600" />
                    <div className="flex-1">
                        <p className="font-medium text-amber-900">{semPasta.length} arquivo(s) enviados antes das pastas</p>
                        <p className="text-sm text-amber-800/80">Organize-os nas pastas dos convênios para gerar as análises por pasta.</p>
                    </div>
                    <ArrowRight className="h-4 w-4 text-amber-600" />
                </button>
            )}

            <div className="mt-12 flex items-end justify-between">
                <h2 className="text-lg font-semibold text-slate-900">Todas as pastas</h2>
                <button onClick={onNova} className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-600/20 hover:bg-indigo-700">
                    <FolderPlus className="h-4 w-4" /> Nova pasta
                </button>
            </div>
            {pastas.length === 0 ? (
                <div className="mt-6 py-16 text-center">
                    <Folder className="mx-auto h-12 w-12 text-slate-200" />
                    <p className="mt-3 font-medium text-slate-700">Nenhuma pasta criada</p>
                    <p className="text-sm text-slate-500">Comece criando a pasta do convênio que vai analisar.</p>
                </div>
            ) : (
                <table className="mt-4 w-full text-sm">
                    <thead>
                        <tr className="border-b border-slate-200 text-left text-[11px] uppercase tracking-wider text-slate-400">
                            <th className="py-2 font-medium">Pasta</th>
                            <th className="py-2 font-medium">Volumes</th>
                            <th className="py-2 font-medium">Páginas</th>
                            <th className="py-2 font-medium">Situação</th>
                            <th className="py-2 text-right font-medium">Atualizada</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                        {pastas.map((p) => {
                            const [sit, cor] = situacaoPasta(p)
                            return (
                                <tr key={p.id} onClick={() => onAbrir(p.id)} className="group cursor-pointer hover:bg-slate-50/80">
                                    <td className="py-3.5 pr-4">
                                        <div className="flex items-center gap-3">
                                            <Folder className="h-5 w-5 text-indigo-400 group-hover:text-indigo-600" />
                                            <div>
                                                <p className="font-medium text-slate-900">{p.nome}</p>
                                                {(p.numero_convenio || p.convenente) && (
                                                    <p className="text-xs text-slate-400">{[p.numero_convenio && `nº ${p.numero_convenio}`, p.convenente].filter(Boolean).join(' · ')}</p>
                                                )}
                                            </div>
                                        </div>
                                    </td>
                                    <td className="py-3.5 text-slate-600">{p.total_arquivos}</td>
                                    <td className="py-3.5 tabular-nums text-slate-600">{p.total_paginas}</td>
                                    <td className={`py-3.5 font-medium ${cor}`}>{sit}</td>
                                    <td className="py-3.5 text-right text-slate-400">{fmtData(p.updated_at)}</td>
                                </tr>
                            )
                        })}
                    </tbody>
                </table>
            )}
        </div>
    )
}

function SemPasta({ arquivos, pastas, onMovidos, onCriarPasta }) {
    const [selecionados, setSelecionados] = useState([])
    const [destino, setDestino] = useState('')
    const [movendo, setMovendo] = useState(false)
    const [erro, setErro] = useState(null)

    const alternar = (nome) => setSelecionados((s) => (s.includes(nome) ? s.filter((n) => n !== nome) : [...s, nome]))

    const moverPara = async (pastaId, nomes = selecionados) => {
        setMovendo(true)
        setErro(null)
        try {
            for (const nome of nomes) await api(`/pastas/${pastaId}/arquivos`, { method: 'POST', body: { arquivo_nome: nome } })
            setSelecionados([])
            onMovidos(pastaId)
        } catch (e) {
            setErro(e.message)
        } finally {
            setMovendo(false)
        }
    }

    return (
        <div className="mx-auto max-w-5xl px-10 pb-24 pt-14">
            <div className="flex items-center gap-3 text-amber-600"><Inbox className="h-6 w-6" /></div>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-900">Arquivos sem pasta</h1>
            <p className="mt-2 max-w-2xl text-slate-500">
                Volumes enviados antes de existirem pastas. Marque-os <strong className="font-medium text-slate-700">na ordem do processo</strong> (volume 1, 2, 3...) e mova para a pasta do convênio.
                Análises antigas feitas só com esses arquivos vão junto.
            </p>

            {arquivos.length === 0 ? (
                <p className="mt-16 text-center text-slate-400">Tudo organizado: nenhum arquivo fora de pasta.</p>
            ) : (
                <>
                    <ul className="mt-10 divide-y divide-slate-100 border-y border-slate-100">
                        {arquivos.map((a) => {
                            const idx = selecionados.indexOf(a.arquivo_nome)
                            return (
                                <li key={a.arquivo_nome}>
                                    <label className="flex cursor-pointer items-center gap-4 py-3.5 hover:bg-slate-50/70">
                                        <input type="checkbox" checked={idx >= 0} onChange={() => alternar(a.arquivo_nome)} className="h-4 w-4 accent-indigo-600" />
                                        <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${idx >= 0 ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-300'}`}>
                                            {idx >= 0 ? idx + 1 : '–'}
                                        </span>
                                        <div className="min-w-0 flex-1">
                                            <p className="truncate font-medium text-slate-900">{nomeLegivel(a.arquivo_nome)}</p>
                                            <p className="text-xs text-slate-500">{a.total_paginas} páginas · {a.status === 'concluido' ? 'pronto' : a.status} · {fmtData(a.updated_at)}</p>
                                        </div>
                                    </label>
                                </li>
                            )
                        })}
                    </ul>
                    <div className="sticky bottom-0 mt-6 flex flex-wrap items-center gap-3 bg-white/90 py-4 backdrop-blur">
                        <p className="mr-auto text-sm text-slate-500">{selecionados.length} selecionado(s)</p>
                        <select value={destino} onChange={(e) => setDestino(e.target.value)} className="rounded-lg border-0 bg-slate-100 px-3 py-2.5 text-sm text-slate-700 outline-none">
                            <option value="">Escolha a pasta de destino...</option>
                            {pastas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
                        </select>
                        <button onClick={() => moverPara(Number(destino))} disabled={!destino || !selecionados.length || movendo}
                            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-40">
                            {movendo && <Loader2 className="h-4 w-4 animate-spin" />} Mover para a pasta
                        </button>
                        <button onClick={() => onCriarPasta((id) => moverPara(id, selecionados))} disabled={!selecionados.length || movendo}
                            className="inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold text-indigo-700 ring-1 ring-indigo-200 hover:bg-indigo-50 disabled:opacity-40">
                            <FolderPlus className="h-4 w-4" /> Criar pasta com eles
                        </button>
                    </div>
                    {erro && <p className="text-sm text-rose-600">{erro}</p>}
                </>
            )}
        </div>
    )
}

const telaDoHash = () => {
    const h = window.location.hash
    const m = h.match(/^#\/pasta\/(\d+)/)
    if (m) return Number(m[1])
    return { '#/sem-pasta': 'sem_pasta', '#/ajuda': 'ajuda' }[h] || 'inicio'
}

const hashDaTela = (tela) => (typeof tela === 'number' ? `#/pasta/${tela}` : { sem_pasta: '#/sem-pasta', ajuda: '#/ajuda' }[tela] || '#/')

function Login({ onEntrar }) {
    const [usuario, setUsuario] = useState('')
    const [senha, setSenha] = useState('')
    const [enviando, setEnviando] = useState(false)
    const [erro, setErro] = useState(null)

    const entrar = async (e) => {
        e.preventDefault()
        setEnviando(true)
        setErro(null)
        try {
            const d = await api('/auth/login', { method: 'POST', body: { usuario, senha } })
            salvarToken(d.token)
            onEntrar()
        } catch (err) {
            setErro(err.message)
        } finally {
            setEnviando(false)
        }
    }

    return (
        <div className="flex min-h-screen items-center justify-center bg-slate-950 px-6">
            <form onSubmit={entrar} className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-2xl">
                <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500">
                        <Layers className="h-5 w-5 text-white" />
                    </div>
                    <div>
                        <p className="font-semibold text-slate-900">Convênio 2.0</p>
                        <p className="text-xs text-slate-500">Auditoria de prestação de contas</p>
                    </div>
                </div>
                <label className="mt-8 block text-sm font-medium text-slate-700">Usuário</label>
                <input value={usuario} onChange={(e) => setUsuario(e.target.value)} autoFocus autoComplete="username"
                    className="mt-1 w-full rounded-lg border-0 bg-slate-100 px-3 py-2.5 text-sm outline-none ring-indigo-500 focus:ring-2" />
                <label className="mt-4 block text-sm font-medium text-slate-700">Senha</label>
                <input type="password" value={senha} onChange={(e) => setSenha(e.target.value)} autoComplete="current-password"
                    className="mt-1 w-full rounded-lg border-0 bg-slate-100 px-3 py-2.5 text-sm outline-none ring-indigo-500 focus:ring-2" />
                {erro && <p className="mt-3 text-sm text-rose-600">{erro}</p>}
                <button type="submit" disabled={enviando || !usuario || !senha}
                    className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50">
                    {enviando && <Loader2 className="h-4 w-4 animate-spin" />} Entrar
                </button>
            </form>
        </div>
    )
}

export default function App() {
    const [config, setConfig] = useState(null)
    const [logado, setLogado] = useState(!!obterToken())

    useEffect(() => {
        api('/auth/status').then(setConfig).catch(() => setConfig({ login: false, limpar_banco: true }))
        const sair = () => setLogado(false)
        window.addEventListener(EVENTO_SAIR, sair)
        return () => window.removeEventListener(EVENTO_SAIR, sair)
    }, [])

    if (!config) return <div className="flex h-screen items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-indigo-500" /></div>
    if (config.login && !logado) return <Login onEntrar={() => setLogado(true)} />
    const sair = config.login ? () => { salvarToken(null); setLogado(false) } : null
    return <Sistema podeLimpar={config.limpar_banco} onSair={sair} />
}

function Sistema({ podeLimpar, onSair }) {
    const [pastas, setPastas] = useState([])
    const [semPasta, setSemPasta] = useState([])
    const [stats, setStats] = useState(null)
    const [tela, setTela] = useState(telaDoHash)

    useEffect(() => {
        if (telaDoHash() !== tela) window.location.hash = hashDaTela(tela)
    }, [tela])

    useEffect(() => {
        const aoMudar = () => setTela(telaDoHash())
        window.addEventListener('hashchange', aoMudar)
        return () => window.removeEventListener('hashchange', aoMudar)
    }, [])
    const [busca, setBusca] = useState('')
    const [modalNova, setModalNova] = useState(null)
    const [progresso, setProgresso] = useState({})
    const [sinal, setSinal] = useState(0)
    const [offline, setOffline] = useState(false)

    const carregarPastas = useCallback(async () => {
        try {
            const d = await api('/pastas')
            setPastas(d.pastas)
            setSemPasta(d.sem_pasta)
            setOffline(false)
        } catch {
            setOffline(true)
        }
        api('/estatisticas').then(setStats).catch(() => {})
    }, [])

    useEffect(() => { carregarPastas() }, [carregarPastas])

    useEffect(() => {
        let ws
        let vivo = true
        let timer
        const conectar = () => {
            ws = new WebSocket(wsUrl())
            ws.onmessage = (ev) => {
                const d = JSON.parse(ev.data)
                if (d.arquivo && (d.type === 'PROGRESS' || !d.type)) {
                    setProgresso((p) => ({ ...p, [d.arquivo]: { message: d.message, progress: d.progress } }))
                }
                if (['FINAL_RESULT', 'ERROR', 'DOSSIE_DONE', 'DOSSIE_ERROR'].includes(d.type)) {
                    setSinal((s) => s + 1)
                    carregarPastas()
                }
            }
            ws.onclose = () => { if (vivo) timer = setTimeout(conectar, 3000) }
        }
        conectar()
        return () => { vivo = false; clearTimeout(timer); ws?.close() }
    }, [carregarPastas])

    const ocupado = pastas.some((p) => p.processando > 0 || p.analise?.status === 'processando')
    useEffect(() => {
        if (!ocupado) return undefined
        const t = setInterval(carregarPastas, 6000)
        return () => clearInterval(t)
    }, [ocupado, carregarPastas])

    const criarPasta = async (form) => {
        const nova = await api('/pastas', { method: 'POST', body: form })
        const depois = modalNova?.depois
        setModalNova(null)
        await carregarPastas()
        if (depois) await depois(nova.id)
        setTela(nova.id)
    }

    const limparBanco = async () => {
        if (!window.confirm('Apagar TODOS os dados do sistema (pastas, volumes, extrações e análises)?\n\nEssa ação não pode ser desfeita.')) return
        await api('/limpar-banco', { method: 'DELETE' }).catch((e) => alert(e.message))
        setTela('inicio')
        carregarPastas()
    }

    const filtradas = useMemo(() => {
        const q = busca.trim().toLowerCase()
        return q ? pastas.filter((p) => [p.nome, p.numero_convenio, p.convenente].some((v) => (v || '').toLowerCase().includes(q))) : pastas
    }, [pastas, busca])

    return (
        <div className="flex h-screen overflow-hidden bg-white text-slate-900">
            {modalNova && <PastaModal onSalvar={criarPasta} onFechar={() => setModalNova(null)} />}

            <aside className="flex w-72 shrink-0 flex-col bg-slate-950 text-slate-300">
                <button onClick={() => setTela('inicio')} className="flex items-center gap-3 px-6 pb-6 pt-7 text-left">
                    <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 shadow-lg shadow-indigo-500/30">
                        <Layers className="h-5 w-5 text-white" />
                    </div>
                    <div>
                        <p className="font-semibold leading-tight text-white">Convênio 2.0</p>
                        <p className="text-xs text-slate-500">Auditoria de prestação de contas</p>
                    </div>
                </button>

                <div className="px-4">
                    <button onClick={() => setModalNova({})}
                        className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-500 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/20 transition hover:bg-indigo-400">
                        <FolderPlus className="h-4 w-4" /> Nova pasta
                    </button>
                    <div className="relative mt-4">
                        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                        <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar convênio..."
                            className="w-full rounded-lg bg-white/5 py-2 pl-9 pr-3 text-sm text-slate-200 outline-none ring-1 ring-white/5 placeholder:text-slate-500 focus:ring-indigo-500/60" />
                    </div>
                </div>

                <p className="px-6 pb-2 pt-6 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Pastas</p>
                <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 pb-4">
                    {filtradas.length === 0 && <p className="px-3 py-2 text-sm text-slate-600">{busca ? 'Nada encontrado.' : 'Nenhuma pasta ainda.'}</p>}
                    {filtradas.map((p) => {
                        const ativa = tela === p.id
                        const Icone = ativa ? FolderOpen : Folder
                        return (
                            <button key={p.id} onClick={() => setTela(p.id)}
                                className={`group relative flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition ${ativa ? 'bg-white/10 text-white' : 'hover:bg-white/5 hover:text-white'}`}>
                                {ativa && <span className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-indigo-400" />}
                                <Icone className={`h-4 w-4 shrink-0 ${ativa ? 'text-indigo-300' : 'text-slate-500 group-hover:text-slate-300'}`} />
                                <div className="min-w-0 flex-1">
                                    <p className="truncate text-sm font-medium">{p.nome}</p>
                                    <p className="text-xs text-slate-500">{p.total_arquivos} volume(s) · {p.total_paginas} págs</p>
                                </div>
                                <IndicadorPasta pasta={p} />
                            </button>
                        )
                    })}
                </nav>

                <div className="space-y-1 border-t border-white/5 px-3 py-4">
                    <button onClick={() => setTela('ajuda')}
                        className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${tela === 'ajuda' ? 'bg-white/10 text-white' : 'hover:bg-white/5 hover:text-white'}`}>
                        <BookOpen className="h-4 w-4 text-indigo-300" />
                        <span className="flex-1 text-left">Como usar</span>
                    </button>
                    {semPasta.length > 0 && (
                        <button onClick={() => setTela('sem_pasta')}
                            className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${tela === 'sem_pasta' ? 'bg-white/10 text-white' : 'hover:bg-white/5 hover:text-white'}`}>
                            <Inbox className="h-4 w-4 text-amber-400" />
                            <span className="flex-1 text-left">Arquivos sem pasta</span>
                            <span className="rounded-full bg-amber-400/15 px-2 text-xs font-semibold text-amber-300">{semPasta.length}</span>
                        </button>
                    )}
                    {offline && (
                        <p className="flex items-center gap-2 px-3 py-1 text-xs text-rose-400"><AlertTriangle className="h-3.5 w-3.5" /> Servidor fora do ar</p>
                    )}
                    {podeLimpar && (
                        <button onClick={limparBanco} className="w-full px-3 py-1 text-left text-xs text-slate-600 hover:text-rose-400">Limpar todos os dados</button>
                    )}
                    {onSair && (
                        <button onClick={onSair} className="flex w-full items-center gap-2 px-3 py-1 text-left text-xs text-slate-500 hover:text-white">
                            <LogOut className="h-3.5 w-3.5" /> Sair
                        </button>
                    )}
                </div>
            </aside>

            <main className="flex-1 overflow-y-auto">
                {tela === 'inicio' && (
                    <Inicio pastas={pastas} semPasta={semPasta} stats={stats} onNova={() => setModalNova({})}
                        onAbrir={setTela} onSemPasta={() => setTela('sem_pasta')} onAjuda={() => setTela('ajuda')} />
                )}
                {tela === 'ajuda' && <ComoUsar />}
                {tela === 'sem_pasta' && (
                    <SemPasta arquivos={semPasta} pastas={pastas}
                        onMovidos={async (id) => { await carregarPastas(); setTela(id) }}
                        onCriarPasta={(depois) => setModalNova({ depois })} />
                )}
                {typeof tela === 'number' && (
                    <PastaView key={tela} pastaId={tela} progresso={progresso} sinal={sinal} onMudou={carregarPastas}
                        onExcluida={() => { setTela('inicio'); carregarPastas() }} />
                )}
            </main>
        </div>
    )
}
