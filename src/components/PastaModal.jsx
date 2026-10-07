import React, { useState } from 'react'
import { FolderPlus, Loader2, X } from 'lucide-react'

export default function PastaModal({ inicial, onSalvar, onFechar }) {
    const [form, setForm] = useState({
        nome: inicial?.nome || '',
        numero_convenio: inicial?.numero_convenio || '',
        convenente: inicial?.convenente || '',
        observacao: inicial?.observacao || '',
    })
    const [salvando, setSalvando] = useState(false)
    const [erro, setErro] = useState(null)

    const enviar = async (e) => {
        e.preventDefault()
        if (!form.nome.trim()) {
            setErro('Dê um nome para a pasta.')
            return
        }
        setSalvando(true)
        setErro(null)
        try {
            await onSalvar(form)
        } catch (err) {
            setErro(err.message)
            setSalvando(false)
        }
    }

    const campo = (chave, rotulo, placeholder, extra = {}) => (
        <label className="block">
            <span className="text-xs font-medium text-slate-500">{rotulo}</span>
            <input
                value={form[chave]}
                onChange={(e) => setForm({ ...form, [chave]: e.target.value })}
                placeholder={placeholder}
                className="mt-1 w-full border-b border-slate-200 bg-transparent py-2 text-sm text-slate-900 outline-none placeholder:text-slate-300 focus:border-indigo-500"
                {...extra}
            />
        </label>
    )

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm" onMouseDown={onFechar}>
            <form onSubmit={enviar} onMouseDown={(e) => e.stopPropagation()} className="w-full max-w-md rounded-2xl bg-white p-7 shadow-2xl animate-in">
                <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
                            <FolderPlus className="h-5 w-5" />
                        </div>
                        <div>
                            <h2 className="text-lg font-semibold text-slate-900">{inicial ? 'Editar pasta' : 'Nova pasta de convênio'}</h2>
                            <p className="text-sm text-slate-500">Todos os volumes deste convênio ficam aqui.</p>
                        </div>
                    </div>
                    <button type="button" onClick={onFechar} className="rounded-lg p-1 text-slate-400 hover:bg-slate-100"><X className="h-5 w-5" /></button>
                </div>
                <div className="mt-6 space-y-5">
                    {campo('nome', 'Nome da pasta *', 'Ex.: Convênio Boa Esperança', { autoFocus: true })}
                    <div className="grid grid-cols-2 gap-5">
                        {campo('numero_convenio', 'Nº do convênio', 'Ex.: 5191000168')}
                        {campo('convenente', 'Convenente', 'Ex.: Município de ...')}
                    </div>
                    {campo('observacao', 'Observação', 'Opcional')}
                </div>
                {erro && <p className="mt-4 text-sm text-rose-600">{erro}</p>}
                <div className="mt-7 flex justify-end gap-2">
                    <button type="button" onClick={onFechar} className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100">Cancelar</button>
                    <button type="submit" disabled={salvando} className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-5 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-70">
                        {salvando && <Loader2 className="h-4 w-4 animate-spin" />}
                        {inicial ? 'Salvar' : 'Criar pasta'}
                    </button>
                </div>
            </form>
        </div>
    )
}
