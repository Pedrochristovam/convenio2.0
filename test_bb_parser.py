import sys
import os

# Adiciona o diretório atual ao sys.path
sys.path.append(os.getcwd())

from backend.monthly_summary_parser import MonthlySummaryParser

def test_bb():
    parser = MonthlySummaryParser()
    
    # Exemplo clássico de BB (CBI)
    ocr_text = """
    BANCO DO BRASIL - RESUMO DO MÊS
    SALDO ANTERIOR      1.000,00
    APLICACOES            500,00
    RESGATES             200,00
    RENDIMENTO BRUTO      10,00
    IMPOSTO RENDA         1,50
    IOF                   0,50
    RENDIMENTO LIQUIDO     8,00
    SALDO ATUAL         1.308,00
    """
    
    result = parser.parse_resumo(ocr_text, 1)
    
    if result:
        print("✓ Teste BB BEM SUCEDIDO!")
        print(f"Tipo: {result['tipo']}")
        for k, v in result['campos'].items():
            print(f"  {k}: {v}")
    else:
        print("✗ FALHA: BB parser não encontrou o resumo.")

if __name__ == "__main__":
    test_bb()
