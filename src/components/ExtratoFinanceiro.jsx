import React, { useCallback, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, ChevronDown, Download, FileSpreadsheet, Loader2, Pencil, Save } from 'lucide-react'
import { BACKEND_URL, fetchAuth, fmtBRL } from '../lib/api'

const parseData = (s) => {
    if (!s) return new Date(NaN)
    if (s === 'HOJE') return new Date()
    const p = s.split('/')
    return p.length === 3 ? new Date(p[2], p[1] - 1, p[0]) : new Date(NaN)
}

const calcularPoupanca = (valorInicial, dataInicioStr, dataFimStr, selic, tr) => {
    const d1 = parseData(dataInicioStr)
    const d2 = parseData(dataFimStr)
    if (Number.isNaN(d1.getTime()) || Number.isNaN(d2.getTime())) return valorInicial
    const qtdDias = Math.floor((d2 - d1) / (1000 * 60 * 60 * 24))
    if (qtdDias > 30) return valorInicial
    const sVal = parseFloat(selic) || 0
    const tVal = parseFloat(tr) || 0
    const taxaMensal = sVal > 8.5 ? 0.005 + tVal / 100 : (sVal * 0.7) / 100 / 12 + tVal / 100
    return parseFloat((valorInicial * Math.pow(1 + taxaMensal, qtdDias / 30)).toFixed(2))
}

const diasUteis = (inicio, fim) => {
    let count = 0
    const cur = new Date(inicio.getTime())
    while (cur < fim) {
        cur.setDate(cur.getDate() + 1)
        const dia = cur.getDay()
        if (dia !== 0 && dia !== 6) count++
    }
    return count
}

const calcularCDI = (valorInicial, dataInicioStr, dataFimStr, cdiAnual, percentualCDI) => {
    const d1 = parseData(dataInicioStr)
    const d2 = parseData(dataFimStr)
    if (Number.isNaN(d1.getTime()) || Number.isNaN(d2.getTime()) || d1 >= d2) return valorInicial
    const taxaDiaria = Math.pow(1 + (parseFloat(cdiAnual) || 0) / 100, 1 / 252) - 1
    const taxaAplicada = taxaDiaria * ((parseFloat(percentualCDI) || 100) / 100)
    return parseFloat((valorInicial * Math.pow(1 + taxaAplicada, diasUteis(d1, d2))).toFixed(2))
}

function CelulaEditavel({ value, onEdit, editado }) {
    const [editando, setEditando] = useState(false)
    const [rascunho, setRascunho] = useState('')

    const confirmar = () => {
        setEditando(false)
        const v = parseFloat(rascunho.replace(/\./g, '').replace(',', '.'))
        if (!Number.isNaN(v)) onEdit(v)
    }

    if (editando) {
        return (
            <input
                autoFocus
                value={rascunho}
                onChange={(e) => setRascunho(e.target.value)}
                onBlur={confirmar}
                onKeyDown={(e) => { if (e.key === 'Enter') confirmar(); if (e.key === 'Escape') setEditando(false) }}
                className="w-28 text-right border-b-2 border-indigo-500 bg-indigo-50/60 px-1 py-0.5 text-sm outline-none font-mono"
            />
        )
    }
    return (
        <button
            type="button"
            onClick={() => { setRascunho(fmtBRL(value)); setEditando(true) }}
            title="Clique para corrigir"
            className={`group inline-flex items-center gap-1 rounded px-1 font-mono tabular-nums transition-colors hover:bg-indigo-50 ${editado ? 'bg-amber-100 text-amber-900' : ''}`}
        >
            {fmtBRL(value)}
            <Pencil className={`h-3 w-3 shrink-0 ${editado ? 'text-amber-500' : 'text-slate-300 opacity-0 group-hover:opacity-100'}`} />
        </button>
    )
}

