import { useState } from 'react'

function AppDebug() {
    const [file, setFile] = useState(null)
    const [loading, setLoading] = useState(false)
    const [results, setResults] = useState(null)
    const [error, setError] = useState(null)
    const [logs, setLogs] = useState([])

    const addLog = (message) => {
        const timestamp = new Date().toLocaleTimeString()
        setLogs(prev => [...prev, `[${timestamp}] ${message}`])
        console.log(message)
    }

    const handleUpload = async () => {
        if (!file) {
            addLog('❌ Nenhum arquivo selecionado')
            alert('Por favor, selecione um arquivo primeiro!')
            return
        }
        
        addLog(`🚀 Iniciando upload: ${file.name} (${file.size} bytes)`)
        setLoading(true)
        setResults(null)
        setError(null)
        
        const formData = new FormData()
        formData.append('file', file)

        try {
            addLog('📡 Enviando requisição para http://127.0.0.1:58009/extract')
            
            const response = await fetch('http://127.0.0.1:58009/extract', {
                method: 'POST',
                body: formData,
            })

            addLog(`📥 Resposta recebida: ${response.status} ${response.statusText}`)

            if (!response.ok) {
                const errJson = await response.json().catch(() => ({ detail: 'Erro desconhecido' }));
                throw new Error(errJson.detail || `Erro HTTP ${response.status}`);
            }

            const data = await response.json()
            addLog(`✅ Dados extraídos: ${Object.keys(data.resultados_por_pagina).length} páginas`)
            setResults(data)
        } catch (error) {
            addLog(`❌ Erro: ${error.message}`)
            setError(error.message)
            alert(`Erro: ${error.message}`)
        } finally {
            setLoading(false)
            addLog('🏁 Processamento finalizado')
        }
    }

    return (
        <div style={{ padding: '20px', fontFamily: 'monospace' }}>
            <h1>🔧 Debug Mode - Convênio 2.0</h1>
            
            <div style={{ marginTop: '20px', padding: '20px', border: '2px solid #ccc', borderRadius: '8px' }}>
                <h2>Upload de Arquivo</h2>
                
                <input
                    type="file"
                    onChange={(e) => {
                        setFile(e.target.files[0])
                        addLog(`📁 Arquivo selecionado: ${e.target.files[0]?.name}`)
                    }}
                    accept=".pdf,.png,.jpg,.jpeg"
                    style={{ margin: '10px 0', padding: '10px' }}
                />
                
                <br />
                
                <button
                    onClick={handleUpload}
                    disabled={loading || !file}
                    style={{
                        padding: '12px 24px',
                        fontSize: '16px',
                        backgroundColor: loading ? '#ccc' : '#4CAF50',
                        color: 'white',
                        border: 'none',
                        borderRadius: '5px',
                        cursor: loading ? 'not-allowed' : 'pointer',
                        marginTop: '10px'
                    }}
                >
                    {loading ? '⏳ Processando...' : '🚀 Iniciar Extração'}
                </button>
            </div>

            {error && (
                <div style={{ marginTop: '20px', padding: '15px', backgroundColor: '#ffebee', border: '2px solid #f44336', borderRadius: '8px', color: '#c62828' }}>
                    <strong>❌ Erro:</strong> {error}
                </div>
            )}

            <div style={{ marginTop: '20px', padding: '20px', backgroundColor: '#f5f5f5', borderRadius: '8px', maxHeight: '300px', overflowY: 'auto' }}>
                <h3>📋 Logs de Execução</h3>
                {logs.map((log, i) => (
                    <div key={i} style={{ padding: '5px 0', borderBottom: '1px solid #ddd' }}>
                        {log}
                    </div>
                ))}
            </div>

            {results && (
                <div style={{ marginTop: '20px', padding: '20px', backgroundColor: '#e8f5e9', border: '2px solid #4CAF50', borderRadius: '8px' }}>
                    <h3>✅ Resultados</h3>
                    <p><strong>Páginas processadas:</strong> {Object.keys(results.resultados_por_pagina).length}</p>
                    
                    {Object.keys(results.resultados_por_pagina).map((pageNum) => (
                        <div key={pageNum} style={{ marginTop: '15px', padding: '15px', backgroundColor: 'white', borderRadius: '5px' }}>
                            <h4>Página {pageNum}</h4>
                            {results.resultados_por_pagina[pageNum].map((res, i) => (
                                <div key={i} style={{ padding: '10px', margin: '5px 0', backgroundColor: '#f9f9f9', borderLeft: '3px solid #4CAF50' }}>
                                    <strong>{res.campo}:</strong> R$ {res.valor?.toLocaleString('pt-BR', { minimumFractionDigits: 2 })} 
                                    <br />
                                    <small>Data: {res.data_extracao} | Confiança: {res.confianca}</small>
                                </div>
                            ))}
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}

export default AppDebug
