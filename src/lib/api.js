const rawUrl = import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:5053'
export const BACKEND_URL = rawUrl.replace(/\/+$/, '')
export const WS_URL = BACKEND_URL.replace(/^http/, 'ws') + '/ws/progress'

// Mesmo critério do backend (re.sub(r'[^\w\.-]', '_') do Python, que preserva acentos)
export const sanitizeFilename = (name) => (name || 'documento.pdf').replace(/[^\p{L}\p{N}_.-]/gu, '_')

export const nomeLegivel = (arquivo) => (arquivo || '').replace(/\.pdf$/i, '').replace(/_+/g, ' ').replace(/\s+-\s+/g, ' – ').trim()

export async function api(path, { method = 'GET', body, form } = {}) {
    const opts = { method }
    if (form) opts.body = form
    else if (body !== undefined) {
        opts.headers = { 'Content-Type': 'application/json' }
        opts.body = JSON.stringify(body)
    }
    const r = await fetch(`${BACKEND_URL}${path}`, opts)
    const data = await r.json().catch(() => null)
    if (!r.ok) throw new Error(data?.detail || `Erro ${r.status}`)
    return data
}

export async function baixar(path, nomePadrao) {
    const r = await fetch(`${BACKEND_URL}${path}`)
    if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail || r.statusText)
    const disp = r.headers.get('Content-Disposition') || ''
    const m = disp.match(/filename\*=UTF-8''([^;]+)/)
    const a = document.createElement('a')
    a.href = URL.createObjectURL(await r.blob())
    a.download = m ? decodeURIComponent(m[1]) : nomePadrao
    a.click()
    URL.revokeObjectURL(a.href)
}

export const fmtBRL = (v) =>
    v === null || v === undefined || Number.isNaN(Number(v))
        ? '—'
        : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export const fmtMoney = (v) =>
    v === null || v === undefined || Number.isNaN(Number(v))
        ? '—'
        : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

export const fmtData = (v) => {
    if (!v) return '—'
    const d = new Date(v)
    return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
}
