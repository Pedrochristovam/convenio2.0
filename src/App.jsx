import { useState, useEffect } from 'react'
import { Button } from "./components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./components/ui/card"
import { Upload, FileText, CheckCircle2, AlertCircle, Loader2 } from "lucide-react"

function App() {
    const [file, setFile] = useState(null)
    const [loading, setLoading] = useState(false)
    const [results, setResults] = useState(null)
    const [error, setError] = useState(null)
    const [historicoAberto, setHistoricoAberto] = useState(false)
    const [historico, setHistorico] = useState([])
    const [estatisticas, setEstatisticas] = useState(null)

    // NOVO: Estados para progresso em tempo real
    const [progressMessage, setProgressMessage] = useState('')
    const [progressPercent, setProgressPercent] = useState(0)
    const [ws, setWs] = useState(null)

    const BACKEND_URL = 'http://127.0.0.1:57670'
    const WS_URL = 'ws://127.0.0.1:57670/ws/progress'

    // Conecta ao WebSocket quando o componente monta
    useEffect(() => {
        const websocket = new WebSocket(WS_URL)

        websocket.onopen = () => {
            console.log('✅ WebSocket conectado')
        }

        websocket.onmessage = (event) => {
            const data = JSON.parse(event.data)
            console.log('📨 Progresso recebido:', data)
            setProgressMessage(data.message)
            setProgressPercent(data.progress)
        }

        websocket.onerror = (error) => {
            console.error('❌ Erro no WebSocket:', error)
        }

        websocket.onclose = () => {
            console.log('🔌 WebSocket desconectado')
        }

        setWs(websocket)

        // Cleanup ao desmontar
        return () => {
            if (websocket.readyState === WebSocket.OPEN) {
                websocket.close()
            }
        }
    }, [])

    const carregarEstatisticas = async () => {
        try {
            const response = await fetch(`${BACKEND_URL}/estatisticas`)
            const data = await response.json()
            setEstatisticas(data)
        } catch (error) {
            console.error('Erro ao carregar estatísticas:', error)
        }
    }

    const carregarHistorico = async () => {
        try {
            const response = await fetch(`${BACKEND_URL}/historico?limite=100`)
            const data = await response.json()
            setHistorico(data.registros || [])
            setHistoricoAberto(true)
        } catch (error) {
            console.error('Erro ao carregar histórico:', error)
        }
    }

    const limparBanco = async () => {
        if (!confirm('⚠️ CUIDADO: Isso vai remover TODOS os dados do banco!\n\nDeseja continuar?')) {
            return
        }

        try {
            const response = await fetch(`${BACKEND_URL}/limpar-banco`, { method: 'DELETE' })
            const data = await response.json()
            alert(`✅ Banco limpo!\n\n${data.removidos.extracoes} extrações removidas\n${data.removidos.resumos} resumos removidos`)

            // Atualiza estatísticas e fecha histórico
            setHistoricoAberto(false)
            carregarEstatisticas()
        } catch (error) {
            console.error('Erro ao limpar banco:', error)
            alert('❌ Erro ao limpar banco: ' + error.message)
        }
    }

    const handleUpload = async () => {
        if (!file) {
            alert('Por favor, selecione um arquivo primeiro!')
            return
        }

        console.log('🚀 Iniciando upload do arquivo:', file.name)
        setLoading(true)
        setResults(null)
        setError(null)
        setProgressMessage('Preparando arquivo...')
        setProgressPercent(0)

        const formData = new FormData()
        formData.append('file', file)

        try {
            console.log('📡 Enviando requisição para o backend...')
            const response = await fetch(`${BACKEND_URL}/extract`, {
                method: 'POST',
                body: formData,
            })

            console.log('📥 Resposta recebida:', response.status, response.statusText)

            if (!response.ok) {
                const errJson = await response.json().catch(() => ({ detail: 'Erro desconhecido' }));
                throw new Error(errJson.detail || `Erro HTTP ${response.status}`);
            }

            const data = await response.json()
            console.log('✅ Dados extraídos com sucesso:', data)
            setResults(data)

            // Atualiza estatísticas após extração
            carregarEstatisticas()
        } catch (error) {
            console.error('❌ Erro no processamento:', error)
            setError(error.message)
            setProgressMessage(`❌ Erro: ${error.message}`)
            alert(`Erro: ${error.message}`)
        } finally {
            setLoading(false)
            console.log('🏁 Processamento finalizado')
        }
    }


    return (
        <div className="min-h-screen bg-background p-8 font-sans">
            <div className="max-w-4xl mx-auto space-y-8">
                <header className="text-center space-y-4">
                    <h1 className="text-5xl font-extrabold tracking-tight gradient-text py-2">
                        Convênio 2.0
                    </h1>
                    <p className="text-muted-foreground text-lg">
                        Extração determinística de dados financeiros sem alucinações.
                    </p>

                    {/* Botões de Histórico e Estatísticas */}
                    <div className="flex justify-center gap-4 mt-4">
                        <Button
                            onClick={carregarHistorico}
                            variant="outline"
                            className="gap-2"
                        >
                            <FileText className="h-4 w-4" />
                            Ver Histórico do Banco
                        </Button>
                        <Button
                            onClick={carregarEstatisticas}
                            variant="outline"
                            className="gap-2"
                        >
                            <CheckCircle2 className="h-4 w-4" />
                            Estatísticas
                        </Button>
                        <Button
                            onClick={limparBanco}
                            variant="destructive"
                            className="gap-2"
                        >
                            <AlertCircle className="h-4 w-4" />
                            Limpar Banco
                        </Button>
                    </div>

                    {/* Estatísticas */}
                    {estatisticas && (
                        <Card className="mt-4 bg-primary/5">
                            <CardContent className="pt-6">
                                <div className="grid grid-cols-3 gap-4 text-center">
                                    <div>
                                        <div className="text-2xl font-bold text-primary">{estatisticas.total_registros}</div>
                                        <div className="text-xs text-muted-foreground">Registros no Banco</div>
                                    </div>
                                    <div>
                                        <div className="text-2xl font-bold text-primary">{estatisticas.total_arquivos}</div>
                                        <div className="text-xs text-muted-foreground">Arquivos Processados</div>
                                    </div>
                                    <div>
                                        <div className="text-2xl font-bold text-primary">
                                            {Object.keys(estatisticas.distribuicao_campos || {}).length}
                                        </div>
                                        <div className="text-xs text-muted-foreground">Tipos de Campos</div>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    )}
                </header>

                {/* Modal de Histórico */}
                {historicoAberto && (
                    <Card className="border-primary/50">
                        <CardHeader>
                            <div className="flex justify-between items-center">
                                <CardTitle>Histórico do Banco de Dados</CardTitle>
                                <Button
                                    onClick={() => setHistoricoAberto(false)}
                                    variant="ghost"
                                    size="sm"
                                >
                                    ✕
                                </Button>
                            </div>
                            <CardDescription>
                                Últimas {historico.length} extrações gravadas (fonte única de verdade)
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="max-h-96 overflow-y-auto space-y-2">
                                {historico.map((reg) => (
                                    <div
                                        key={reg.id}
                                        className="p-3 border rounded-lg hover:bg-muted/50 transition-colors"
                                    >
                                        <div className="flex justify-between items-start">
                                            <div>
                                                <div className="font-semibold text-sm">{reg.campo}</div>
                                                <div className="text-xs text-muted-foreground">
                                                    {reg.arquivo_nome} • Página {reg.pagina}
                                                </div>
                                            </div>
                                            <div className="text-right">
                                                <div className="font-bold text-primary">
                                                    R$ {reg.valor.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                                </div>
                                                <div className="text-xs text-muted-foreground">{reg.data_extracao}</div>
                                            </div>
                                        </div>
                                        {reg.linha_ocr && (
                                            <div className="mt-2 text-xs text-muted-foreground italic truncate">
                                                {reg.linha_ocr}
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </CardContent>
                    </Card>
                )}

                <Card className="glass animate-in">
                    <CardHeader>
                        <CardTitle>Processar Extrato</CardTitle>
                        <CardDescription>Upload de arquivos PDF ou Imagens (Google Vision OCR)</CardDescription>
                    </CardHeader>
                    <CardContent className="flex flex-col items-center justify-center border-2 border-dashed border-muted rounded-lg p-12 transition-colors hover:border-primary/50">
                        <input
                            type="file"
                            id="file-upload"
                            className="hidden"
                            onChange={(e) => {
                                setFile(e.target.files[0])
                                setError(null)
                                console.log('📁 Arquivo selecionado:', e.target.files[0]?.name)
                            }}
                            accept=".pdf,.png,.jpg,.jpeg"
                        />
                        <label htmlFor="file-upload" className="flex flex-col items-center cursor-pointer space-y-4">
                            <div className="p-4 bg-primary/10 rounded-full">
                                <Upload className="h-8 w-8 text-primary" />
                            </div>
                            <div className="text-center">
                                <span className="font-semibold text-primary">Clique para selecionar</span>
                                <p className="text-sm text-muted-foreground">{file ? file.name : 'PDF ou Imagem'}</p>
                            </div>
                        </label>
                        {file && (
                            <Button
                                onClick={(e) => {
                                    e.preventDefault();
                                    console.log('🔘 Botão clicado!');
                                    handleUpload();
                                }}
                                disabled={loading}
                                className="mt-6 btn-premium"
                                type="button"
                            >
                                {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileText className="mr-2 h-4 w-4" />}
                                {loading ? 'Processando...' : 'Iniciar Extração'}
                            </Button>
                        )}

                        {/* NOVO: Barra de Progresso em Tempo Real */}
                        {loading && progressMessage && (
                            <div className="mt-6 w-full space-y-3">
                                <div className="flex items-center justify-between text-sm">
                                    <span className="text-muted-foreground">{progressMessage}</span>
                                    <span className="font-semibold text-primary">{progressPercent}%</span>
                                </div>
                                <div className="w-full h-3 bg-muted rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-gradient-to-r from-blue-500 to-purple-500 transition-all duration-300 ease-out"
                                        style={{ width: `${progressPercent}%` }}
                                    />
                                </div>
                                <p className="text-xs text-muted-foreground text-center">
                                    {progressPercent < 50 && "Lendo e corrigindo páginas..."}
                                    {progressPercent >= 50 && progressPercent < 95 && "Extraindo resumos mensais..."}
                                    {progressPercent >= 95 && progressPercent < 100 && "Salvando no banco de dados..."}
                                    {progressPercent === 100 && "✓ Concluído!"}
                                </p>
                            </div>
                        )}

                        {error && (
                            <div className="mt-4 p-4 bg-red-500/10 border border-red-500/50 rounded-lg text-red-500 text-sm">
                                <AlertCircle className="inline-block mr-2 h-4 w-4" />
                                {error}
                            </div>
                        )}
                    </CardContent>
                </Card>

                {results && (!results.resumos_mensais || Object.keys(results.resumos_mensais).length === 0) && (
                    <Card className="mt-8 border-amber-500/50 bg-amber-500/5">
                        <CardHeader>
                            <CardTitle className="text-amber-600">⚠️ Nenhum Resumo Mensal Encontrado</CardTitle>
                            <CardDescription>
                                O OCR foi executado, mas não foram encontradas seções de "Resumo do Mês" no documento.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <p className="text-sm text-muted-foreground mb-2">
                                <strong>Possíveis causas:</strong>
                            </p>
                            <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                                <li>O documento não contém seção "Resumo do Mês"</li>
                                <li>A qualidade do OCR está muito baixa</li>
                                <li>O formato do documento não corresponde ao esperado</li>
                            </ul>

                            {results.ocr_bruto && results.ocr_bruto !== "Falha na leitura OCR" && (
                                <details className="mt-4">
                                    <summary className="cursor-pointer text-sm font-semibold text-primary">
                                        Ver texto extraído pelo OCR
                                    </summary>
                                    <pre className="mt-2 p-4 bg-muted rounded text-xs overflow-auto max-h-60">
                                        {results.ocr_bruto}
                                    </pre>
                                </details>
                            )}
                        </CardContent>
                    </Card>
                )}

                {/* Resumo de Cobertura do Documento */}
                {results && results.resumos_mensais && Object.keys(results.resumos_mensais).length > 0 && (
                    <Card className="border-blue-500/50 bg-blue-50/50 dark:bg-blue-950/20">
                        <CardHeader>
                            <CardTitle className="text-blue-700 dark:text-blue-400">📊 Resumo do Processamento</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="grid grid-cols-2 gap-4 text-center">
                                <div className="p-3 bg-white dark:bg-gray-800 rounded border">
                                    <div className="text-2xl font-bold text-amber-600">
                                        {Object.keys(results.resumos_mensais).length}
                                    </div>
                                    <div className="text-xs text-muted-foreground mt-1">
                                        Resumos Mensais Extraídos
                                    </div>
                                </div>
                                <div className="p-3 bg-white dark:bg-gray-800 rounded border">
                                    <div className="text-2xl font-bold text-green-600">
                                        8
                                    </div>
                                    <div className="text-xs text-muted-foreground mt-1">
                                        Campos por Resumo
                                    </div>
                                </div>
                            </div>
                            <p className="text-xs text-center text-muted-foreground mt-4">
                                💡 Exibindo apenas os resumos mensais consolidados
                            </p>
                        </CardContent>
                    </Card>
                )}

                {/* Renderiza APENAS Resumos Mensais */}
                {results && results.resumos_mensais &&
                    Object.keys(results.resumos_mensais).map((pageNum) => (
                        <div key={`resumo-${pageNum}`} className="space-y-4">
                            <h2 className="text-xl font-bold border-l-4 border-amber-500 pl-4 mt-8">
                                Página {pageNum}
                            </h2>

                            {/* Card de Resumo Mensal */}
                            <Card className="border-2 border-amber-500 bg-amber-50/50 dark:bg-amber-950/20">
                                <CardHeader>
                                    <CardTitle className="text-amber-700 dark:text-amber-400">
                                        📊 Resumo do Mês
                                    </CardTitle>
                                    <CardDescription>
                                        Extração determinística da seção de resumo mensal
                                    </CardDescription>
                                </CardHeader>
                                <CardContent>
                                    <div className="grid grid-cols-2 gap-3">
                                        {Object.entries({
                                            "Saldo Anterior": results.resumos_mensais[pageNum].campos.saldo_anterior,
                                            "Aplicações (+)": results.resumos_mensais[pageNum].campos.aplicacoes,
                                            "Resgates (-)": results.resumos_mensais[pageNum].campos.resgates,
                                            "Rendimento Bruto (+)": results.resumos_mensais[pageNum].campos.rendimento_bruto,
                                            "Imposto de Renda (-)": results.resumos_mensais[pageNum].campos.imposto_renda,
                                            "IOF (-)": results.resumos_mensais[pageNum].campos.iof,
                                            "Rendimento Líquido": results.resumos_mensais[pageNum].campos.rendimento_liquido,
                                            "Saldo Atual": results.resumos_mensais[pageNum].campos.saldo_atual
                                        }).map(([label, valor]) => (
                                            <div key={label} className="p-3 bg-white dark:bg-gray-800 rounded border">
                                                <div className="text-xs text-muted-foreground font-medium uppercase mb-1">
                                                    {label}
                                                </div>
                                                <div className="text-lg font-bold text-amber-700 dark:text-amber-400">
                                                    {valor !== null && valor !== undefined
                                                        ? `R$ ${valor.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`
                                                        : '---'}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </CardContent>
                            </Card>
                        </div>
                    ))
                }

            </div>
        </div>
    )
}

export default App
