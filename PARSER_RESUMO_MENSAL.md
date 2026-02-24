# Parser de Resumo Mensal - Documentação Técnica

## 🎯 Objetivo

Extrair deterministicamente a seção "Resumo do mês" dos extratos bancários, **sem usar IA generativa**, **sem inventar valores** e mantendo **100% de auditabilidade**.

---

## 📋 Campos Extraídos (Sempre Presentes)

O parser extrai **EXATAMENTE 8 campos** na seguinte ordem:

1. **SALDO ANTERIOR** - Saldo do mês anterior
2. **APLICAÇÕES (+)** - Valores aplicados no período
3. **RESGATES (-)** - Valores resgatados no período
4. **RENDIMENTO BRUTO (+)** - Rendimentos antes de impostos
5. **IMPOSTO DE RENDA (-)** - IR retido na fonte
6. **IOF (-)** - Imposto sobre Operações Financeiras
7. **RENDIMENTO LÍQUIDO** - Rendimento após impostos
8. **SALDO ATUAL** - Saldo final do período

---

## 🔍 Lógica de Extração

### 1. Detecção da Seção

```python
# Busca "Resumo do mês" (case-insensitive, aceita variações)
if re.search(r"RESUMO\s+DO\s+M[EÊ]S", page_text, re.IGNORECASE):
    # Seção encontrada
```

### 2. Extração do Bloco

O parser extrai apenas o bloco de texto relevante:

- **Início:** Primeira ocorrência de "Resumo do mês"
- **Fim:** Detecta automaticamente quando a seção termina:
  - Nova tabela (com datas `dd/mm/yyyy`)
  - Múltiplas linhas vazias
  - Início de nova seção ("Extrato", "Data Histórico", etc)

### 3. Regex por Campo

Cada campo possui um regex específico que aceita variações de OCR:

```python
regex_patterns = {
    "saldo_anterior": r"SALDO\s+ANTERIOR\s*([\d\.\s,]+)",
    "aplicacoes": r"APLICA[CÇ][OÕ]ES\s*\(\+\)\s*([\d\.\s,]+)",
    "resgates": r"RESGATES?\s*\(-\)\s*([\d\.\s,]+)",
    "rendimento_bruto": r"RENDIMENTO\s+BRUTO\s*\(\+\)\s*([\d\.\s,]+)",
    "imposto_renda": r"IMPOSTO\s+DE\s+RENDA\s*\(-\)\s*([\d\.\s,]+)",
    "iof": r"IOF\s*\(-\)\s*([\d\.\s,]+)",
    "rendimento_liquido": r"RENDIMENTO\s+L[IÍ]QUIDO\s*([\d\.\s,]+)",
    "saldo_atual": r"SALDO\s+ATUAL\s*=?\s*([\d\.\s,]+)"
}
```

### 4. Limpeza de Valores

```python
def clean_value(self, value_str: str) -> Optional[float]:
    # Remove espaços: "60 820,83" → "60820,83"
    # Converte pontos: "60.820,83" → "60820,83"
    # Converte vírgula: "60820,83" → "60820.83"
    # Retorna float: 60820.83
    
    # IMPORTANTE: 0,00 é VÁLIDO e retorna 0.0
    # Retorna None apenas se não conseguir parsear
```

---

## ✅ Regras Obrigatórias

### 1. **Valores 0,00 SÃO VÁLIDOS**
```json
{
  "aplicacoes": 0.0,  // ✅ CORRETO
  "resgates": 0.0     // ✅ CORRETO
}
```

### 2. **Campo não encontrado = null**
```json
{
  "iof": null  // ✅ CORRETO (não encontrado no OCR)
}
```

### 3. **NUNCA inventar valores**
```python
# ❌ PROIBIDO
if not found_value:
    return 0.0  # NUNCA fazer isso

# ✅ CORRETO
if not found_value:
    return None  # Retorna null
```

### 4. **NUNCA calcular ou inferir**
```python
# ❌ PROIBIDO
saldo_atual = saldo_anterior + aplicacoes - resgates + rendimento_liquido

# ✅ CORRETO
# Cada campo é extraído INDEPENDENTEMENTE por regex
```