function ModalConfirmacao({ edicoes, onConfirmar, onCancelar, salvando }) {
    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 backdrop-blur-sm p-4">
            <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl animate-in">
                <div className="px-6 pt-6">
                    <h3 className="text-lg font-semibold text-slate-900">Confirmar correções</h3>
                    <p className="text-sm text-slate-500">Revise os valores antes de gravar no banco.</p>
                </div>
                <div className="px-6 py-4 max-h-80 overflow-y-auto divide-y divide-slate-100">
                    {edicoes.map((e) => (
                        <div key={e.chave} className="py-2.5">
                            <p className="text-[11px] font-medium uppercase tracking-wider text-slate-400">{e.rotulo}</p>
                            <p className="text-sm font-mono">
                                <span className="text-rose-500 line-through">{fmtBRL(e.antes)}</span>
                                <span className="mx-2 text-slate-300">→</span>
                                <span className="font-semibold text-emerald-700">{fmtBRL(e.depois)}</span>
                            </p>
                        </div>
                    ))}
                </div>
                <div className="flex justify-end gap-2 border-t border-slate-100 px-6 py-4">
                    <button onClick={onCancelar} disabled={salvando} className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100">
                        Cancelar
                    </button>
                    <button onClick={onConfirmar} disabled={salvando} className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700">
                        {salvando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                        {salvando ? 'Salvando...' : 'Gravar correções'}
                    </button>
                </div>
            </div>
        </div>
    )
}

function Secao({ titulo, subtitulo, aberta, onAlternar, children }) {
    return (
        <section className="border-t border-slate-200 pt-6">
            <button onClick={onAlternar} className="flex w-full items-end justify-between text-left">
                <div>
                    <h3 className="text-lg font-semibold tracking-tight text-slate-900">{titulo}</h3>
                    {subtitulo && <p className="text-sm text-slate-500">{subtitulo}</p>}
                </div>
                <ChevronDown className={`h-5 w-5 text-slate-400 transition-transform ${aberta ? 'rotate-180' : ''}`} />
            </button>
            {aberta && <div className="mt-4 animate-in">{children}</div>}
        </section>
    )
}

