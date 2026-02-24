# 🔍 Guia de Diagnóstico Detalhado - Encontrando o Problema Real

## 📊 Situação Atual

**Problema:** O sistema extrai valores, mas:
- ❌ Faltam valores (campos vazios quando não deveriam)
- ❌ Valores incorretos (números diferentes do PDF)
- ❌ Inconsistente (funciona em algumas páginas, falha em outras)

**Você está certo em duas coisas:**
1. ✅ Se eu (humano) consegui ler as imagens, o OCR também deveria conseguir
2. ✅ Páginas tortas PODEM afetar, mas o Google Vision é robusto contra isso

---

## 🎯 Vamos Descobrir O QUE Exatamente Está Acontecendo

### **Teste 1: Verificar O Que o OCR Está Lendo**

#### **Passo 1: Faça upload do PDF**
```
http://localhost:5174/
Upload → Aguarde
```

#### **Passo 2: Pegue o OCR de uma página problemática**
```
Abra no navegador:
http://127.0.0.1:61439/debug/ocr-page/2

(Substitua 2 pelo número da página com problema)
```

Isso vai mostrar:
- O texto EXATO que o OCR leu
- Linha por linha numerado
- Total de linhas

#### **Passo 3: Compare com o PDF**
```
Abra o PDF na página correspondente
Compare lado a lado:
- O que está no PDF
- O que o OCR leu
```

**Se o OCR estiver CORRETO:**
→ Problema é no PARSER (minha lógica de extração)
→ Posso corrigir facilmente

**Se o OCR estiver ERRADO:**
→ Problema é no Google Vision API
→ Precisamos de outra estratégia

---

## 🔬 Análise Detalhada de UMA Página

Vamos pegar **UMA página específica** que está com problema e analisar COMPLETAMENTE.

### **Escolha UMA página com problema óbvio:**
Exemplo: "Página 2 - SALDO ATUAL está vazio quando deveria ser R$ 61.290,01"

### **Execute o script de debug:**

```bash
# No terminal, na pasta do projeto:
python debug_ocr_page.py
```

**Antes de executar, edite o arquivo `debug_ocr_page.py`:**

1. Abra `raw_ocr_debug.txt`
2. Encontre a página problemática
3. Copie TODO o texto dessa página
4. Cole na variável `ocr_text` do script
5. Execute o script

**O script vai mostrar:**
- ✓ Onde cada campo foi encontrado
- ✓ Qual valor foi extraído
- ✓ Se não encontrou, mostra as linhas próximas
- ✓ Você verá EXATAMENTE o que o parser está vendo

---

## 📸 O Que Eu Preciso Para Ajudar

Para eu conseguir corrigir definitivamente, preciso de **UMA página completa** com:

### **1. Print/Screenshot do PDF original**
- Página inteira visível
- Seção "Resumo do Mês" legível
- Todos os valores visíveis

### **2. OCR dessa página**
```
GET http://127.0.0.1:61439/debug/ocr-page/X
```
Onde X = número da página

### **3. O que o sistema extraiu**
```
Screenshot do frontend mostrando os valores extraídos
```

### **4. Comparação lado a lado:**
```
| Campo               | PDF Original | OCR Leu    | Sistema Extraiu |
|---------------------|--------------|------------|-----------------|
| SALDO ANTERIOR      | 60.820,83    | ?          | ?               |
| APLICAÇÕES          | 0,00         | ?          | ?               |
| ...                 | ...          | ?          | ?               |
| SALDO ATUAL         | 61.290,01    | ?          | ?               |
```

---

## 💡 Hipóteses e Soluções

### **Hipótese 1: OCR Está Correto, Parser Está Errado**

**Sintomas:**
- OCR lê `SALDO ATUAL = 61.290,01` corretamente
- Mas parser não encontra ou pega valor errado

**Solução:**
- Ajustar regex do parser
- Ajustar lógica sequencial
- **Fácil de corrigir!**