### 5. **Não exigir data por linha**
- Resumo mensal é um bloco semântico
- NÃO possui datas individuais por campo
- Diferente da tabela principal

---

## 🗄️ Estrutura no Banco de Dados

### Tabela: `resumos_mensais`

| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | INTEGER | ID único |
| arquivo_nome | TEXT | Nome do arquivo |
| data_processamento | TEXT | Timestamp do processamento |
| pagina | INTEGER | Número da página |
| saldo_anterior | REAL | Permite NULL |
| aplicacoes | REAL | Permite NULL |
| resgates | REAL | Permite NULL |
| rendimento_bruto | REAL | Permite NULL |
| imposto_renda | REAL | Permite NULL |
| iof | REAL | Permite NULL |
| rendimento_liquido | REAL | Permite NULL |
| saldo_atual | REAL | Permite NULL |
| created_at | TIMESTAMP | Timestamp da gravação |

**Nota:** Todos os campos de valor permitem NULL para representar "não encontrado".

---

## 📊 Saída JSON (API)

```json
{
  "resultados_por_pagina": {
    "1": [
      { "campo": "SALDO ANTERIOR", "valor": 60820.83, ... }
    ]
  },
  "resumos_mensais": {
    "1": {
      "tipo": "RESUMO_MENSAL",
      "pagina": 1,
      "campos": {
        "saldo_anterior": 60820.83,
        "aplicacoes": 0.0,
        "resgates": 0.0,
        "rendimento_bruto": 469.18,
        "imposto_renda": 0.0,
        "iof": 0.0,
        "rendimento_liquido": 469.18,
        "saldo_atual": 61290.01
      }
    }
  },
  "ocr_bruto": "..."
}
```

---

## 🎨 Renderização no Frontend

### Card de Resumo Mensal

```jsx
<Card className="border-2 border-amber-500 bg-amber-50">
  <CardHeader>
    <CardTitle>📊 Resumo do Mês</CardTitle>
  </CardHeader>
  <CardContent>
    <div className="grid grid-cols-2 gap-3">
      {/* Todos os 8 campos são renderizados SEMPRE */}
      {Object.entries({
        "Saldo Anterior": campos.saldo_anterior,
        "Aplicações (+)": campos.aplicacoes,
        "Resgates (-)": campos.resgates,
        "Rendimento Bruto (+)": campos.rendimento_bruto,
        "Imposto de Renda (-)": campos.imposto_renda,
        "IOF (-)": campos.iof,
        "Rendimento Líquido": campos.rendimento_liquido,
        "Saldo Atual": campos.saldo_atual
      }).map(([label, valor]) => (
        <div key={label}>
          <div className="text-xs">{label}</div>
          <div className="text-lg font-bold">
            {valor !== null 
              ? `R$ ${valor.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}` 
              : '---'}
          </div>
        </div>
      ))}
    </div>
  </CardContent>
</Card>
```

**Características:**
- ✅ Todos os 8 campos sempre visíveis
- ✅ Valores 0,00 são exibidos como "R$ 0,00"
- ✅ Valores não encontrados são exibidos como "---"
- ✅ Nenhum campo desaparece
- ✅ Nenhuma lógica de interpretação

---

## 🔄 Fluxo Completo

```
1. OCR (Google Vision)
   ↓
2. Detecta "Resumo do mês" no texto da página?
   ├─ NÃO → Parser de tabela principal apenas
   └─ SIM → Parser de tabela + Parser de resumo
       ↓
3. Parser de Resumo Mensal
   ├─ Extrai bloco da seção
   ├─ Aplica regex em cada campo
   ├─ Converte valores (aceita 0,00)
   └─ Retorna JSON estruturado
       ↓
4. Salva no Banco (tabela resumos_mensais)
   ↓
5. Lista do Banco
   ↓
6. Frontend renderiza Card de Resumo
```

---

## 🧪 Casos de Teste

