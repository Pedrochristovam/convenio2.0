# Sistema de Banco de Dados - Eliminando Alucinações

## 🎯 Problema Resolvido

Antes o sistema estava "alucinando" valores - retornando dados inconsistentes ou pulando registros. 

**Solução:** Agora TUDO é gravado em um banco de dados SQLite, criando uma **fonte única de verdade**.

## 🔄 Novo Fluxo de Processamento

```
1. OCR (Google Vision) → Extrai texto de todas as páginas
2. Parser Determinístico → Identifica campos, datas e valores
3. SALVA NO BANCO → Grava todos os registros (fonte confiável)
4. LISTA DO BANCO → Retorna os dados salvos (elimina inconsistências)
```

## 📊 Estrutura do Banco de Dados

### Tabela `extracoes`

| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | INTEGER | ID único da extração |
| arquivo_nome | TEXT | Nome do arquivo processado |
| data_processamento | TEXT | Data/hora do processamento |
| campo | TEXT | Campo extraído (SALDO ANTERIOR, SALDO ATUAL, RESGATE) |
| valor | REAL | Valor numérico extraído |
| data_extracao | TEXT | Data encontrada no documento |
| pagina | INTEGER | Número da página |
| linha_ocr | TEXT | Linha original do OCR |
| confianca | TEXT | Nível de confiança (ALTA, MEDIA, BAIXA) |
| status | TEXT | Status da extração (SUCESSO, FALHA) |
| created_at | TIMESTAMP | Timestamp da gravação |

## 📡 Novos Endpoints da API

### 1. `/extract` (POST)
Processa o documento e salva no banco.

**Novo comportamento:**
- Extrai dados do OCR
- Salva TUDO no banco
- Retorna os dados DO BANCO (não da memória)

### 2. `/historico` (GET)
Lista todas as extrações do banco.

**Parâmetros:**
- `limite` (opcional): Número máximo de registros (padrão: 100)

**Resposta:**
```json
{
  "total": 245,
  "registros": [
    {
      "id": 1,
      "arquivo_nome": "documento.pdf",
      "campo": "SALDO ANTERIOR",
      "valor": 60820.83,
      "data_extracao": "31/07/2015",
      "pagina": 1,
      "linha_ocr": "31/07/2015 SALDO ANTERIOR 60.820,83",
      "confianca": "ALTA",
      "status": "SUCESSO"
    }
  ]
}
```

### 3. `/historico/{arquivo_nome}` (GET)
Lista a última extração de um arquivo específico.

**Exemplo:**
```bash
GET /historico/documento.pdf
```

### 4. `/estatisticas` (GET)
Retorna estatísticas globais do banco.

**Resposta:**
```json
{
  "total_registros": 245,
  "total_arquivos": 12,
  "distribuicao_campos": {
    "SALDO ANTERIOR": 82,
    "SALDO ATUAL": 82,
    "RESGATE": 81
  }
}
```

## 🎨 Frontend Atualizado

### Novos Recursos:

1. **Botão "Ver Histórico do Banco"**
   - Mostra todas as extrações gravadas
   - Fonte única de verdade
   - Permite auditoria completa

2. **Botão "Estatísticas"**
   - Total de registros no banco
   - Total de arquivos processados
   - Distribuição por tipo de campo

3. **Card de Estatísticas**
   - Visualização em tempo real
   - 3 métricas principais
   - Atualiza após cada extração

## ✅ Vantagens do Sistema

### 1. **Elimina Alucinações**
- Os dados vêm direto do banco
- Não há processamento em memória
- Fonte única de verdade

### 2. **Auditoria Completa**
- Histórico de todas as extrações
- Timestamp de cada processamento
- Rastreabilidade total

### 3. **Performance**
- Índices otimizados no banco
- Busca rápida por arquivo/campo
- Consultas eficientes

### 4. **Confiabilidade**
- Dados persistidos em disco
- Não perde informações em restart
- Backup simples (arquivo .db)

## 📝 Arquivos Criados/Modificados

### Novo:
- `backend/database.py` - Classe para gerenciar o banco SQLite

### Modificados:
- `backend/extraction_service.py` - Integração com banco
- `backend/main.py` - Novos endpoints
- `src/App.jsx` - Interface com histórico

### Gerado:
- `extractions.db` - Banco de dados SQLite (criado automaticamente)

## 🚀 Como Usar

1. **Processar documento:**
   - Upload do PDF
   - Sistema extrai e salva no banco
   - Retorna dados do banco

2. **Ver histórico:**
   - Clique em "Ver Histórico do Banco"
   - Visualiza todas as extrações
   - Auditoria completa

3. **Ver estatísticas:**
   - Clique em "Estatísticas"
   - Visualiza métricas globais
   - Distribuição de campos

## 🔍 Verificação dos Dados

Para verificar os dados diretamente no banco:

```bash
# Instalar SQLite (se necessário)
# Windows: já vem com Python

# Abrir banco
sqlite3 extractions.db

# Ver todas as extrações
SELECT * FROM extracoes ORDER BY created_at DESC LIMIT 10;

# Contar registros por arquivo
SELECT arquivo_nome, COUNT(*) FROM extracoes GROUP BY arquivo_nome;

# Ver estatísticas por campo
SELECT campo, COUNT(*), AVG(valor) FROM extracoes GROUP BY campo;
```

## 🎯 Próximos Passos

- [x] Criar banco de dados
- [x] Salvar extrações
- [x] Endpoints de consulta
- [x] Frontend com histórico
- [ ] Export para Excel
- [ ] Filtros avançados no histórico
- [ ] Gráficos de evolução temporal
