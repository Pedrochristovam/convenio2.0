import re

text = """
31/07/2015 SALDO ANTERIOR
Valor Valor IR Prej. Comp.
60.820,83
31/10/2016 13 42 22
31/05/2016 SALDO ANTERIOR 64.441,34
20/06/2016 RESGATE 801,18
"""

# Regex original
line_re = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+(.*?)\s+(\d{1,3}(?:\.\d{3})*,\d{2})")

print("Testando Regex...")
lines = text.split('\n')
for line in lines:
    line = line.strip()
    match = line_re.search(line)
    if match:
        print(f"MATCH: {match.groups()}")
    else:
        print(f"NO MATCH: {line}")