### Caso 1: Todos os campos encontrados
**OCR:**
```
Resumo do mês
SALDO ANTERIOR       60.820,83
APLICAÇÕES (+)            0,00
RESGATES (-)              0,00
RENDIMENTO BRUTO (+)    469,18
IMPOSTO DE RENDA (-)      0,00
IOF (-)                   0,00
RENDIMENTO LÍQUIDO      469,18
SALDO ATUAL =        61.290,01
```

**Saída:**
```json
{
  "saldo_anterior": 60820.83,
  "aplicacoes": 0.0,
  "resgates": 0.0,
  "rendimento_bruto": 469.18,
  "imposto_renda": 0.0,
  "iof": 0.0,
  "rendimento_liquido": 469.18,
  "saldo_atual": 61290.01
}
```

### Caso 2: Alguns campos não encontrados (OCR ruim)
**OCR:**
```
Resumo do mês
SALDO ANTERIOR       60.820,83
RENDIMENTO LÍQUIDO      469,18
SALDO ATUAL          61.290,01
```

**Saída:**
```json
{
  "saldo_anterior": 60820.83,
  "aplicacoes": null,
  "resgates": null,
  "rendimento_bruto": null,
  "imposto_renda": null,
  "iof": null,
  "rendimento_liquido": 469.18,
  "saldo_atual": 61290.01
}
```

**Frontend exibe:**
```
Saldo Anterior: R$ 60.820,83
Aplicações (+): ---
Resgates (-): ---
Rendimento Bruto (+): ---
Imposto de Renda (-): ---
IOF (-): ---
Rendimento Líquido: R$ 469,18
Saldo Atual: R$ 61.290,01
```

---

## 🔒 Garantias de Qualidade

### 1. **100% Determinístico**
- Mesmo OCR → Mesma saída
- Apenas regex e lógica fixa
- Zero aleatoriedade

### 2. **100% Auditável**
- Todos os dados no banco SQLite
- Logs detalhados de cada campo
- Rastreabilidade completa

### 3. **Zero Alucinações**
- Nunca inventa valores
- Nunca calcula valores
- Nunca infere valores

### 4. **Separação Clara**
- Parser de tabela principal ≠ Parser de resumo
- Tabela `extracoes` ≠ Tabela `resumos_mensais`
- Não há mistura de lógicas

---

## 📝 Arquivos Criados/Modificados

### Novos:
- `backend/monthly_summary_parser.py` - Parser de resumo mensal

### Modificados:
- `backend/extraction_service.py` - Integração com parser
- `backend/database.py` - Nova tabela e métodos
- `backend/models.py` - Campo `resumos_mensais`
- `src/App.jsx` - Card de resumo mensal

---

## ✅ Critérios de Sucesso

- [x] Parser 100% determinístico (apenas regex)
- [x] Valores 0,00 são aceitos e exibidos
- [x] Campos não encontrados retornam null (exibem "---")
- [x] Todos os 8 campos sempre aparecem no frontend
- [x] Nenhum valor é inventado ou calculado
- [x] Sistema continua auditável
- [x] Banco de dados persiste resumos
- [x] Frontend renderiza card único e claro

---

## 🚀 Como Testar

1. **Prepare um PDF com "Resumo do mês"**
2. **Faça upload no sistema**
3. **Observe:**
   - Card amarelo "📊 Resumo do Mês" aparece na página correta
   - Todos os 8 campos estão visíveis
   - Valores 0,00 aparecem como "R$ 0,00"
   - Campos não encontrados aparecem como "---"
4. **Verifique o banco:**
   ```sql
   SELECT * FROM resumos_mensais ORDER BY created_at DESC LIMIT 1;
   ```

---

## 🎯 Resultado Final

O sistema agora possui **dois parsers independentes e determinísticos**:

1. **Parser de Tabela Principal** (`parser_service.py`)
   - Extrai: SALDO ANTERIOR, SALDO ATUAL, RESGATE
   - Requisitos: Data + Termo + Valor
   - Ignora: "Resumo do mês", valores zerados

2. **Parser de Resumo Mensal** (`monthly_summary_parser.py`)
   - Extrai: 8 campos do resumo
   - Requisitos: Apenas termos + valores
   - Aceita: Valores zerados, campos ausentes

**Ambos sem alucinações. Ambos auditáveis. Ambos determinísticos.** ✅
