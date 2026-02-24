"""
Script de Debug - Análise Detalhada de Uma Página Específica
Mostra EXATAMENTE o que o OCR leu e o que o parser extraiu
"""

# Leia o arquivo raw_ocr_debug.txt e cole aqui UMA página específica que está com problema
# Exemplo: A página 2 que deveria ter SALDO ATUAL = 61.290,01

ocr_text = """
Cole aqui o texto da página problemática
"""

import re

print("=" * 80)
print("ANÁLISE DETALHADA DO OCR")
print("=" * 80)

# Divide em linhas
linhas = ocr_text.split('\n')

print(f"\nTotal de linhas: {len(linhas)}")
print("\nPrimeiras 50 linhas com números:")
print("-" * 80)

for i, linha in enumerate(linhas[:100]):
    # Mostra linhas que contenham números ou termos chave
    if any(termo in linha.upper() for termo in ["RESUMO", "SALDO", "APLICAÇÕES", "RESGATES", "RENDIMENTO", "IMPOSTO", "IOF"]):
        print(f"Linha {i:3d}: {linha}")
    elif re.search(r'\d{1,3}[,\.]\d{2}', linha):
        print(f"Linha {i:3d}: {linha}")

print("\n" + "=" * 80)
print("PROCURANDO CAMPOS ESPECÍFICOS")
print("=" * 80)

# Procura cada campo
campos = [
    ("SALDO ANTERIOR", r'(\d{1,3}(?:[\.\s]\d{3})*,\d{2})'),
    ("APLICAÇÕES", r'(\d{1,3}(?:[\.\s]\d{3})*,\d{2})'),
    ("RESGATES", r'(\d{1,3}(?:[\.\s]\d{3})*,\d{2})'),
    ("RENDIMENTO BRUTO", r'(\d{1,3}(?:[\.\s]\d{3})*,\d{2})'),
    ("IMPOSTO DE RENDA", r'(\d{1,3}(?:[\.\s]\d{3})*,\d{2})'),
    ("IOF", r'(\d{1,3}(?:[\.\s]\d{3})*,\d{2})'),
    ("RENDIMENTO LÍQUIDO", r'(\d{1,3}(?:[\.\s]\d{3})*,\d{2})'),
    ("SALDO ATUAL", r'(\d{1,3}(?:[\.\s]\d{3})*,\d{2})')
]

for campo, pattern in campos:
    print(f"\n🔍 Procurando: {campo}")
    print("-" * 40)
    
    encontrado = False
    for i, linha in enumerate(linhas):
        if campo in linha.upper():
            print(f"  Linha {i}: {linha}")
            
            # Procura valor na mesma linha
            match = re.search(pattern, linha)
            if match:
                print(f"  ✓ VALOR NA MESMA LINHA: {match.group(1)}")
                encontrado = True
            else:
                # Procura nas próximas 3 linhas
                for j in range(i+1, min(i+4, len(linhas))):
                    match = re.search(pattern, linhas[j])
                    if match:
                        print(f"  ✓ VALOR NA LINHA {j}: {match.group(1)} → {linhas[j]}")
                        encontrado = True
                        break
            
            if not encontrado:
                print(f"  ❌ VALOR NÃO ENCONTRADO nas próximas linhas")
                print(f"     Próximas 3 linhas:")
                for j in range(i+1, min(i+4, len(linhas))):
                    print(f"       Linha {j}: {linhas[j]}")

print("\n" + "=" * 80)
print("INSTRUÇÕES")
print("=" * 80)
print("""
1. Abra o arquivo: raw_ocr_debug.txt
2. Encontre a página que está com problema
3. Copie TODO o texto dessa página (desde [NOVA PAGINA] até o próximo [NOVA PAGINA])
4. Cole no início deste script na variável ocr_text
5. Execute: python debug_ocr_page.py
6. Me envie o resultado completo
""")
