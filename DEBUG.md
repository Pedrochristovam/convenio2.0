# 🔧 Guia de Debug - Convênio 2.0

## Problema Reportado
O botão "Iniciar Extração" fica "bugado" e não inicia o processamento.

## Correções Aplicadas

### 1. Frontend (src/App.jsx)
- ✅ Adicionado logs detalhados no console
- ✅ Adicionado estado de erro com feedback visual
- ✅ Adicionado `type="button"` e `e.preventDefault()` no botão
- ✅ Melhorado tratamento de erros

### 2. Backend (backend/main.py)
- ✅ Adicionado endpoint `/test` para verificar conectividade
- ✅ Adicionado logs coloridos com emojis
- ✅ Melhorado tratamento de exceções

### 3. Arquivo de Debug
- ✅ Criado `src/AppDebug.jsx` - versão simplificada sem dependências de UI
- ✅ Criado `test_upload.html` - teste puro em HTML

## Como Testar

### Opção 1: Modo Debug (Recomendado)
1. Edite `src/main.jsx` e troque:
   ```jsx
   import App from './App.jsx'
   ```
   por:
   ```jsx
   import App from './AppDebug.jsx'
   ```

2. Acesse `http://localhost:5174`
3. Veja os logs em tempo real na tela

### Opção 2: HTML Puro
1. Abra `http://localhost:5174/test_upload.html`
2. Teste o upload diretamente

### Opção 3: Console do Navegador
1. Acesse `http://localhost:5174`
2. Abra DevTools (F12) → Console
3. Veja os logs detalhados

## Checklist de Diagnóstico

Quando clicar no botão, verifique:

- [ ] O botão muda para "Processando..."?
- [ ] Aparece algum erro no console (F12)?
- [ ] O backend registra a requisição? (veja terminal do backend)
- [ ] Há erro de CORS?
- [ ] O arquivo é muito grande (> 20MB)?
- [ ] A API Key do Google Vision está configurada?

## Logs Esperados

### Console do Navegador (F12)
```
🔘 Botão clicado!
🚀 Iniciando upload do arquivo: teste.pdf
📡 Enviando requisição para o backend...
📥 Resposta recebida: 200 OK
✅ Dados extraídos com sucesso: {...}
🏁 Processamento finalizado
```

### Terminal do Backend
```
🔵 Nova requisição recebida - Arquivo: teste.pdf
✅ Arquivo validado: teste.pdf (123456 bytes)
🔄 Iniciando processamento OCR...
✅ Processamento concluído com sucesso!
```

## Possíveis Causas

1. **Cache do Navegador**
   - Solução: Ctrl + Shift + R (hard refresh)

2. **Porta Incorreta**
   - Verificar: `active_port.txt` deve ter `58009`
   - Backend deve estar em: `http://127.0.0.1:58009`

3. **Google Vision API**
   - Verificar: `backend/.env` tem `GOOGLE_VISION_API_KEY`
   - Testar: `curl http://localhost:58009/test`

4. **CORS**
   - Já configurado com `allow_origins=["*"]`
   - Verificar no console se há erro de CORS

5. **React StrictMode**
   - StrictMode pode causar double-render em dev
   - Não afeta produção

## Comandos Úteis

```bash
# Ver logs do backend em tempo real
Get-Content "C:\Users\teste\.cursor\projects\c-Users-teste-Desktop-convenio2-0\terminals\857188.txt" -Wait -Tail 20

# Testar backend
curl http://localhost:58009/test

# Verificar porta ativa
cat active_port.txt

# Reiniciar backend
# (Ctrl+C no terminal e rodar novamente)
python find_port_and_start.py
```

## Próximos Passos

Se o problema persistir, forneça:
1. Screenshot do console (F12)
2. Screenshot do terminal do backend
3. Tipo e tamanho do arquivo testado
4. Comportamento exato (botão trava? erro aparece?)
