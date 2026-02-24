"""
Script de diagnóstico manual para identificar problemas de extração

USO:
1. Faça upload do PDF no sistema
2. Veja qual página tem problemas (ex: página 48)
3. Execute: python diagnostico_manual.py 48
4. O script vai mostrar:
   - O que o OCR leu
   - O que o parser extraiu
   - Onde estão os problemas
"""

import sys
import re

def diagnostico_pagina(numero_pagina):
    """Analisa uma página específica"""
    
    print(f"\n{'='*60}")
    print(f"DIAGNÓSTICO DA PÁGINA {numero_pagina}")
    print(f"{'='*60}\n")
    
    # 1. Lê o OCR
    try:
        with open("raw_ocr_debug.txt", "r", encoding="utf-8") as f:
            pages = f.read().split("[NOVA PAGINA]")
        
        if numero_pagina < 1 or numero_pagina > len(pages):
            print(f"❌ Página {numero_pagina} não existe. Total: {len(pages)} páginas")
            return
        
        page_text = pages[numero_pagina - 1]
        
        print(f"📄 TEXTO OCR DA PÁGINA {numero_pagina}:")
        print("-" * 60)
        print(page_text[:2000])  # Primeiros 2000 caracteres
        print("-" * 60)
        
    except FileNotFoundError:
        print("❌ Arquivo raw_ocr_debug.txt não encontrado. Faça upload primeiro.")
        return
    
    # 2. Verifica se tem "Resumo do mês"
    if "RESUMO" not in page_text.upper() or "MÊS" not in page_text.upper() and "MES" not in page_text.upper():
        print(f"\n⚠️ Página {numero_pagina} NÃO contém 'Resumo do mês'")
        return
    
    print(f"\n✓ Página {numero_pagina} CONTÉM 'Resumo do mês'\n")
    
    # 3. Extrai o bloco de resumo
    match_inicio = re.search(r"RESUMO\s+DO\s+M[EÊ]S", page_text, re.IGNORECASE)
    if not match_inicio:
        print("❌ Não conseguiu localizar início do bloco")
        return
    
    texto_pos_resumo = page_text[match_inicio.start():]
    
    # Encontra o fim
    fim_patterns = [
        r"\n\s*Valor\s+da\s+Cota",
        r"\n\s*Rentabilidade",
        r"\n\s*Data\s+Hist[oó]rico",
        r"\n\s*\d{2}/\d{2}/\d{4}\s+[A-Z]"
    ]
    
    fim_pos = len(texto_pos_resumo)
    for pattern in fim_patterns:
        match_fim = re.search(pattern, texto_pos_resumo, re.IGNORECASE)
        if match_fim and match_fim.start() > 100:
            fim_pos = min(fim_pos, match_fim.start())
    
    bloco_resumo = texto_pos_resumo[:fim_pos]
    
    print("📋 BLOCO DE RESUMO EXTRAÍDO:")
    print("-" * 60)
    print(bloco_resumo)
    print("-" * 60)
    
    # 4. Tenta extrair cada campo
    print(f"\n🔍 TENTANDO EXTRAIR CAMPOS:\n")
    
    campos = {
        "SALDO ANTERIOR": ["SALDO ANTERIOR"],
        "APLICAÇÕES (+)": ["APLICAÇÕES (+)", "APLICACOES (+)", "APLICAÇÕES", "APLICACOES"],
        "RESGATES (-)": ["RESGATES (-)"],
        "RENDIMENTO BRUTO (+)": ["RENDIMENTO BRUTO (+)"],
        "IMPOSTO DE RENDA (-)": ["IMPOSTO DE RENDA (-)", "IMPOSTO RENDA (-)"],
        "IOF (-)": ["IOF (-)"],
        "RENDIMENTO LÍQUIDO": ["RENDIMENTO LÍQUIDO", "RENDIMENTO LIQUIDO"],
        "SALDO ATUAL": ["SALDO ATUAL =", "SALDO ATUAL"]
    }
    
    valor_pattern = re.compile(r'(\d{1,3}(?:[\.\s]\d{3})*,\d{2})')
    
    for campo_nome, termos in campos.items():
        encontrado = False
        for termo in termos:
            if termo in bloco_resumo.upper():
                print(f"✓ '{campo_nome}': termo '{termo}' ENCONTRADO")
                
                # Busca valor após o termo
                pos_termo = bloco_resumo.upper().index(termo)
                texto_apos = bloco_resumo[pos_termo + len(termo):]
                
                # Mostra os próximos 100 caracteres após o termo
                print(f"  Texto após o termo: '{texto_apos[:100]}'")
                
                match = valor_pattern.search(texto_apos)
                if match:
                    print(f"  ✓ Valor encontrado: {match.group(1)}")
                else:
                    print(f"  ❌ NENHUM valor encontrado nos próximos 100 caracteres")
                
                encontrado = True
                break
        
        if not encontrado:
            print(f"❌ '{campo_nome}': TERMO NÃO ENCONTRADO no bloco")
    
    print(f"\n{'='*60}")
    print("DIAGNÓSTICO COMPLETO")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("\n❌ USO: python diagnostico_manual.py <numero_pagina>")
        print("   Exemplo: python diagnostico_manual.py 48\n")
        sys.exit(1)
    
    try:
        numero = int(sys.argv[1])
        diagnostico_pagina(numero)
    except ValueError:
        print("\n❌ Número de página inválido\n")
        sys.exit(1)