export default function ExtratoFinanceiro({ resultadoInicial, arquivo }) {
    const [results, setResults] = useState(resultadoInicial)
    const [metodo, setMetodo] = useState('cdi')
    const [dataInicio, setDataInicio] = useState('01/01/2023')
    const [dataFim, setDataFim] = useState('HOJE')
    const [fatorManual, setFatorManual] = useState('')
    const [selic, setSelic] = useState(10.75)
    const [tr, setTr] = useState(0)
    const [cdiAnual, setCdiAnual] = useState(10.65)
    const [percentualCDI, setPercentualCDI] = useState(100)
    const [aplicado, setAplicado] = useState(null)
    const [aviso, setAviso] = useState(null)
    const [abertas, setAbertas] = useState({ cc: true, inv: true })
    const [pendentes, setPendentes] = useState({})
    const [gravadas, setGravadas] = useState(new Set())
    const [modal, setModal] = useState(false)
    const [salvando, setSalvando] = useState(false)

    const resumos = results?.resumos_mensais || {}
    const paginas = Object.keys(resumos).sort((a, b) => Number(a) - Number(b))
    const movs = results?.movimentacoes_cc || []
    const temInvest = paginas.length > 0
    const temCC = movs.length > 0

    const saldoFinal = useMemo(() => {
        if (temInvest) {
            const s = resumos[paginas[paginas.length - 1]]?.campos?.saldo_atual
            if (s !== undefined && s !== null) return s
        }
        if (temCC) {
            const s = movs[movs.length - 1]?.saldo
            if (s !== undefined && s !== null) return s
        }
        return null
    }, [resumos, paginas, movs, temInvest, temCC])

    const corrigir = useCallback((valor) => {
        if (!aplicado) return valor
        if (aplicado.fator) return valor * aplicado.fator
        if (aplicado.metodo === 'poupanca') return calcularPoupanca(valor, dataInicio, dataFim, selic, tr)
        return calcularCDI(valor, dataInicio, dataFim, cdiAnual, percentualCDI)
    }, [aplicado, dataInicio, dataFim, selic, tr, cdiAnual, percentualCDI])

    const calcular = () => {
        setAviso(null)
        if (fatorManual) {
            setAplicado({ metodo, fator: parseFloat(fatorManual) })
            return
        }
        if (metodo === 'poupanca') {
            const dias = Math.floor((parseData(dataFim) - parseData(dataInicio)) / (1000 * 60 * 60 * 24))
            if (dias > 30) setAviso(`Período de ${dias} dias excede 30 dias — a poupança não aplica correção por regra definida.`)
        }
        setAplicado({ metodo, fator: null })
    }

    const resetar = (fn) => (e) => { fn(e.target.value); setAplicado(null) }

    const saldos = paginas.map((p) => resumos[p]?.campos?.saldo_atual || 0)
    const rendimentos = [
        ...paginas.map((p) => ({ desc: 'Rendimento (aplicação)', val: resumos[p].campos?.rendimento_bruto || resumos[p].campos?.rendimento_liquido || 0, p })),
        ...movs.filter((m) => /(rendimento|juros|aplic)/i.test(m.historico || '')).map((m) => ({ desc: m.historico, val: Math.abs(m.valor), p: m.pagina })),
    ].filter((x) => x.val > 0)
    const somaSaldos = saldos.reduce((a, b) => a + b, 0)
    const somaRend = rendimentos.reduce((a, b) => a + b.val, 0)

    const gruposCC = useMemo(() => movs.reduce((acc, m) => {
        const dt = m.data_movimento || m.data_balancete || 'Sem data'
        ;(acc[dt] = acc[dt] || []).push(m)
        return acc
    }, {}), [movs])

    const registrar = (chave, rotulo, pagina, campo, antes, depois) => {
        setPendentes((prev) => {
            const n = { ...prev }
            if (String(antes) === String(depois)) delete n[chave]
            else n[chave] = { chave, rotulo, pagina, campo, antes, depois }
            return n
        })
    }

    const gravar = async () => {
        setSalvando(true)
        try {
            const novos = { ...resumos }
            for (const e of Object.values(pendentes)) {
                await fetchAuth(`${BACKEND_URL}/resumo-mensal/${encodeURIComponent(arquivo)}/${e.pagina}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ campo: e.campo, valor: e.depois }),
                })
                novos[e.pagina] = { ...novos[e.pagina], campos: { ...novos[e.pagina].campos, [e.campo]: e.depois } }
            }
            setResults({ ...results, resumos_mensais: novos })
            setGravadas((prev) => new Set([...prev, ...Object.keys(pendentes)]))
            setPendentes({})
            setModal(false)
        } catch (e) {
            alert('Erro ao salvar: ' + e.message)
        } finally {
            setSalvando(false)
        }
    }

    const exportar = async (tipo) => {
        try {
            const r = await fetchAuth(`${BACKEND_URL}/export/${tipo}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...results, metodoCalculo: metodo, dataInicio, fatorCalculo: fatorManual ? parseFloat(fatorManual) : 1 }),
            })
            const a = document.createElement('a')
            a.href = URL.createObjectURL(await r.blob())
            a.download = `Auditoria_${Date.now()}.${tipo === 'pdf' ? 'pdf' : 'xlsx'}`
            a.click()
            URL.revokeObjectURL(a.href)
        } catch (e) {
            alert('Erro ao gerar arquivo para exportação.')
        }
    }

    if (!temInvest && !temCC) {
        return (
            <div className="py-16 text-center">
                <p className="text-base font-medium text-slate-700">Este volume não tem extratos bancários reconhecidos.</p>
                <p className="mt-1 text-sm text-slate-500">É normal em volumes de celebração ou documentos. O texto lido continua disponível para a Análise Documental.</p>
            </div>
        )
    }

    const inputCls = 'bg-transparent border-b border-slate-300 px-1 py-1 text-sm font-mono outline-none focus:border-indigo-500'
    const nPend = Object.keys(pendentes).length

    return (
        <div className="space-y-8">
            {modal && (
                <ModalConfirmacao edicoes={Object.values(pendentes)} onConfirmar={gravar} onCancelar={() => { setPendentes({}); setModal(false) }} salvando={salvando} />
            )}

            {nPend > 0 && (
                <div className="sticky top-4 z-30 flex justify-center">
                    <button onClick={() => setModal(true)} className="inline-flex items-center gap-2 rounded-full bg-amber-500 px-6 py-2.5 text-sm font-semibold text-white shadow-lg shadow-amber-500/30 hover:bg-amber-600">
                        <Save className="h-4 w-4" /> Gravar {nPend} correção(ões)
                    </button>
                </div>
            )}

            {saldoFinal !== null && (
                <div className={`flex items-center gap-5 border-l-4 py-2 pl-5 ${saldoFinal === 0 ? 'border-emerald-500' : 'border-rose-500'}`}>
                    {saldoFinal === 0
                        ? <CheckCircle2 className="h-9 w-9 shrink-0 text-emerald-500" />
                        : <AlertTriangle className="h-9 w-9 shrink-0 text-rose-500" />}
                    <div className="flex-1">
                        <p className={`text-lg font-semibold ${saldoFinal === 0 ? 'text-emerald-800' : 'text-rose-800'}`}>
                            {saldoFinal === 0 ? 'Conta totalmente zerada' : 'Saldo remanescente detectado'}
                        </p>
                        <p className="text-sm text-slate-500">
                            {saldoFinal === 0
                                ? `A movimentação encerrou sem saldo em ${temInvest ? 'aplicação' : 'conta corrente'}.`
                                : 'O extrato termina com saldo em aberto; avalie glosa ou correção monetária.'}
                        </p>
                    </div>
                    {saldoFinal !== 0 && (
                        <div className="text-right">
                            <p className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Saldo final</p>
                            <p className="text-3xl font-semibold tabular-nums text-rose-600">R$ {fmtBRL(saldoFinal)}</p>
                        </div>
                    )}
                </div>
            )}

            {temInvest && (
                <div className="flex flex-wrap items-end gap-x-6 gap-y-3 rounded-xl bg-slate-50 px-5 py-4">
                    <div>
                        <p className="mb-1 text-[11px] font-medium uppercase tracking-wider text-slate-400">Índice</p>
                        <div className="inline-flex rounded-lg bg-white p-0.5 ring-1 ring-slate-200">
                            {[['cdi', 'CDI'], ['poupanca', 'Poupança']].map(([k, rot]) => (
                                <button key={k} onClick={() => { setMetodo(k); setAplicado(null) }}
                                    className={`rounded-md px-3 py-1 text-xs font-semibold ${metodo === k ? 'bg-indigo-600 text-white' : 'text-slate-500 hover:text-slate-800'}`}>
                                    {rot}
                                </button>
                            ))}
                        </div>
                    </div>
                    <label className="text-xs text-slate-500">Data inicial<br /><input value={dataInicio} onChange={resetar(setDataInicio)} className={`${inputCls} w-28`} /></label>
                    <label className="text-xs text-slate-500">Data final<br /><input value={dataFim} onChange={resetar(setDataFim)} className={`${inputCls} w-28`} /></label>
                    {metodo === 'cdi' ? (
                        <>
                            <label className="text-xs text-slate-500">CDI anual (%)<br /><input type="number" step="0.01" value={cdiAnual} onChange={resetar(setCdiAnual)} className={`${inputCls} w-20`} /></label>
                            <label className="text-xs text-slate-500">% do CDI<br /><input type="number" value={percentualCDI} onChange={resetar(setPercentualCDI)} className={`${inputCls} w-20`} /></label>
                        </>
                    ) : (
                        <>
                            <label className="text-xs text-slate-500">Selic (%)<br /><input type="number" step="0.01" value={selic} onChange={resetar(setSelic)} className={`${inputCls} w-20`} /></label>
                            <label className="text-xs text-slate-500">TR (%)<br /><input type="number" step="0.0001" value={tr} onChange={resetar(setTr)} className={`${inputCls} w-20`} /></label>
                        </>
                    )}
                    <label className="text-xs text-slate-500">Fator manual<br /><input type="number" step="0.0001" placeholder="ex.: 1.10" value={fatorManual} onChange={resetar(setFatorManual)} className={`${inputCls} w-24`} /></label>
                    <button onClick={calcular} className="ml-auto rounded-lg bg-indigo-600 px-5 py-2 text-sm font-semibold text-white hover:bg-indigo-700">
                        Calcular correção
                    </button>
                    {(aviso || aplicado) && (
                        <p className={`w-full text-xs font-medium ${aviso ? 'text-amber-700' : 'text-emerald-700'}`}>
                            {aviso || `✓ Correção por ${aplicado.metodo === 'cdi' ? 'CDI' : 'poupança'} aplicada${aplicado.fator ? ` (fator ${aplicado.fator.toFixed(4)})` : ''}.`}
                        </p>
                    )}
                </div>
            )}

            <div className="grid gap-10 md:grid-cols-2">
                {[
                    { titulo: 'Saldos de aplicação', itens: saldos.map((v, i) => ({ desc: `Pág. ${paginas[i]}`, val: v })), soma: somaSaldos, cor: 'text-indigo-700' },
                    { titulo: 'Rendimentos', itens: rendimentos.map((r) => ({ desc: `${r.desc} · pág. ${r.p}`, val: r.val })), soma: somaRend, cor: 'text-rose-700' },
                ].map((bloco) => (
                    <div key={bloco.titulo}>
                        <p className="text-[11px] font-medium uppercase tracking-wider text-slate-400">{bloco.titulo}</p>
                        <div className="mt-2 flex items-baseline justify-between">
                            <p className={`text-3xl font-semibold tabular-nums ${bloco.cor}`}>R$ {fmtBRL(bloco.soma)}</p>
                            <p className={`text-sm tabular-nums ${aplicado ? 'font-semibold text-emerald-600' : 'text-slate-400'}`}>
                                {aplicado ? `corrigido: R$ ${fmtBRL(bloco.itens.reduce((a, x) => a + corrigir(x.val), 0))}` : 'aguardando cálculo'}
                            </p>
                        </div>
                        <div className="mt-3 max-h-36 overflow-y-auto divide-y divide-slate-100 text-xs">
                            {bloco.itens.length === 0 && <p className="py-3 text-slate-400">Nenhum valor identificado.</p>}
                            {bloco.itens.map((x, i) => (
                                <div key={i} className="flex justify-between py-1.5">
                                    <span className="truncate pr-4 text-slate-500">{x.desc}</span>
                                    <span className="font-mono tabular-nums text-slate-700">{fmtBRL(x.val)}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                ))}
            </div>

            {temInvest && (
                <Secao titulo="Extrato de investimento" subtitulo={`${paginas.length} meses consolidados · clique em um valor para corrigir`}
                    aberta={abertas.inv} onAlternar={() => setAbertas((a) => ({ ...a, inv: !a.inv }))}>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-slate-200 text-left text-[11px] uppercase tracking-wider text-slate-400">
                                    <th className="py-2 pr-4 font-medium">Pág.</th>
                                    <th className="py-2 px-3 text-right font-medium">Saldo anterior</th>
                                    <th className="py-2 px-3 text-right font-medium">Aplicações</th>
                                    <th className="py-2 px-3 text-right font-medium">Resgates</th>
                                    <th className="py-2 px-3 text-right font-medium">Rendimento</th>
                                    <th className="py-2 px-3 text-right font-medium">Impostos</th>
                                    <th className="py-2 pl-3 text-right font-medium">Saldo atual</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {paginas.map((p) => {
                                    const c = resumos[p].campos
                                    const cel = (campo, valor = c[campo]) => {
                                        const chave = `resumo_${p}_${campo}`
                                        return (
                                            <CelulaEditavel value={valor} editado={gravadas.has(chave) || !!pendentes[chave]}
                                                onEdit={(v) => registrar(chave, `Pág. ${p} · ${campo}`, Number(p), campo, c[campo], v)} />
                                        )
                                    }
                                    return (
                                        <tr key={p} className="hover:bg-slate-50/70">
                                            <td className="py-2 pr-4 font-medium text-slate-600">{p}</td>
                                            <td className="py-2 px-3 text-right text-slate-600">{cel('saldo_anterior')}</td>
                                            <td className="py-2 px-3 text-right text-emerald-700">{cel('aplicacoes')}</td>
                                            <td className="py-2 px-3 text-right text-rose-700">{cel('resgates')}</td>
                                            <td className="py-2 px-3 text-right text-indigo-700">{cel('rendimento_liquido')}</td>
                                            <td className="py-2 px-3 text-right text-slate-500">{cel('imposto_renda', (c.imposto_renda || 0) + (c.iof || 0))}</td>
                                            <td className="py-2 pl-3 text-right font-semibold text-slate-900">{cel('saldo_atual')}</td>
                                        </tr>
                                    )
                                })}
                            </tbody>
                        </table>
                    </div>
                </Secao>
            )}

            {temCC && (
                <Secao titulo="Conta corrente" subtitulo={`${movs.length} lançamentos identificados`}
                    aberta={abertas.cc} onAlternar={() => setAbertas((a) => ({ ...a, cc: !a.cc }))}>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-slate-200 text-left text-[11px] uppercase tracking-wider text-slate-400">
                                    <th className="py-2 pr-4 font-medium">Histórico</th>
                                    <th className="py-2 px-3 font-medium">Documento</th>
                                    <th className="py-2 px-3 text-right font-medium">Valor</th>
                                    <th className="py-2 pl-3 text-right font-medium">Saldo</th>
                                </tr>
                            </thead>
                            <tbody>
                                {Object.entries(gruposCC).map(([data, itens]) => (
                                    <React.Fragment key={data}>
                                        <tr><td colSpan={4} className="pt-4 pb-1 text-[11px] font-semibold uppercase tracking-wider text-indigo-600">{data}</td></tr>
                                        {itens.map((m, i) => (
                                            <tr key={`${data}-${i}`} className="border-b border-slate-100 hover:bg-slate-50/70">
                                                <td className="py-2 pr-4">
                                                    <span className="text-slate-800">{m.historico}</span>
                                                    <span className="ml-2 text-[11px] text-slate-400">pág. {m.pagina}</span>
                                                </td>
                                                <td className="py-2 px-3 font-mono text-xs text-slate-500">{m.documento || '—'}</td>
                                                <td className={`py-2 px-3 text-right font-mono tabular-nums ${m.valor_tipo === 'D' ? 'text-rose-600' : 'text-emerald-600'}`}>
                                                    {m.valor_tipo === 'D' ? '−' : ''}{fmtBRL(m.valor)}
                                                </td>
                                                <td className="py-2 pl-3 text-right font-mono tabular-nums text-slate-700">
                                                    {fmtBRL(m.saldo)} <span className="text-[10px] text-slate-400">{m.saldo_tipo}</span>
                                                </td>
                                            </tr>
                                        ))}
                                    </React.Fragment>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </Secao>
            )}

            <div className="flex flex-wrap items-center justify-end gap-3 border-t border-slate-200 pt-6">
                <p className="mr-auto text-xs text-slate-400">Os arquivos exportados trazem as memórias de cálculo.</p>
                <button onClick={() => exportar('pdf')} className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50">
                    <Download className="h-4 w-4 text-rose-500" /> Parecer (PDF)
                </button>
                <button onClick={() => exportar('excel')} className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700">
                    <FileSpreadsheet className="h-4 w-4" /> Dados (Excel)
                </button>
            </div>
        </div>
    )
}
