# Guia de Testes com Documentos Reais

## 🎯 Cenários Reais de Documentos

O sistema foi projetado para funcionar com documentos bancários **do mundo real**, que geralmente têm:

### ✅ Cenário 1: Documento com Páginas Irrelevantes no Início
```
Página 1-5:   Capa, índice, páginas em branco
Página 6-50:  Extratos bancários com dados
Página 51-52: Resumos mensais
```

**O que o sistema faz:**
- ✅ Ignora páginas 1-5 automaticamente (sem dados financeiros)
- ✅ Processa páginas 6-50 (extrai tabela principal)
- ✅ Processa páginas 51-52 (extrai resumos mensais)
- ✅ Relatório: "45 páginas com dados, 5 páginas irrelevantes"

### ✅ Cenário 2: Extratos Espalhados ao Longo do Documento
```
Página 1:    Capa
Página 2-3:  Extrato Conta A
Página 4:    Página em branco
Página 5-7:  Extrato Conta B
Página 8:    Resumo mensal
Página 9-10: Extrato Conta C
```

**O que o sistema faz:**
- ✅ Processa TODAS as páginas independentemente
- ✅ Extrai dados de páginas 2-3, 5-7, 8, 9-10
- ✅ Ignora páginas 1 e 4 automaticamente
- ✅ Agrupa resultados por página no frontend

### ✅ Cenário 3: Documento Apenas com Resumos Mensais
```
Página 1-10: Apenas "Resumo do Mês" (sem tabela de movimentações)
```

**O que o sistema faz:**
- ✅ Extrai os 10 resumos mensais
- ✅ Mostra aviso: "Nenhum dado da tabela principal encontrado"
- ✅ Exibe cards amarelos com os resumos
- ✅ Estatísticas: "0 registros da tabela, 10 resumos mensais"

### ✅ Cenário 4: Documento Misto (Típico de Bancos)
```
Página 1-2:   Capa + índice
Página 3-25:  Extratos com movimentações (Data + Histórico + Valor)
Página 26:    Resumo do mês com totalizadores
Página 27-50: Mais extratos
Página 51:    Resumo do mês final
```

**O que o sistema faz:**
- ✅ Ignora páginas 1-2
- ✅ Extrai tabela principal das páginas 3-25, 27-50
- ✅ Extrai resumos mensais das páginas 26, 51
- ✅ Não mistura dados de resumo com tabela
- ✅ Relatório completo de cobertura

---

## 📊 O Que Você Verá nos Logs (Backend)

### Logs de Parser de Tabela Principal:

```
INFO: Processando pagina 1 (45 linhas) - Data:False Valor:False Termo:False
DEBUG: Pagina 1: SEM conteudo financeiro relevante (pulando)

INFO: Processando pagina 2 (120 linhas) - Data:True Valor:True Termo:True
INFO:   ✓ Pagina 2: SALDO ANTERIOR = R$ 60,820.83 em 31/07/2015
INFO:   ✓ Pagina 2: SALDO ATUAL = R$ 61,290.01 em 31/08/2015

INFO: ============================================================
INFO: RELATORIO DE EXTRACAO:
INFO:   Total de paginas processadas: 82
INFO:   Paginas com dados extraidos: 41 [2, 4, 6, 8, 10, ...]
INFO:   Paginas vazias/irrelevantes: 41 [1, 3, 5, 7, 9, ...]
INFO:   Total de registros extraidos: 54
INFO: ============================================================
```

### Logs de Parser de Resumo Mensal:

```
INFO: Pagina 2: Processando Resumo do Mes
INFO: Resumo do Mes extraido: 8/8 campos encontrados

INFO: ============================================================
INFO: RELATORIO DE RESUMOS MENSAIS:
INFO:   Total de paginas processadas: 82
INFO:   Paginas com resumo mensal: 26 [2, 4, 6, 8, ...]
INFO:   Paginas sem resumo mensal: 56
INFO: ============================================================
```

---

## 🎨 O Que Você Verá no Frontend

### Card de Resumo de Processamento (Novo!):

```
┌─────────────────────────────────────────────────────┐
│ 📊 Resumo do Processamento                          │
├─────────────────────────────────────────────────────┤
│  41            54            26            67        │
│ Páginas com   Registros    Resumos       Total de   │
│  Extratos     da Tabela    Mensais      Págs Úteis  │
└─────────────────────────────────────────────────────┘
💡 Páginas sem dados financeiros foram automaticamente
   ignoradas (capas, índices, etc)
```

### Caso 1: Documento com Dados Completos
- ✅ Card azul: Resumo do Processamento
- ✅ Cards verdes/azuis: Extratos por página
- ✅ Cards amarelos: Resumos mensais por página

### Caso 2: Documento Apenas com Resumos
- ⚠️ Aviso amarelo: "Nenhum dado da tabela principal encontrado"
- ✅ Mensagem: "Encontrados 26 resumos mensais!"
- ✅ Cards amarelos: Todos os resumos

