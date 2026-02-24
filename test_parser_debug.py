import re

# Simula o parser
date_re = re.compile(r"(\d{2}/\d{2}/\d{4})")
value_re = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2})")

test_lines = [
    "Data Histórico",
    "31/07/2015 SALDO ANTERIOR",
    "Valor Valor IR Prej. Comp.",
    "60.820,83",
    "Valor IOF"
]

print("🧪 Testando parser com linhas do OCR real:\n")

for i, line in enumerate(test_lines):
    print(f"Linha {i}: {line}")
    
    # Testa se tem SALDO ANTERIOR
    if "SALDO ANTERIOR" in line.upper():
        print(f"  ✅ Termo encontrado!")
        
        # Testa se tem data
        dt_match = date_re.search(line)
        if dt_match:
            print(f"  📅 Data encontrada: {dt_match.group(1)}")
        else:
            print(f"  ❌ Data NÃO encontrada na linha")
        
        # Testa se tem valor
        val_match = value_re.search(line)
        if val_match:
            print(f"  💰 Valor encontrado: {val_match.group(1)}")
        else:
            print(f"  ⚠️ Valor NÃO encontrado na linha")
            # Busca nas próximas 5 linhas
            for k in range(i + 1, min(len(test_lines), i + 6)):
                val_match = value_re.search(test_lines[k])
                if val_match:
                    print(f"  💰 Valor encontrado {k-i} linhas abaixo: {val_match.group(1)}")
                    break
    
    print()
