import React, { useState, useEffect, useCallback } from 'react'
import { Button } from "./components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./components/ui/card"
import { Upload, FileText, CheckCircle2, AlertCircle, Loader2, Pencil, Save, X, Download, FileSpreadsheet, Database, Zap } from "lucide-react"

// ─────────────────────────────────────────────────────────────────────────────
// Helper: formata numero como BRL
// ─────────────────────────────────────────────────────────────────────────────
const fmtBRL = (v) =>
    v === null || v === undefined ? '—' :
        Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const calcularPoupanca = (valorInicial, dataInicioStr, dataFimStr, selic, tr) => {
    try {
        if (!dataInicioStr || !dataFimStr) return { valorCorrigido: valorInicial, taxaUsada: 0, qtdDias: 0, qtdMeses: 0 };
        const parseDate = (s) => {
            if (!s) return new Date(NaN);
            const parts = s.split('/');
            if (parts.length !== 3) return new Date(NaN);
            return new Date(parts[2], parts[1] - 1, parts[0]);
        };
        const d1 = parseDate(dataInicioStr);
        const d2 = dataFimStr === 'HOJE' ? new Date() : parseDate(dataFimStr);

        if (isNaN(d1) || isNaN(d2)) return { valorCorrigido: valorInicial, taxaUsada: 0, qtdDias: 0, qtdMeses: 0 };

        const diffTime = d2 - d1;
        const qtdDias = Math.floor(diffTime / (1000 * 60 * 60 * 24));

        if (qtdDias > 30) {
            return { valorCorrigido: valorInicial, taxaUsada: 0, qtdDias, qtdMeses: qtdDias / 30 };
        }

        let taxaMensal = 0;
        const sVal = parseFloat(selic) || 0;
        const tVal = parseFloat(tr) || 0;

        if (sVal > 8.5) {
            taxaMensal = 0.005 + (tVal / 100);
        } else {
            taxaMensal = ((sVal * 0.7 / 100) / 12) + (tVal / 100);
        }

        const qtdMeses = qtdDias / 30;
        const valorFinal = valorInicial * Math.pow((1 + taxaMensal), qtdMeses);

        return {
            valorCorrigido: parseFloat(valorFinal.toFixed(2)),
            taxaUsada: taxaMensal * 100,
            qtdDias,
            qtdMeses
        };
    } catch (e) {
        console.error("Erro no cálculo da poupança:", e);
        return { valorCorrigido: valorInicial, taxaUsada: 0, qtdDias: 0, qtdMeses: 0 };
    }
};

const getDiasUteis = (startDate, endDate) => {
    let count = 0;
    let curDate = new Date(startDate.getTime());
    while (curDate < endDate) {
        curDate.setDate(curDate.getDate() + 1);
        const dayOfWeek = curDate.getDay();
        if (dayOfWeek !== 0 && dayOfWeek !== 6) count++;
    }
    return count;
};

const calcularCDI = (valorInicial, dataInicioStr, dataFimStr, cdiAnual, percentualCDI) => {
    try {
        if (!dataInicioStr || !dataFimStr) return { valorCorrigido: valorInicial, taxaUsada: 0, qtdDias: 0 };
        const parseDate = (s) => {
            if (!s) return new Date(NaN);
            const parts = s.split('/');
            if (parts.length !== 3) return new Date(NaN);
            return new Date(parts[2], parts[1] - 1, parts[0]);
        };
        const d1 = parseDate(dataInicioStr);
        const d2 = dataFimStr === 'HOJE' ? new Date() : parseDate(dataFimStr);

        if (isNaN(d1) || isNaN(d2) || d1 >= d2) return { valorCorrigido: valorInicial, taxaUsada: 0, qtdDias: 0 };

        const diasUteis = getDiasUteis(d1, d2);

        const cdiRate = parseFloat(cdiAnual) || 0;
        const perc = parseFloat(percentualCDI) || 100;

        // taxaDiaria = (1 + (cdiAnual / 100))^(1/252) - 1
        const taxaDiaria = Math.pow(1 + (cdiRate / 100), 1 / 252) - 1;

        // taxaAplicada = taxaDiaria * (percentualCDI / 100)
        const taxaAplicada = taxaDiaria * (perc / 100);

        // valorFinal = valorInicial * (1 + taxaAplicada) ^ diasUteis
        const valorFinal = valorInicial * Math.pow(1 + taxaAplicada, diasUteis);

        return {
            valorCorrigido: parseFloat(valorFinal.toFixed(2)),
            taxaUsada: taxaAplicada * 100, // em percentual
            qtdDias: diasUteis
        };
    } catch (e) {
        console.error("Erro no cálculo do CDI:", e);
        return { valorCorrigido: valorInicial, taxaUsada: 0, qtdDias: 0 };
    }
};

