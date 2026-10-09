const rawUrl = import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:5053'
// No Render o endereço do backend chega só como host (sem https://)
export const BACKEND_URL = (/^https?:\/\//.test(rawUrl) ? rawUrl : `https://${rawUrl}`).replace(/\/+$/, '')

const CHAVE_TOKEN = 'convenio2_token'
export const obterToken = () => localStorage.getItem(CHAVE_TOKEN)
export const salvarToken = (t) => (t ? localStorage.setItem(CHAVE_TOKEN, t) : localStorage.removeItem(CHAVE_TOKEN))
export const EVENTO_SAIR = 'convenio2:sair'

export const wsUrl = () => `${BACKEND_URL.replace(/^http/, 'ws')}/ws/progress${obterToken() ? `?token=${encodeURIComponent(obterToken())}` : ''}`

// fetch com o token de login; um 401 encerra a sessão e volta para a tela de login
export async function fetchAuth(url, opts = {}) {
    const t = obterToken()
    const headers = { ...(opts.headers || {}), ...(t ? { Authorization: `Bearer ${t}` } : {}) }
    const r = await fetch(url, { ...opts, headers })
    if (r.status === 401) {
        salvarToken(null)
        window.dispatchEvent(new Event(EVENTO_SAIR))
    }
    return r
}

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
    const r = await fetchAuth(`${BACKEND_URL}${path}`, opts)
    const data = await r.json().catch(() => null)
    if (!r.ok) throw new Error(data?.detail || `Erro ${r.status}`)
    return data
}

export async function baixar(path, nomePadrao) {
    const r = await fetchAuth(`${BACKEND_URL}${path}`)
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