### **Hipótese 2: OCR Está Lendo Errado**

**Sintomas:**
- OCR lê `SALDO ATUAL = 61.29O,O1` (com letra O em vez de zero)
- OCR pula linhas inteiras
- OCR lê valores de colunas erradas juntos

**Soluções Possíveis:**

#### **A) Pré-processar Imagens**
```python
# Antes de enviar para Google Vision:
1. Converter para escala de cinza
2. Aumentar contraste
3. Binarização (preto e branco puro)
4. Correção de rotação automática
5. Remoção de ruído
```

#### **B) Usar Tesseract Local**
```python
# Mais controle sobre OCR:
1. Configurar para português
2. Ajustar PSM (page segmentation mode)
3. Treinar com seus documentos específicos
```

#### **C) OCR Duplo com Validação**
```python
# Rodar 2 engines e comparar:
1. Google Vision
2. Tesseract
3. Retornar apenas valores que ambos concordam
```

#### **D) OCR por Região (Template)**
```python
# Se layout for fixo:
1. Detectar posição da tabela
2. Extrair cada célula separadamente
3. OCR individual por campo
```

### **Hipótese 3: Qualidade do PDF**

**Sintomas:**
- Páginas tortas
- Resolução baixa
- Tabelas com linhas finas que confundem OCR
- Fontes pequenas

**Soluções:**
```python
# Melhorar qualidade antes do OCR:
1. Aumentar DPI (de 72 para 300)
2. Aplicar sharpening
3. Melhorar iluminação
```

---

## 🚀 Próximos Passos IMEDIATOS

### **1. Diagnóstico (Agora):**
```
1. Faça upload do PDF
2. Acesse: http://127.0.0.1:61439/debug/ocr-page/2
3. Me envie o JSON completo
4. Me diga qual valor está errado
```

### **2. Análise (Com os dados acima):**
```
Eu vou:
1. Ver EXATAMENTE o que o OCR leu
2. Ver onde o parser está falhando
3. Corrigir o código especificamente
```

### **3. Se OCR Estiver Ruim:**
```
Implementamos uma das soluções:
- Pré-processamento de imagem
- Tesseract local
- OCR por região
```

---

## 📝 Template de Report

**Use este template para me enviar informações:**

```markdown
## Página Problemática: X

### O que deveria ser:
SALDO ANTERIOR: 60.820,83
APLICAÇÕES: 0,00
RESGATES: 0,00
RENDIMENTO BRUTO: 469,18
IMPOSTO RENDA: 0,00
IOF: 0,00
RENDIMENTO LÍQUIDO: 469,18
SALDO ATUAL: 61.290,01

### O que o sistema extraiu:
[Cole aqui ou screenshot]

### OCR dessa página:
[Cole o JSON de http://127.0.0.1:61439/debug/ocr-page/X]

### Observações:
- Campo SALDO ATUAL está vazio
- Ou: Campo X tem valor Y mas deveria ser Z
```

---

## ✅ Garantia

Com essas informações, eu CONSIGO identificar e corrigir o problema. 

**Por quê?**
- Se você (humano) consegue ler → é possível extrair
- Se o OCR ler certo → é só ajustar o parser
- Se o OCR ler errado → aplicamos uma das soluções de pré-processamento

---

## 🎯 URLs Úteis

**Frontend:** http://localhost:5174/  
**Backend:** http://127.0.0.1:61439  
**Debug OCR Página 2:** http://127.0.0.1:61439/debug/ocr-page/2  
**Debug OCR Página 4:** http://127.0.0.1:61439/debug/ocr-page/4  
**Debug OCR Página 6:** http://127.0.0.1:61439/debug/ocr-page/6  

---

**Vamos fazer esse diagnóstico detalhado e descobrir EXATAMENTE onde está o problema!** 🔍

Me envie o resultado de uma página problemática e vamos resolver isso de uma vez por todas.