// ─────────────────────────────────────────────────────────────────────────────
// EditableCell — célula que vira <input> ao clicar
// ─────────────────────────────────────────────────────────────────────────────
function EditableCell({ value, onEdit, isEdited, isNumeric, className = '' }) {
    const [editing, setEditing] = useState(false)
    const [draft, setDraft] = useState(String(value ?? ''))

    const commit = () => {
        setEditing(false)
        const parsed = isNumeric ? parseFloat(draft.replace(',', '.')) : draft
        if (!isNaN(parsed) || !isNumeric) {
            onEdit(isNumeric ? parsed : draft)
        }
    }

    if (editing) {
        return (
            <input
                autoFocus
                value={draft}
                onChange={e => setDraft(e.target.value)}
                onBlur={commit}
                onKeyDown={e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') setEditing(false) }}
                className="w-full border border-blue-400 rounded px-1 py-0.5 text-sm outline-none bg-blue-50"
            />
        )
    }

    return (
        <span
            onClick={() => { setDraft(String(value ?? '')); setEditing(true) }}
            title="Clique para editar"
            className={`cursor-pointer group relative inline-flex items-center gap-1 rounded px-1 transition-colors hover:bg-blue-50 ${isEdited ? 'bg-yellow-50 text-yellow-800 font-medium' : ''} ${className}`}
        >
            {isNumeric ? fmtBRL(value) : (value || '—')}
            {isEdited && <Pencil className="h-3 w-3 text-yellow-500 shrink-0" />}
            {!isEdited && <Pencil className="h-3 w-3 text-slate-300 opacity-0 group-hover:opacity-100 shrink-0 transition-opacity" />}
        </span>
    )
}

// ─────────────────────────────────────────────────────────────────────────────
// ConfirmModal — modal mostrando antes/depois antes de salvar
// ─────────────────────────────────────────────────────────────────────────────
function ConfirmModal({ pendingEdits, onConfirm, onCancel, saving }) {
    return (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <Card className="w-full max-w-lg shadow-2xl border-slate-200 animate-in">
                <CardHeader className="border-b border-slate-100 pb-4">
                    <CardTitle className="text-slate-800 flex items-center gap-2">
                        <Save className="h-5 w-5 text-blue-600" />
                        Confirmar Alterações
                    </CardTitle>
                    <CardDescription>
                        Revise as correções antes de salvar no banco de dados.
                    </CardDescription>
                </CardHeader>
                <CardContent className="pt-4 space-y-3 max-h-80 overflow-y-auto">
                    {pendingEdits.map((edit, i) => (
                        <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-slate-50 border border-slate-100">
                            <div className="flex-1 min-w-0">
                                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">
                                    {edit.label}
                                </p>
                                <div className="flex items-center gap-2 text-sm">
                                    <span className="text-rose-600 line-through">{edit.oldDisplay}</span>
                                    <span className="text-slate-400">→</span>
                                    <span className="text-emerald-700 font-bold">{edit.newDisplay}</span>
                                </div>
                            </div>
                        </div>
                    ))}
                </CardContent>
                <div className="flex justify-end gap-3 px-6 py-4 border-t border-slate-100">
                    <Button variant="outline" onClick={onCancel} disabled={saving} className="text-slate-600">
                        <X className="h-4 w-4 mr-1" /> Cancelar
                    </Button>
                    <Button onClick={onConfirm} disabled={saving} className="bg-blue-600 hover:bg-blue-700 text-white">
                        {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
                        {saving ? 'Salvando...' : 'Confirmar e Salvar'}
                    </Button>
                </div>
            </Card>
        </div>
    )
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN APP
// ─────────────────────────────────────────────────────────────────────────────
function App() {
    const [file, setFile] = useState(null)
    const [loading, setLoading] = useState(false)
    const [results, setResults] = useState(null)
    const [error, setError] = useState(null)
    const [historicoAberto, setHistoricoAberto] = useState(false)
    const [historico, setHistorico] = useState([])
    const [estatisticas, setEstatisticas] = useState(null)
    const [progressMessage, setProgressMessage] = useState('')
    const [progressPercent, setProgressPercent] = useState(0)
    const [ws, setWs] = useState(null)
    const [metodoCalculo, setMetodoCalculo] = useState('cdi')
    const [dataInicio, setDataInicio] = useState('01/01/2023')
    const [dataFim, setDataFim] = useState('HOJE')
    const [fatorCalculo, setFatorCalculo] = useState(1.0)
    const [fatorManual, setFatorManual] = useState('')
    const [selicAnual, setSelicAnual] = useState(10.75)
    const [taxaTR, setTaxaTR] = useState(0)
    const [cdiAnual, setCdiAnual] = useState(10.65)
    const [percentualCDI, setPercentualCDI] = useState(100)
    const [fatorAplicado, setFatorAplicado] = useState(null) // only set when user clicks Calcular
    const [isCalculating, setIsCalculating] = useState(false)
    const [periodoAviso, setPeriodoAviso] = useState(null) // null | 'poupanca_acima_30'
    const [showCCDetails, setShowCCDetails] = useState(true) // Toggle for "Extrato Detalhado"
    const [showInvestmentDetails, setShowInvestmentDetails] = useState(true) // Toggle for "Extrato de Investimento"

    // ── Edit state ──────────────────────────────────────────────────────────
    // pendingEdits: { key: { label, campo, tipo, id, pagina, oldValue, newValue, arquivo } }
    const [pendingEdits, setPendingEdits] = useState({})
    const [showModal, setShowModal] = useState(false)
    const [saving, setSaving] = useState(false)
    // savedKeys: set of edit keys that were confirmed and saved (for yellow highlight)
    const [savedKeys, setSavedKeys] = useState(new Set())

    const hasPending = Object.keys(pendingEdits).length > 0

    const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:5053'
    const WS_URL = import.meta.env.VITE_BACKEND_URL
        ? `${import.meta.env.VITE_BACKEND_URL.replace(/^http/, 'ws')}/ws/progress`
        : 'ws://127.0.0.1:5053/ws/progress'

    // WebSocket
    useEffect(() => {
        const websocket = new WebSocket(WS_URL)
        websocket.onopen = () => console.log('✅ WebSocket conectado')
        websocket.onmessage = (event) => {
            const data = JSON.parse(event.data)
            setProgressMessage(data.message)
            setProgressPercent(data.progress)
        }
        websocket.onerror = (err) => console.error('❌ Erro no WebSocket:', err)
        websocket.onclose = () => console.log('🔌 WebSocket desconectado')
        setWs(websocket)
        return () => { if (websocket.readyState === WebSocket.OPEN) websocket.close() }
    }, [])

    useEffect(() => { carregarEstatisticas() }, [])

    const carregarEstatisticas = async () => {
        try {
            const r = await fetch(`${BACKEND_URL}/estatisticas`)
            setEstatisticas(await r.json())
        } catch (e) { console.error(e) }
    }

    const carregarHistorico = async () => {
        try {
            const r = await fetch(`${BACKEND_URL}/historico?limite=100`)
            const d = await r.json()
            setHistorico(d.registros || [])
            setHistoricoAberto(true)
        } catch (e) { console.error(e) }
    }

    const limparBanco = async () => {
        if (!confirm('⚠️ CUIDADO: Isso vai remover TODOS os dados do banco!\n\nDeseja continuar?')) return
        try {
            const r = await fetch(`${BACKEND_URL}/limpar-banco`, { method: 'DELETE' })
            const d = await r.json()
            alert(`✅ Banco limpo!\n\n${d.removidos.extracoes} extrações removidas`)
            setHistoricoAberto(false)
            setResults(null)
            setPendingEdits({})
            setSavedKeys(new Set())
            carregarEstatisticas()
        } catch (e) { alert('❌ Erro ao limpar banco: ' + e.message) }
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // Handler: Cálculo manual (disparado pelo botão "Calcular")
    // ─────────────────────────────────────────────────────────────────────────────
    const handleCalculate = async () => {
        setPeriodoAviso(null);
        if (fatorManual) {
            setFatorAplicado({ fator: parseFloat(fatorManual), method: metodoCalculo, manual: true });
            return;
        }
        if (metodoCalculo === 'poupanca') {
            // Check period length to warn user
            const parseDate = (s) => {
                if (!s) return new Date(NaN);
                if (s === 'HOJE') return new Date();
                const p = s.split('/');
                return p.length === 3 ? new Date(p[2], p[1] - 1, p[0]) : new Date(NaN);
            };
            const d1 = parseDate(dataInicio);
            const d2 = parseDate(dataFim);
            if (!isNaN(d1) && !isNaN(d2)) {
                const dias = Math.floor((d2 - d1) / (1000 * 60 * 60 * 24));
                if (dias > 30) {
                    setPeriodoAviso(`Período de ${dias} dias excede 30 dias — poupança não aplica correção por regra definida.`);
                    setFatorAplicado({ fator: null, method: 'poupanca', manual: false });
                    return;
                }
            }
            setFatorAplicado({ fator: null, method: 'poupanca', manual: false });
            return;
        }
        if (metodoCalculo === 'cdi') {
            setFatorAplicado({ fator: null, method: 'cdi', manual: false });
            return;
        }
    };

    // ─────────────────────────────────────────────────────────────────────────────
    // Handlers: Exportação
    // ─────────────────────────────────────────────────────────────────────────────
    const handleExport = async (type) => {
        const payload = {
            ...results,
            metodoCalculo,
            dataInicio,
            fatorCalculo: fatorManual ? parseFloat(fatorManual) : fatorCalculo
        };

        try {
            const res = await fetch(`${BACKEND_URL}/export/${type}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `Auditoria_${new Date().getTime()}.${type === 'pdf' ? 'pdf' : 'xlsx'}`;
            document.body.appendChild(a);
            a.click();
            a.remove();
        } catch (err) {
            console.error("Erro ao exportar:", err);
            alert("Erro ao gerar arquivo para exportação.");
        }
    };

    const handleUpload = async () => {
        if (!file) return alert('Selecione um arquivo primeiro!')
        setLoading(true)
        setResults(null)
        setError(null)
        setPendingEdits({})
        setSavedKeys(new Set())
        setProgressMessage('Preparando arquivo...')
        setProgressPercent(0)
        const formData = new FormData()
        formData.append('file', file)
        try {
            const r = await fetch(`${BACKEND_URL}/extract`, { method: 'POST', body: formData })
            if (!r.ok) { const e = await r.json().catch(() => ({ detail: 'Erro desconhecido' })); throw new Error(e.detail) }
            const data = await r.json()
            setResults(data)
            carregarEstatisticas()
        } catch (e) {
            setError(e.message)
            setProgressMessage(`❌ Erro: ${e.message}`)
        } finally {
            setLoading(false)
        }
    }

    // ── Edit handlers ────────────────────────────────────────────────────────
    const registerEdit = useCallback(({ key, label, campo, tipo, id, pagina, oldValue, newValue, arquivo }) => {
        // If they revert to the original, clear the pending edit
        if (String(newValue) === String(oldValue)) {
            setPendingEdits(prev => { const n = { ...prev }; delete n[key]; return n })
        } else {
            setPendingEdits(prev => ({ ...prev, [key]: { label, campo, tipo, id, pagina, oldValue, newValue, arquivo } }))
        }
    }, [])

    const handleConfirmSave = async () => {
        setSaving(true)
        const entries = Object.entries(pendingEdits)
        try {
            // Cria uma cópia profunda dos resultados para atualizar localmente
            const updatedResults = { ...results }
            if (updatedResults.resumos_mensais) {
                updatedResults.resumos_mensais = { ...updatedResults.resumos_mensais }
            }
            if (updatedResults.movimentacoes_cc) {
                updatedResults.movimentacoes_cc = [...updatedResults.movimentacoes_cc]
            }

            for (const [key, edit] of entries) {
                if (edit.tipo === 'cc') {
                    await fetch(`${BACKEND_URL}/movimentacao-cc/${edit.id}`, {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ campo: edit.campo, valor: edit.newValue }),
                    })
                    // Atualiza localmente
                    const idx = updatedResults.movimentacoes_cc.findIndex(m => m.id === edit.id)
                    if (idx !== -1) {
                        updatedResults.movimentacoes_cc[idx] = {
                            ...updatedResults.movimentacoes_cc[idx],
                            [edit.campo]: edit.newValue,
                            editado_manualmente: 1
                        }
                    }
                } else if (edit.tipo === 'resumo') {
                    await fetch(`${BACKEND_URL}/resumo-mensal/${encodeURIComponent(edit.arquivo)}/${edit.pagina}`, {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ campo: edit.campo, valor: edit.newValue }),
                    })
                    // Atualiza localmente
                    if (updatedResults.resumos_mensais[edit.pagina]) {
                        updatedResults.resumos_mensais[edit.pagina] = {
                            ...updatedResults.resumos_mensais[edit.pagina],
                            campos: {
                                ...updatedResults.resumos_mensais[edit.pagina].campos,
                                [edit.campo]: edit.newValue
                            }
                        }
                    }
                }
            }

            // Atualiza o estado global com os novos valores
            setResults(updatedResults)
            // Mark all as saved
            setSavedKeys(prev => new Set([...prev, ...Object.keys(pendingEdits)]))
            setPendingEdits({})
            setShowModal(false)
        } catch (e) {
            alert('Erro ao salvar: ' + e.message)
        } finally {
            setSaving(false)
        }
    }

    const handleCancelModal = () => {
        setPendingEdits({})
        setShowModal(false)
    }

    // ── Diagnosis helper ─────────────────────────────────────────────────────
    const hasCC = results?.movimentacoes_cc?.length > 0
    const hasInvestment = results?.resumos_mensais && Object.keys(results.resumos_mensais).length > 0
    const hasResults = hasCC || hasInvestment

    const getDiagnosis = () => {
        if (!results) return null

        // 1. Tenta pegar o último saldo dos resumos mensais (investimento)
        if (hasInvestment) {
            const pages = Object.keys(results.resumos_mensais).sort((a, b) => Number(a) - Number(b))
            const lastPage = pages[pages.length - 1]
            const saldo = results.resumos_mensais[lastPage]?.campos?.saldo_atual
            if (saldo !== undefined && saldo !== null) return saldo
        }

        // 2. Se não houver investimento, tenta pegar o último saldo da conta corrente
        if (hasCC) {
            const lastMov = results.movimentacoes_cc[results.movimentacoes_cc.length - 1]
            if (lastMov?.saldo !== undefined && lastMov?.saldo !== null) return lastMov.saldo
        }

        return null
    }

    const saldoFinal = getDiagnosis()

    // Build list for modal
    const modalEdits = Object.entries(pendingEdits).map(([key, e]) => ({
        label: e.label,
        oldDisplay: typeof e.oldValue === 'number' ? `R$ ${fmtBRL(e.oldValue)}` : e.oldValue,
        newDisplay: typeof e.newValue === 'number' ? `R$ ${fmtBRL(e.newValue)}` : e.newValue,
    }))

    const arquivoAtual = file?.name?.replace(/[^\w.-]/g, '_') || ''

    return (
        <div className="min-h-screen bg-background px-6 py-8 font-sans">
            {/* CONFIRMATION MODAL */}
            {showModal && (
                <ConfirmModal
                    pendingEdits={modalEdits}
                    onConfirm={handleConfirmSave}
                    onCancel={handleCancelModal}
                    saving={saving}
                />
            )}

            <div className="max-w-6xl mx-auto space-y-6">

                {/* ── HEADER ── */}
                <header className="flex flex-col md:flex-row items-start md:items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-6">
                    <div>
                        <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100 border-l-4 border-blue-600 pl-3">
                            Painel de Auditoria
                        </h1>
                        <p className="text-slate-500 text-sm mt-1 pl-4">Módulo de Fiscalização e Encerramento de Convênios</p>
                    </div>
                    <div className="flex gap-3 mt-4 md:mt-0">
                        <Button onClick={carregarHistorico} variant="outline" size="sm" className="text-slate-600 border-slate-300 hover:bg-slate-50 shadow-sm">
                            <FileText className="h-4 w-4 mr-2" /> Histórico
                        </Button>
                        <Button onClick={limparBanco} variant="destructive" size="sm" className="shadow-sm">
                            <AlertCircle className="h-4 w-4 mr-2" /> Limpar Banco
                        </Button>
                    </div>
                </header>

                {/* ── GUIA DE USO DO SISTEMA ── */}
                <details className="group bg-white border border-blue-100 rounded-xl shadow-sm overflow-hidden">
                    <summary className="cursor-pointer px-6 py-4 flex items-center justify-between hover:bg-blue-50/50 transition-colors select-none">
                        <div className="flex items-center gap-3">
                            <div className="p-2 bg-blue-100 rounded-lg">
                                <AlertCircle className="h-5 w-5 text-blue-600" />
                            </div>
                            <div>
                                <h2 className="text-sm font-bold text-slate-800">Como Usar o Sistema — Guia Completo</h2>
                                <p className="text-[11px] text-slate-500">Clique para expandir as instruções detalhadas de uso</p>
                            </div>
                        </div>
                        <span className="text-blue-500 text-xs font-bold uppercase tracking-wider group-open:hidden">▼ Abrir</span>
                        <span className="text-blue-500 text-xs font-bold uppercase tracking-wider hidden group-open:inline">▲ Fechar</span>
                    </summary>

                    <div className="px-6 pb-6 pt-2 border-t border-blue-100 space-y-5 text-sm text-slate-700 leading-relaxed">

                        {/* PASSO 1 */}
                        <div className="flex gap-4">
                            <div className="shrink-0 w-8 h-8 rounded-full bg-blue-600 text-white flex items-center justify-center font-black text-sm">1</div>
                            <div>
                                <h3 className="font-bold text-slate-800 mb-1">Preencha os Dados do Convênio</h3>
                                <p className="text-slate-600 text-xs">
                                    No painel à esquerda (<strong>"Dados do Convênio"</strong>), informe o <strong>Número do Convênio</strong>, o <strong>Órgão Concessor</strong>,
                                    o <strong>Convenente</strong> e as <strong>datas de vigência</strong>. Estes dados serão utilizados no parecer de cobrança exportado ao final.
                                </p>
                            </div>
                        </div>

                        {/* PASSO 2 */}
                        <div className="flex gap-4">
                            <div className="shrink-0 w-8 h-8 rounded-full bg-blue-600 text-white flex items-center justify-center font-black text-sm">2</div>
                            <div>
                                <h3 className="font-bold text-slate-800 mb-1">Importe o Extrato Bancário</h3>
                                <p className="text-slate-600 text-xs">
                                    Clique ou arraste o arquivo <strong>PDF</strong> (ou imagem) do extrato bancário na área de upload à direita.
                                    Após selecionar, clique em <strong>"Iniciar Auditoria"</strong>. O sistema executará:
                                </p>
                                <ul className="list-disc list-inside text-xs text-slate-500 mt-1 space-y-0.5 ml-2">
                                    <li><strong>OCR (Google Vision)</strong> — converte cada página em texto digital</li>
                                    <li><strong>Parser Inteligente (Groq IA)</strong> — localiza e extrai os campos financeiros automaticamente</li>
                                    <li><strong>Gravação Incremental</strong> — cada página é salva no banco imediatamente, evitando perda de dados</li>
                                </ul>
                                <p className="text-slate-500 text-[11px] mt-1 italic">
                                    ⏱ Tempo estimado: ~1-2 min para cada 50 páginas. Acompanhe o progresso pela barra azul em tempo real.
                                </p>
                            </div>
                        </div>

                        {/* PASSO 3 */}
                        <div className="flex gap-4">
                            <div className="shrink-0 w-8 h-8 rounded-full bg-blue-600 text-white flex items-center justify-center font-black text-sm">3</div>
                            <div>
                                <h3 className="font-bold text-slate-800 mb-1">Analise os Resultados</h3>
                                <p className="text-slate-600 text-xs">
                                    Após o processamento, o sistema exibirá automaticamente:
                                </p>
                                <ul className="list-disc list-inside text-xs text-slate-500 mt-1 space-y-0.5 ml-2">
                                    <li><strong>Diagnóstico</strong> — card verde (conta zerada) ou vermelho (saldo remanescente detectado)</li>
                                    <li><strong>Cards de Totais</strong> — somatório dos saldos (azul = base, vermelho = atualizado)</li>
                                    <li><strong>Extrato Detalhado (Conta Corrente)</strong> — todas as movimentações agrupadas por data</li>
                                    <li><strong>Extrato de Investimento (Resumos Mensais)</strong> — tabela com os 8 campos por mês</li>
                                </ul>
                                <p className="text-slate-500 text-[11px] mt-1 italic">
                                    💡 Use os botões "Recolher/Expandir" no cabeçalho de cada tabela para organizar a visualização.
                                </p>
                            </div>
                        </div>

                        {/* PASSO 4 */}
                        <div className="flex gap-4">
                            <div className="shrink-0 w-8 h-8 rounded-full bg-emerald-600 text-white flex items-center justify-center font-black text-sm">4</div>
                            <div>
                                <h3 className="font-bold text-slate-800 mb-1">Edite Valores (se necessário)</h3>
                                <p className="text-slate-600 text-xs">
                                    <strong>Clique em qualquer célula</strong> da tabela de Resumos Mensais para editar o valor manualmente.
                                    As células editadas ficam destacadas em amarelo. Um botão flutuante <strong>"Salvar Alterações"</strong> aparecerá
                                    no topo para confirmar suas correções. Um modal de confirmação mostrará o antes/depois antes de gravar.
                                </p>
                            </div>
                        </div>

                        {/* PASSO 5 */}
                        <div className="flex gap-4">
                            <div className="shrink-0 w-8 h-8 rounded-full bg-emerald-600 text-white flex items-center justify-center font-black text-sm">5</div>
                            <div>
                                <h3 className="font-bold text-slate-800 mb-1">Aplique a Correção Monetária</h3>
                                <p className="text-slate-600 text-xs">
                                    No painel <strong>"Índice de Correção"</strong> (acima dos cards de totais), escolha o método:
                                </p>
                                <ul className="list-disc list-inside text-xs text-slate-500 mt-1 space-y-0.5 ml-2">
                                    <li><strong>CDI</strong> — informe o CDI Anual (%) e o % do CDI. O cálculo é diário (252 dias úteis/ano), por juros compostos</li>
                                    <li><strong>Poupança</strong> — informe a Taxa Selic e TR. Regra: não aplica correção para períodos &gt; 30 dias</li>
                                    <li><strong>Fator Manual</strong> — digite diretamente um multiplicador (ex: 1.10 para 10% de acréscimo)</li>
                                </ul>
                                <p className="text-slate-600 text-xs mt-1.5">
                                    Após configurar, clique em <strong>"Calcular"</strong>. O card vermelho será atualizado com o valor corrigido.
                                    Um badge verde confirmará que o cálculo foi aplicado.
                                </p>
                            </div>
                        </div>

                        {/* PASSO 6 */}
                        <div className="flex gap-4">
                            <div className="shrink-0 w-8 h-8 rounded-full bg-violet-600 text-white flex items-center justify-center font-black text-sm">6</div>
                            <div>
                                <h3 className="font-bold text-slate-800 mb-1">Exporte o Parecer Final</h3>
                                <p className="text-slate-600 text-xs">
                                    No rodapé da página, exporte os resultados:
                                </p>
                                <ul className="list-disc list-inside text-xs text-slate-500 mt-1 space-y-0.5 ml-2">
                                    <li><strong>Exportar Parecer (PDF)</strong> — gera o documento formal de cobrança com todas as memórias de cálculo</li>
                                    <li><strong>Exportar Dados (Excel)</strong> — planilha com todos os dados extraídos para conferência ou arquivo</li>
                                </ul>
                            </div>
                        </div>

                        {/* DICAS */}
                        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mt-2">
                            <h3 className="font-bold text-amber-800 text-xs uppercase tracking-wider mb-2">⚡ Dicas Importantes</h3>
                            <ul className="list-disc list-inside text-xs text-amber-700 space-y-1 ml-1">
                                <li><strong>Histórico:</strong> Use o botão "Histórico" no topo para consultar todas as extrações já realizadas</li>
                                <li><strong>Limpar Banco:</strong> Remove todos os dados salvos. Use com cuidado — ação irreversível</li>
                                <li><strong>Múltiplos Arquivos:</strong> Você pode processar vários extratos. Cada novo upload substitui os dados do arquivo anterior no banco</li>
                                <li><strong>Documentos Suportados:</strong> PDF (múltiplas páginas), PNG, JPG. O sistema aguenta centenas de páginas sem travar</li>
                            </ul>
                        </div>
                    </div>
                </details>

                {/* ── KPI BAR ── */}
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                    {[
                        { label: "Registros no Banco", value: estatisticas?.total_registros ?? "—", color: "text-blue-600", sub: "Resumos + CC" },
                        { label: "Arquivos no Sistema", value: estatisticas?.total_arquivos ?? "—", color: "text-emerald-600", sub: "PDFs processados" },
                        { label: "Extrações Mensais", value: estatisticas?.resumos ?? "—", color: "text-violet-600", sub: "Identificadas" },
                    ].map(({ label, value, color, sub }) => (
                        <div key={label} className="bg-white dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-xl px-5 py-4 shadow-sm card-hover">
                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">{label}</p>
                            <p className={`text-2xl font-bold ${color}`}>{value}</p>
                            <p className="text-[10px] text-slate-500 mt-1">{sub}</p>
                        </div>
                    ))}
                </div>

                {/* ── DEBUG PANEL (Temporary) ── */}
                {results && !hasResults && !loading && (
                    <div className="p-4 bg-slate-900 text-slate-50 rounded-xl mt-6 font-mono text-[10px] overflow-auto max-h-60 border-2 border-amber-500 shadow-xl">
                        <p className="text-amber-400 font-bold mb-2 flex items-center gap-2">
                            <Database className="h-4 w-4" /> DEBUG: Resposta Bruta do Servidor
                        </p>
                        <pre>{JSON.stringify(results, null, 2)}</pre>
                    </div>
                )}

                {/* ── HISTÓRICO MODAL ── */}
                {historicoAberto && (
                    <Card className="border-slate-200 shadow-sm">
                        <CardHeader className="border-b border-slate-100 pb-3">
                            <div className="flex justify-between items-center">
                                <CardTitle className="text-slate-800">Histórico do Banco de Dados</CardTitle>
                                <Button onClick={() => setHistoricoAberto(false)} variant="ghost" size="sm">✕</Button>
                            </div>
                            <CardDescription>Últimas {historico.length} extrações gravadas</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="max-h-72 overflow-y-auto space-y-2 mt-3">
                                {historico.map((reg) => (
                                    <div key={reg.id} className="p-3 border border-slate-100 rounded-lg hover:bg-slate-50 transition-colors">
                                        <div className="flex justify-between items-start">
                                            <div>
                                                <div className="font-semibold text-sm text-slate-800">{reg.campo}</div>
                                                <div className="text-xs text-slate-400">{reg.arquivo_nome} • Página {reg.pagina}</div>
                                            </div>
                                            <div className="text-right">
                                                <div className="font-bold text-blue-600 text-sm">R$ {fmtBRL(reg.valor)}</div>
                                                <div className="text-xs text-slate-400">{reg.data_extracao}</div>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </CardContent>
                    </Card>
                )}

                {/* ── UPLOAD AREA ── */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    {/* Config Panel */}
                    <div className="md:col-span-1">
                        <Card className="border-slate-200 shadow-sm h-full">
                            <CardHeader className="pb-3 border-b border-slate-100">
                                <CardTitle className="text-sm font-bold text-slate-700 uppercase tracking-wider">Dados do Convênio</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4 pt-4">
                                <div className="space-y-1">
                                    <label className="text-xs font-semibold text-slate-500">Banco de Origem</label>
                                    <select className="w-full text-sm p-2 rounded border border-slate-200 bg-slate-50 text-slate-700 outline-none focus:border-blue-500">
                                        <option>Detecção Automática</option>
                                        <option>Banco do Brasil</option>
                                        <option>Caixa Econômica Federal</option>
                                    </select>
                                </div>
                                <div className="space-y-1">
                                    <label className="text-xs font-semibold text-slate-500">Nº do Convênio / Ano</label>
                                    <input type="text" placeholder="Ex: 812345/2021" className="w-full text-sm p-2 rounded border border-slate-200 bg-white placeholder:text-slate-300 text-slate-700 outline-none focus:border-blue-500" />
                                </div>
                                <div className="space-y-1">
                                    <label className="text-xs font-semibold text-slate-500">Fim da Vigência</label>
                                    <input type="date" className="w-full text-sm p-2 rounded border border-slate-200 bg-white text-slate-700 outline-none focus:border-blue-500" />
                                </div>
                                <div className="pt-2 text-xs text-slate-400 border-t border-slate-100 flex items-start gap-1">
                                    <AlertCircle className="w-3 h-3 shrink-0 mt-0.5" />
                                    <span>Dados usados no Parecer de Cobrança final.</span>
                                </div>
                            </CardContent>
                        </Card>
                    </div>

                    {/* Upload dropzone */}
                    <div className="md:col-span-2">
                        <Card className="border-slate-200 shadow-sm h-full flex flex-col">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-lg text-slate-800">Importar Extrato Bancário</CardTitle>
                                <CardDescription>Faça o upload do documento em PDF ou Imagem para iniciar a auditoria robótica.</CardDescription>
                            </CardHeader>
                            <CardContent className="flex-1 flex flex-col justify-center">
                                <div className="flex flex-col items-center justify-center border-2 border-dashed border-slate-300 rounded-xl p-8 transition-all hover:border-blue-500 hover:bg-blue-50/50 group bg-slate-50">
                                    <input type="file" id="file-upload" className="hidden"
                                        onChange={e => { setFile(e.target.files[0]); setError(null) }}
                                        accept=".pdf,.png,.jpg,.jpeg"
                                    />
                                    <label htmlFor="file-upload" className="flex flex-col items-center cursor-pointer space-y-4 w-full">
                                        <div className="p-4 bg-white rounded-full shadow-sm border border-slate-100 group-hover:scale-110 transition-transform">
                                            <Upload className="h-8 w-8 text-blue-600" />
                                        </div>
                                        <div className="text-center">
                                            <span className="font-semibold text-slate-700 block text-lg group-hover:text-blue-600 transition-colors">
                                                {file ? 'Arquivo Selecionado' : 'Clique ou arraste o arquivo aqui'}
                                            </span>
                                            <p className="text-sm text-slate-500 mt-1">
                                                {file ? <span className="text-blue-600 font-medium">{file.name}</span> : 'PDF (múltiplas páginas) ou Imagem'}
                                            </p>
                                        </div>
                                    </label>
                                    {file && (
                                        <Button onClick={e => { e.preventDefault(); handleUpload() }} disabled={loading}
                                            className="mt-6 w-full max-w-xs bg-blue-600 hover:bg-blue-700 text-white shadow-md" type="button" size="lg">
                                            {loading ? <Loader2 className="mr-2 h-5 w-5 animate-spin" /> : <FileText className="mr-2 h-5 w-5" />}
                                            {loading ? 'Auditando Documento...' : 'Iniciar Auditoria'}
                                        </Button>
                                    )}
                                </div>

                                {loading && progressMessage && (
                                    <div className="mt-5 space-y-2 p-4 bg-slate-50 rounded-lg border border-slate-100">
                                        <div className="flex items-center justify-between text-sm">
                                            <span className="text-blue-700 font-medium flex items-center">
                                                <Loader2 className="w-3 h-3 animate-spin mr-2" />{progressMessage}
                                            </span>
                                            <span className="font-bold text-slate-700">{progressPercent}%</span>
                                        </div>
                                        <div className="w-full h-2 bg-slate-200 rounded-full overflow-hidden">
                                            <div className="h-full bg-blue-500 transition-all duration-300" style={{ width: `${progressPercent}%` }} />
                                        </div>
                                        <p className="text-xs text-slate-500 text-center">
                                            {progressPercent < 50 && "Aplicando OCR (Google Vision)..."}
                                            {progressPercent >= 50 && progressPercent < 95 && "Localizando matrizes matemáticas do extrato..."}
                                            {progressPercent >= 95 && progressPercent < 100 && "Registrando auditoria no banco de dados..."}
                                            {progressPercent === 100 && "✓ Auditoria concluída."}
                                        </p>
                                    </div>
                                )}

                                {error && (
                                    <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-600 text-sm">
                                        <AlertCircle className="inline-block mr-2 h-4 w-4" />
                                        <strong>Erro na Leitura:</strong> {error}
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </div>
                </div>

                {/* ── NO RESULTS WARNING ── */}
                {results && !hasResults && (
                    <Card className="border-amber-500/50 bg-amber-50">
                        <CardHeader>
                            <CardTitle className="text-amber-700">⚠️ Nenhum dado encontrado</CardTitle>
                            <CardDescription>O OCR foi executado, mas não foram encontradas seções reconhecíveis no documento.</CardDescription>
                        </CardHeader>
                    </Card>
                )}

                {/* ── DEBUG PANEL (Temporary) ── */}
                {results && !hasResults && !loading && (
                    <div className="p-4 bg-slate-900 text-slate-50 rounded-xl mb-6 font-mono text-[10px] overflow-auto max-h-60 border-2 border-amber-500 shadow-xl">
                        <p className="text-amber-400 font-bold mb-2 flex items-center gap-2">
                            <Database className="h-4 w-4" /> DEBUG: Resposta Bruta do Servidor
                        </p>
                        <pre>{JSON.stringify(results, null, 2)}</pre>
                    </div>
                )}

                {/* ════════════════════════════════════════════════════════════
                    RESULTS SECTION
                ════════════════════════════════════════════════════════════ */}
                {hasResults && (
                    <div className="space-y-6 animate-in">
                        {/* ── FLOATING SAVE BUTTON ── */}
                        {hasPending && (
                            <div className="sticky top-4 z-40 flex justify-center pointer-events-none">
                                <div className="pointer-events-auto">
                                    <Button onClick={() => setShowModal(true)}
                                        className="bg-amber-500 hover:bg-amber-600 text-white shadow-lg px-6 py-3 rounded-full font-semibold flex items-center gap-2 animate-bounce-subtle">
                                        <Save className="h-5 w-5" />
                                        Salvar {Object.keys(pendingEdits).length} Alteração(ões)
                                    </Button>
                                </div>
                            </div>
                        )}

                        {/* ── DIAGNOSIS PANEL (Unified) ── */}
                        {hasResults && saldoFinal !== null && (
                            saldoFinal === 0 ? (
                                <Card className="border-emerald-500/50 bg-emerald-500/10 shadow-sm">
                                    <div className="flex items-center p-6 gap-4">
                                        <div className="p-3 bg-emerald-500/20 rounded-full">
                                            <CheckCircle2 className="h-8 w-8 text-emerald-600" />
                                        </div>
                                        <div>
                                            <h3 className="text-xl font-bold text-emerald-800">Resultado da Auditoria: Conta Totalmente Zerada</h3>
                                            <p className="text-emerald-700/80 text-sm mt-1">A movimentação financeira deste convênio encerrou sem saldo remanescente em {hasInvestment ? 'Investimentos' : 'Conta Corrente'}.</p>
                                        </div>
                                    </div>
                                </Card>
                            ) : (
                                <Card className="border-rose-500/50 bg-rose-500/5 shadow-md">
                                    <div className="flex items-start p-6 gap-4">
                                        <div className="p-3 bg-rose-500/20 rounded-full shrink-0">
                                            <AlertCircle className="h-8 w-8 text-rose-600" />
                                        </div>
                                        <div className="w-full">
                                            <div className="flex justify-between items-start">
                                                <div>
                                                    <h3 className="text-xl font-bold text-rose-800">Alerta de Auditoria: Saldo Remanescente Detectado</h3>
                                                    <p className="text-rose-700/80 text-sm mt-1">O documento apresenta um saldo final em aberto. Recomenda-se a aplicação de glosa/correção monetária.</p>
                                                </div>
                                                <div className="text-right">
                                                    <p className="text-xs font-semibold text-rose-700/70 uppercase tracking-wider">Saldo Final Identificado</p>
                                                    <p className="text-3xl font-black text-rose-600 mt-1">R$ {fmtBRL(saldoFinal)}</p>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </Card>
                            )
                        )}

                        {/* ── PERIODO AVISO (Large Banner) ── */}
                        {periodoAviso && (
                            <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-center gap-3 animate-in slide-in-from-left duration-300 shadow-sm">
                                <AlertCircle className="h-6 w-6 text-amber-600 shrink-0" />
                                <div className="text-sm font-bold text-amber-800">
                                    {periodoAviso}
                                </div>
                            </div>
                        )}

                        {/* ── FILTROS DE CÁLCULO (acima dos cards) ── */}
                        {hasInvestment && (
                            <div className="bg-white border border-blue-100 rounded-xl shadow-sm p-4 mb-2">
                                <div className="flex flex-wrap items-center gap-3">
                                    <span className="text-xs font-black text-slate-500 uppercase tracking-widest">Índice de Correção:</span>
                                    <div className="flex bg-slate-100 p-1 rounded-lg">
                                        <button
                                            onClick={() => { setMetodoCalculo('poupanca'); setFatorManual(''); setFatorAplicado(null); }}
                                            className={`px-4 py-1.5 text-xs font-semibold rounded-md transition-all ${metodoCalculo === 'poupanca' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
                                        >Poupança</button>
                                        <button
                                            onClick={() => { setMetodoCalculo('cdi'); setFatorAplicado(null); }}
                                            className={`px-4 py-1.5 text-xs font-semibold rounded-md transition-all ${metodoCalculo === 'cdi' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
                                        >CDI</button>
                                    </div>

                                    <div className="h-8 w-px bg-slate-200" />

                                    <div className="flex items-center gap-2">
                                        <label className="text-[10px] font-black text-rose-600 uppercase">Fator Manual:</label>
                                        <input
                                            type="number" placeholder="Ex: 1.10" step="0.0001"
                                            value={fatorManual}
                                            onChange={e => { setFatorManual(e.target.value); setFatorAplicado(null); }}
                                            className="bg-white border border-rose-200 rounded px-2 py-1 text-xs font-mono outline-none focus:ring-2 focus:ring-rose-500 w-24 text-rose-700"
                                        />
                                    </div>

                                    <div className="h-8 w-px bg-slate-200" />

                                    <div className="flex items-center gap-2">
                                        <label className="text-xs font-bold text-slate-600">Data Inicial:</label>
                                        <input type="text" placeholder="DD/MM/YYYY"
                                            value={dataInicio} onChange={e => { setDataInicio(e.target.value); setFatorAplicado(null); }}
                                            className="bg-white border border-slate-200 rounded px-2 py-1 text-xs font-mono outline-none focus:ring-2 focus:ring-blue-500 w-28"
                                        />
                                    </div>

                                    <div className="flex items-center gap-2">
                                        <label className="text-xs font-bold text-slate-600">Data Final:</label>
                                        <input type="text" placeholder="DD/MM/YYYY ou HOJE"
                                            value={dataFim} onChange={e => { setDataFim(e.target.value); setFatorAplicado(null); }}
                                            className="bg-white border border-slate-200 rounded px-2 py-1 text-xs font-mono outline-none focus:ring-2 focus:ring-blue-500 w-32"
                                        />
                                    </div>

                                    {metodoCalculo === 'poupanca' && (
                                        <div className="flex items-center gap-3 border-l border-slate-200 pl-3">
                                            <div className="flex items-center gap-1">
                                                <label className="text-[10px] font-black text-rose-600 uppercase">Selic (%):</label>
                                                <input type="number" step="0.01" value={selicAnual}
                                                    onChange={e => { setSelicAnual(e.target.value); setFatorAplicado(null); }}
                                                    className="bg-white border border-rose-200 rounded px-2 py-1 text-xs font-mono outline-none focus:ring-2 focus:ring-rose-500 w-20 text-rose-700 font-bold"
                                                />
                                            </div>
                                            <div className="flex items-center gap-1">
                                                <label className="text-[10px] font-black text-rose-600 uppercase">TR (%):</label>
                                                <input type="number" step="0.0001" value={taxaTR}
                                                    onChange={e => { setTaxaTR(e.target.value); setFatorAplicado(null); }}
                                                    className="bg-white border border-rose-200 rounded px-2 py-1 text-xs font-mono outline-none focus:ring-2 focus:ring-rose-500 w-20 text-rose-700 font-bold"
                                                />
                                            </div>
                                        </div>
                                    )}

                                    {metodoCalculo === 'cdi' && (
                                        <div className="flex items-center gap-3 border-l border-slate-200 pl-3">
                                            <div className="flex items-center gap-1">
                                                <label className="text-[10px] font-black text-blue-600 uppercase">CDI Anual (%):</label>
                                                <input type="number" step="0.01" value={cdiAnual}
                                                    onChange={e => { setCdiAnual(e.target.value); setFatorAplicado(null); }}
                                                    className="bg-white border border-blue-200 rounded px-2 py-1 text-xs font-mono outline-none focus:ring-2 focus:ring-blue-500 w-20 text-blue-700 font-bold"
                                                />
                                            </div>
                                            <div className="flex items-center gap-1">
                                                <label className="text-[10px] font-black text-blue-600 uppercase">% CDI:</label>
                                                <input type="number" step="1" value={percentualCDI}
                                                    onChange={e => { setPercentualCDI(e.target.value); setFatorAplicado(null); }}
                                                    className="bg-white border border-blue-200 rounded px-2 py-1 text-xs font-mono outline-none focus:ring-2 focus:ring-blue-500 w-20 text-blue-700 font-bold"
                                                />
                                            </div>
                                        </div>
                                    )}

                                    <button
                                        onClick={handleCalculate}
                                        disabled={isCalculating}
                                        className="ml-auto flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-xs font-bold px-5 py-2 rounded-lg shadow transition-all"
                                    >
                                        {isCalculating ? <><span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin inline-block" /> Calculando...</> : '▶ Calcular'}
                                    </button>

                                    {fatorAplicado && !periodoAviso && (
                                        <span className="text-[10px] font-bold text-emerald-600 bg-emerald-50 border border-emerald-200 px-2 py-1 rounded-full">
                                            ✓ {fatorAplicado.method.toUpperCase()} aplicado {fatorAplicado.fator ? `[${fatorAplicado.fator.toFixed(4)}x]` : ''}
                                        </span>
                                    )}
                                    {periodoAviso && (
                                        <span className="text-[10px] font-bold text-amber-700 bg-amber-50 border border-amber-300 px-2 py-1 rounded-full">
                                            ⚠ {periodoAviso}
                                        </span>
                                    )}
                                </div>
                            </div>
                        )}

                        {/* ── CONSOLIDATED SUMMARY CARDS (NEW) ── */}
                        {hasResults && (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                                {/* CARD 1: Saldo Atual (Investimentos) */}
                                <Card className="border-blue-200 bg-blue-50/30 overflow-hidden shadow-md">
                                    <div className="bg-blue-600 px-4 py-2 text-white text-[10px] font-bold uppercase tracking-widest flex items-center gap-2">
                                        <div className="w-1.5 h-1.5 bg-blue-300 rounded-full animate-pulse"></div>
                                        Totalizador de Saldo — Investimentos
                                    </div>
                                    <CardContent className="p-6">
                                        <div className="space-y-4">
                                            {(() => {
                                                const saldos = results?.resumos_mensais
                                                    ? Object.values(results.resumos_mensais).map(p => p.campos?.saldo_atual || 0)
                                                    : [];
                                                const totalBase = saldos.reduce((a, b) => a + b, 0);
                                                const totalAtualizado = fatorAplicado ? saldos.reduce((acc, val) => {
                                                    if (fatorAplicado.method === 'poupanca' && !fatorAplicado.fator) {
                                                        return acc + calcularPoupanca(val, dataInicio, dataFim, selicAnual, taxaTR).valorCorrigido;
                                                    }
                                                    if (fatorAplicado.method === 'cdi' && !fatorAplicado.fator) {
                                                        return acc + calcularCDI(val, dataInicio, dataFim, cdiAnual, percentualCDI).valorCorrigido;
                                                    }
                                                    return acc + (val * (fatorAplicado.fator || 1));
                                                }, 0) : totalBase;

                                                return (
                                                    <>
                                                        <div className="max-h-32 overflow-y-auto pr-2 space-y-1 custom-scrollbar">
                                                            {saldos.map((val, i) => (
                                                                <div key={i} className="flex justify-between text-[11px] text-slate-500 font-mono border-b border-blue-100/50 pb-1">
                                                                    <span>Saldo Ref. #{i + 1}</span>
                                                                    <span className="font-bold text-slate-700">{fmtBRL(val)}</span>
                                                                </div>
                                                            ))}
                                                        </div>
                                                        <div className="pt-4 border-t border-blue-200">
                                                            <div className="flex justify-between items-end">
                                                                <div>
                                                                    <p className="text-[10px] text-blue-600 font-black uppercase">Soma Base</p>
                                                                    <p className="text-lg font-mono font-bold text-blue-900">{fmtBRL(totalBase)}</p>
                                                                </div>
                                                                <div className="text-right">
                                                                    <p className="text-[10px] font-black uppercase inline-flex items-center gap-1 text-slate-400">
                                                                        {fatorAplicado ? <span className="text-emerald-600">Atualizado ({fatorAplicado.method.toUpperCase()})</span> : <span className="italic">— aguardando cálculo</span>}
                                                                    </p>
                                                                    <p className={`text-2xl font-mono font-black animate-in fade-in ${fatorAplicado ? 'text-emerald-600' : 'text-slate-400'}`}>
                                                                        {fmtBRL(totalAtualizado)}
                                                                    </p>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </>
                                                );
                                            })()}
                                        </div>
                                    </CardContent>
                                </Card>

                                {/* CARD 2: Totalizador de Rendimentos */}
                                <Card className="border-rose-200 bg-rose-50/30 overflow-hidden shadow-md">
                                    <div className="bg-rose-600 px-4 py-2 text-white text-[10px] font-bold uppercase tracking-widest flex items-center gap-2">
                                        <div className="w-1.5 h-1.5 bg-rose-300 rounded-full animate-pulse"></div>
                                        Totalizador de Rendimentos (Impostos)
                                    </div>
                                    <CardContent className="p-6">
                                        <div className="space-y-4">
                                            {(() => {
                                                // Coleta apenas Rendimentos (Bruto ou Líquido conforme disponibilidade)
                                                const itemsInv = results?.resumos_mensais
                                                    ? Object.values(results.resumos_mensais).map(p => ({
                                                        desc: 'Rendimento (Invest)',
                                                        val: p.campos?.rendimento_bruto || p.campos?.rendimento_liquido || 0,
                                                        p: p.pagina
                                                    })).filter(x => x.val > 0)
                                                    : [];

                                                const itemsCC = results?.movimentacoes_cc
                                                    ? results.movimentacoes_cc
                                                        .filter(m => /(rendimento|juros|aplic)/i.test(m.historico))
                                                        .map(m => ({
                                                            desc: m.historico,
                                                            val: Math.abs(m.valor),
                                                            p: m.pagina
                                                        }))
                                                    : [];

                                                const allItems = [...itemsInv, ...itemsCC];
                                                const totalBase = allItems.reduce((a, b) => a + b.val, 0);

                                                const totalAtualizado = fatorAplicado ? allItems.reduce((acc, item) => {
                                                    if (fatorAplicado.method === 'poupanca' && !fatorAplicado.fator) {
                                                        return acc + calcularPoupanca(item.val, dataInicio, dataFim, selicAnual, taxaTR).valorCorrigido;
                                                    }
                                                    if (fatorAplicado.method === 'cdi' && !fatorAplicado.fator) {
                                                        return acc + calcularCDI(item.val, dataInicio, dataFim, cdiAnual, percentualCDI).valorCorrigido;
                                                    }
                                                    return acc + (item.val * (fatorAplicado.fator || 1));
                                                }, 0) : totalBase;

                                                return (
                                                    <>
                                                        <div className="max-h-32 overflow-y-auto pr-2 space-y-1 custom-scrollbar">
                                                            {allItems.length > 0 ? allItems.map((item, i) => (
                                                                <div key={i} className="flex justify-between text-[11px] text-slate-500 font-mono border-b border-rose-100/50 pb-1">
                                                                    <span className="truncate max-w-[150px]">{item.desc} (Pág {item.p})</span>
                                                                    <span className="font-bold text-rose-700">{fmtBRL(item.val)}</span>
                                                                </div>
                                                            )) : <div className="text-center text-slate-400 text-xs py-4">Nenhum rendimento identificado</div>}
                                                        </div>
                                                        <div className="pt-4 border-t border-rose-200">
                                                            <div className="flex justify-between items-end">
                                                                <div>
                                                                    <p className="text-[10px] text-rose-600 font-black uppercase">Soma Rendimentos</p>
                                                                    <p className="text-xl font-mono font-bold text-rose-900">{fmtBRL(totalBase)}</p>
                                                                </div>
                                                                <div className="text-right">
                                                                    <p className="text-[10px] font-black uppercase flex items-center justify-end gap-1">
                                                                        {isCalculating && <Loader2 className="w-3 h-3 animate-spin" />}
                                                                        {fatorAplicado ? <span className="text-rose-500">Atualizado ({fatorAplicado.method.toUpperCase()})</span> : <span className="text-slate-400 italic">— aguardando cálculo</span>}
                                                                    </p>
                                                                    <p className={`text-2xl font-mono font-black animate-in fade-in ${fatorAplicado ? 'text-rose-600' : 'text-slate-400'}`}>
                                                                        {fmtBRL(totalAtualizado)}
                                                                    </p>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </>
                                                );
                                            })()}
                                        </div>
                                    </CardContent>
                                </Card>
                            </div>
                        )}

                        {/* ── CARD 0: MOVIMENTAÇÕES EM CONTA CORRENTE (PREMIUM) ── */}
                        {results?.movimentacoes_cc && results.movimentacoes_cc.length > 0 && (() => {
                            // Agrupar por data
                            const groups = results.movimentacoes_cc.reduce((acc, mov) => {
                                const dt = mov.data_movimento || mov.data_balancete || 'Sem Data';
                                if (!acc[dt]) acc[dt] = [];
                                acc[dt].push(mov);
                                return acc;
                            }, {});

                            return (
                                <Card className="border-slate-200 shadow-xl overflow-hidden mb-8 bg-white/50 backdrop-blur-sm">
                                    <div className="bg-gradient-to-r from-blue-700 to-indigo-800 p-4 text-white">
                                        <div className="flex justify-between items-center">
                                            <div className="flex items-center gap-3">
                                                <div className="p-2 bg-white/20 rounded-lg backdrop-blur-md">
                                                    <FileText className="h-5 w-5 text-white" />
                                                </div>
                                                <div>
                                                    <h3 className="text-lg font-bold tracking-tight">Extrato Detalhado — Conta Corrente</h3>
                                                    <p className="text-blue-100 text-[10px] uppercase tracking-widest font-semibold opacity-80">
                                                        {results.movimentacoes_cc.length} Lançamentos Identificados
                                                    </p>
                                                </div>
                                            </div>
                                            <Button
                                                onClick={() => setShowCCDetails(!showCCDetails)}
                                                variant="ghost"
                                                size="sm"
                                                className="text-white hover:bg-white/20 hover:text-white transition-colors border border-white/30"
                                            >
                                                {showCCDetails ? 'Recolher Visualização' : 'Expandir Tabela'}
                                            </Button>
                                        </div>
                                    </div>

                                    {showCCDetails && (
                                        <div className="p-0 animate-in fade-in slide-in-from-top-4 duration-300">
                                            <div className="overflow-x-auto">
                                                <table className="w-full text-sm text-left border-collapse">
                                                    <thead className="bg-slate-50/80 border-b border-slate-200">
                                                        <tr>
                                                            <th className="px-6 py-4 font-bold text-slate-500 uppercase text-[10px] tracking-widest text-center w-24">Data</th>
                                                            <th className="px-6 py-4 font-bold text-slate-500 uppercase text-[10px] tracking-widest">Histórico / Descrição</th>
                                                            <th className="px-4 py-4 font-bold text-slate-500 uppercase text-[10px] tracking-widest">Documento</th>
                                                            <th className="px-6 py-4 font-bold text-slate-500 text-right uppercase text-[10px] tracking-widest w-32">Valor (R$)</th>
                                                            <th className="px-6 py-4 font-bold text-slate-500 text-right uppercase text-[10px] tracking-widest w-32">Saldo (R$)</th>
                                                        </tr>
                                                    </thead>
                                                    <tbody className="bg-white">
                                                        {Object.entries(groups).map(([date, movs], gIdx) => (
                                                            <React.Fragment key={date}>
                                                                {/* Date Header Row */}
                                                                <tr className="bg-slate-50/30">
                                                                    <td colSpan="5" className="px-6 py-2 border-y border-slate-100">
                                                                        <div className="flex items-center gap-2">
                                                                            <div className="h-px flex-1 bg-slate-200"></div>
                                                                            <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest bg-slate-100 px-2 py-0.5 rounded-full border border-slate-200">
                                                                                {date}
                                                                            </span>
                                                                            <div className="h-px flex-1 bg-slate-200"></div>
                                                                        </div>
                                                                    </td>
                                                                </tr>
                                                                {movs.map((mov, mIdx) => (
                                                                    <tr key={`${gIdx}-${mIdx}`} className="group hover:bg-blue-50/40 transition-all border-b border-slate-50 last:border-b-0">
                                                                        <td className="px-6 py-4 text-center">
                                                                            <span className="text-[10px] font-mono font-bold text-slate-400 group-hover:text-blue-500 transition-colors">
                                                                                {date.split('/')[0]}/{date.split('/')[1]}
                                                                            </span>
                                                                        </td>
                                                                        <td className="px-6 py-4">
                                                                            <div className="flex flex-col">
                                                                                <span className="text-slate-800 font-semibold text-xs leading-relaxed group-hover:translate-x-1 transition-transform inline-block">
                                                                                    {mov.historico}
                                                                                </span>
                                                                                <div className="flex items-center gap-2 mt-1">
                                                                                    <span className="text-[9px] font-bold text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">
                                                                                        PÁG. {mov.pagina}
                                                                                    </span>
                                                                                </div>
                                                                            </div>
                                                                        </td>
                                                                        <td className="px-4 py-4">
                                                                            {mov.documento ? (
                                                                                <span className="text-[10px] font-mono text-slate-500 bg-slate-50 px-2 py-1 rounded border border-slate-100">
                                                                                    #{mov.documento}
                                                                                </span>
                                                                            ) : (
                                                                                <span className="text-slate-300 text-[10px]">—</span>
                                                                            )}
                                                                        </td>
                                                                        <td className={`px-6 py-4 text-right font-mono font-bold text-sm ${mov.valor_tipo === 'D' ? 'text-rose-600' : 'text-emerald-600'}`}>
                                                                            <div className="flex items-center justify-end gap-1">
                                                                                <span>{mov.valor_tipo === 'D' ? '-' : ''}{fmtBRL(mov.valor)}</span>
                                                                                <span className="text-[9px] opacity-60 font-black">{mov.valor_tipo}</span>
                                                                            </div>
                                                                        </td>
                                                                        <td className="px-6 py-4 text-right">
                                                                            <div className="font-mono font-black text-slate-700 text-sm">
                                                                                {fmtBRL(mov.saldo)}
                                                                            </div>
                                                                            <div className={`text-[9px] font-black uppercase ${mov.saldo_tipo === 'D' ? 'text-rose-500' : 'text-slate-400'}`}>
                                                                                SALDO {mov.saldo_tipo}
                                                                            </div>
                                                                        </td>
                                                                    </tr>
                                                                ))}
                                                            </React.Fragment>
                                                        ))}
                                                    </tbody>
                                                </table>
                                            </div>
                                        </div>
                                    )}
                                </Card>
                            );
                        })()}

                        {/* old filter removed — now above cards */}
                        {hasInvestment && (
                            <Card className="border-slate-200 shadow-sm overflow-hidden mb-6">
                                <CardHeader className="bg-blue-50/60 border-b border-blue-100 pb-4">
                                    <div className="flex justify-between items-center">
                                        <div>
                                            <CardTitle className="text-slate-800 flex items-center gap-2">
                                                <span className="w-2 h-5 bg-blue-500 rounded inline-block" />
                                                Extrato de Investimento — Resumos Mensais
                                            </CardTitle>
                                            <CardDescription className="mt-1">
                                                {Object.keys(results.resumos_mensais).length} meses consolidados.
                                                <span className="ml-2 text-blue-600 font-medium">Clique em qualquer célula para editar.</span>
                                            </CardDescription>
                                        </div>
                                        <Button
                                            onClick={() => setShowInvestmentDetails(!showInvestmentDetails)}
                                            variant="outline"
                                            size="sm"
                                            className="text-slate-600 hover:bg-blue-50 transition-colors border border-slate-300"
                                        >
                                            {showInvestmentDetails ? 'Recolher Visualização' : 'Expandir Tabela'}
                                        </Button>
                                    </div>
                                </CardHeader>
                                {showInvestmentDetails && (
                                    <div className="overflow-x-auto animate-in fade-in slide-in-from-top-4 duration-300">
                                        <table className="w-full text-sm text-left">
                                            <thead className="text-xs font-semibold text-slate-500 uppercase bg-slate-50 border-b border-slate-200">
                                                <tr>
                                                    <th className="px-4 py-3">Pág.</th>
                                                    <th className="px-4 py-3 text-right">Saldo Ant.</th>
                                                    <th className="px-4 py-3 text-right text-emerald-600">Entradas (+)</th>
                                                    <th className="px-4 py-3 text-right text-rose-600">Saídas (-)</th>
                                                    <th className="px-4 py-3 text-right text-blue-600">Rendimento</th>
                                                    <th className="px-4 py-3 text-right">Impostos</th>
                                                    <th className="px-4 py-3 text-right bg-slate-100">Saldo Atual</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-slate-100">
                                                {Object.keys(results.resumos_mensais)
                                                    .sort((a, b) => Number(a) - Number(b))
                                                    .map((pageNum) => {
                                                        const c = results.resumos_mensais[pageNum].campos
                                                        const keyPrefix = `resumo_${pageNum}`
                                                        const isEdited = (campo) => savedKeys.has(`${keyPrefix}_${campo}`)
                                                        const hasPend = (campo) => pendingEdits[`${keyPrefix}_${campo}`] !== undefined
                                                        const mkEdit = (campo, oldValue) => v => registerEdit({
                                                            key: `${keyPrefix}_${campo}`, label: `Pág.${pageNum} | ${campo}`,
                                                            campo, tipo: 'resumo', pagina: Number(pageNum),
                                                            oldValue, newValue: v, arquivo: arquivoAtual
                                                        })
                                                        return (
                                                            <tr key={pageNum} className="hover:bg-slate-50/80 transition-colors">
                                                                <td className="px-4 py-3 font-semibold text-slate-700">Pág. {pageNum}</td>
                                                                <td className="px-4 py-3 text-right text-slate-600">
                                                                    <EditableCell value={c.saldo_anterior} isNumeric isEdited={isEdited('saldo_anterior') || hasPend('saldo_anterior')} onEdit={mkEdit('saldo_anterior', c.saldo_anterior)} />
                                                                </td>
                                                                <td className="px-4 py-3 text-right text-emerald-600 font-medium">
                                                                    <EditableCell value={c.aplicacoes} isNumeric isEdited={isEdited('aplicacoes') || hasPend('aplicacoes')} onEdit={mkEdit('aplicacoes', c.aplicacoes)} />
                                                                </td>
                                                                <td className="px-4 py-3 text-right text-rose-600 font-medium">
                                                                    <EditableCell value={c.resgates} isNumeric isEdited={isEdited('resgates') || hasPend('resgates')} onEdit={mkEdit('resgates', c.resgates)} />
                                                                </td>
                                                                <td className="px-4 py-3 text-right text-blue-600">
                                                                    <EditableCell value={c.rendimento_liquido} isNumeric isEdited={isEdited('rendimento_liquido') || hasPend('rendimento_liquido')} onEdit={mkEdit('rendimento_liquido', c.rendimento_liquido)} />
                                                                </td>
                                                                <td className="px-4 py-3 text-right text-slate-500">
                                                                    <EditableCell value={(c.imposto_renda || 0) + (c.iof || 0)} isNumeric isEdited={isEdited('imposto_renda') || hasPend('imposto_renda')} onEdit={mkEdit('imposto_renda', c.imposto_renda)} />
                                                                </td>
                                                                <td className="px-4 py-3 text-right font-bold text-slate-800 bg-slate-50/50">
                                                                    <EditableCell value={c.saldo_atual} isNumeric isEdited={isEdited('saldo_atual') || hasPend('saldo_atual')} onEdit={mkEdit('saldo_atual', c.saldo_atual)} />
                                                                </td>
                                                            </tr>
                                                        )
                                                    })}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                            </Card>
                        )}
                    </div>
                )}
                {hasResults && (
                    <div className="flex flex-col md:flex-row items-center justify-end gap-4 pt-8 border-t border-slate-200 dark:border-slate-800 pb-12">
                        <p className="text-xs text-slate-400 italic mr-auto">
                            * Os arquivos exportados conterão todas as memórias de cálculo e glosas identificadas.
                        </p>
                        <Button
                            onClick={() => handleExport('pdf')}
                            variant="outline" className="bg-white border-slate-300 text-slate-700 hover:bg-slate-50 shadow-sm px-6"
                        >
                            <Download className="w-4 h-4 mr-2 text-rose-500" />
                            Exportar Parecer (PDF)
                        </Button>
                        <Button
                            onClick={() => handleExport('excel')}
                            className="bg-emerald-600 hover:bg-emerald-700 text-white shadow-md px-6"
                        >
                            <FileSpreadsheet className="w-4 h-4 mr-2" />
                            Exportar Dados (Excel)
                        </Button>
                    </div>
                )}
            </div>
        </div>
    )
}

export default App