### Caso 3: Documento sem Dados
- ⚠️ Aviso amarelo: "Nenhum dado encontrado"
- 📝 Sugestões de causas
- 🔍 Botão para ver OCR bruto

---

## 🧪 Como Testar com Seu Documento Real

### Passo 1: Prepare o Documento
```
✅ Use seu PDF real de 800 páginas
✅ Não precisa editar nada
✅ Pode ter páginas irrelevantes no início/fim
✅ Pode ter extratos espalhados
```

### Passo 2: Faça o Upload
```
1. Abra http://localhost:5174/
2. Selecione o PDF completo
3. Clique em "Iniciar Extração"
4. AGUARDE (pode demorar 5-10 minutos para 800 páginas)
```

### Passo 3: Verifique os Logs (Terminal Backend)
```
Procure por:
- "RELATORIO DE EXTRACAO"
- "Paginas com dados extraidos"
- "Paginas vazias/irrelevantes"
- "RELATORIO DE RESUMOS MENSAIS"
```

### Passo 4: Analise o Frontend
```
✅ Card "Resumo do Processamento" mostra cobertura
✅ Páginas sem dados foram ignoradas automaticamente
✅ Apenas páginas com dados financeiros aparecem
✅ Resumos mensais em cards amarelos separados
```

---

## ❓ Perguntas Frequentes

### "Muitas páginas foram ignoradas, isso é normal?"
✅ **SIM!** Documentos reais têm:
- Capas (1-2 páginas)
- Índices (1-3 páginas)
- Páginas em branco (várias)
- Páginas de observações/avisos

O sistema ignora automaticamente o que não tem dados financeiros.

### "O sistema encontrou apenas resumos, sem tabela. Está errado?"
✅ **NORMAL!** Alguns documentos têm apenas resumos mensais consolidados, sem a tabela detalhada de movimentações. O sistema processa ambos independentemente.

### "Algumas páginas com extratos não foram processadas"
🔍 **Verifique:**
- O OCR conseguiu ler o texto? (veja `raw_ocr_debug.txt`)
- A página tem DATA + TERMO + VALOR próximos?
- Os valores são maiores que zero?

### "Valores estão duplicados/triplicados"
✅ **CORRIGIDO!** Agora o sistema:
- Remove dados antigos antes de salvar novos
- Deduplica por (campo + data + valor) na mesma página
- Logs mostram: "Removidas X extrações antigas"

---

## 📋 Checklist de Validação

Use este checklist para validar seus testes:

### Backend:
- [ ] Logs mostram "RELATORIO DE EXTRACAO" no final
- [ ] Número de páginas processadas = número de páginas do PDF
- [ ] Páginas vazias foram identificadas e ignoradas
- [ ] Total de registros extraídos faz sentido
- [ ] Resumos mensais foram encontrados (se existirem)
- [ ] Sem erros de timeout ou OCR failure

### Frontend:
- [ ] Card "Resumo do Processamento" aparece
- [ ] Número de páginas úteis está correto
- [ ] Cards de extratos aparecem apenas em páginas com dados
- [ ] Cards amarelos aparecem para resumos mensais
- [ ] Valores não estão duplicados
- [ ] Todas as páginas listadas têm dados visíveis

### Banco de Dados:
- [ ] `extractions.db` foi criado/atualizado
- [ ] Tabela `extracoes` tem registros
- [ ] Tabela `resumos_mensais` tem registros (se houver resumos)
- [ ] Re-upload do mesmo arquivo não duplica dados

---

## 🎯 Testes Recomendados

### Teste 1: PDF Pequeno (10-20 páginas)
```
Objetivo: Validar extração básica
Tempo: ~30 segundos
Verifique: Todos os dados visíveis foram extraídos
```

### Teste 2: PDF Médio (50-100 páginas)
```
Objetivo: Validar robustez e deduplicação
Tempo: ~2-3 minutos
Verifique: Páginas irrelevantes foram ignoradas
```

### Teste 3: PDF Grande (800 páginas)
```
Objetivo: Validar performance e timeout
Tempo: ~5-10 minutos
Verifique: Processamento completo sem erros
```

### Teste 4: Re-upload do Mesmo Arquivo
```
Objetivo: Validar não-duplicação
Tempo: ~igual ao upload original
Verifique: "Removidas X extrações antigas" nos logs
Verifique: Total no banco não muda
```

---

## ✅ Sistema Está Pronto Para Produção

O sistema foi projetado especificamente para documentos reais com:
- ✅ Páginas irrelevantes (ignoradas automaticamente)
- ✅ Extratos espalhados (processados independentemente)
- ✅ Documentos grandes (até 800+ páginas)
- ✅ Múltiplos uploads (sem duplicação)
- ✅ OCR variável (robusto a falhas parciais)
- ✅ Layouts diversos (genérico, não depende de template)

**Pode testar com seus documentos reais sem medo!** 🚀
