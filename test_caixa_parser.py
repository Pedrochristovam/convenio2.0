import sys
import os

# Adiciona o diretório atual ao sys.path
sys.path.append(os.getcwd())

from backend.caixa_summary_parser import CaixaSummaryParser

def test_caixa():
    parser = CaixaSummaryParser()
    
    ocr_text = """
    GovConta Caixa
    Investimentos
    :: Informativo Mensal
    Conta Vinculada: 0115/006/00000289-0
    Fundo: 0058 - FIC EXECUTIVO
    Nome: MUNICIPIO DE FORMIGA
    Período: mês: Maio ano: 2016

    Total Aplicação Período:
    Total Resgates Período:
    Rendimento Bruto:
    (-) Imposto de Renda:
    (-) IOF:
    Rendimento Líquido
    Data Mov. Nr. Doc. Histórico Quantidade de Cotas Valor (R$)
    1.120.000,00
    0,00
    4.385,82C
    0,00
    0,00
    4.385,82C
    29/04/2016 - Saldo Anterior 0,00C
    18/05/2016 258435 APLICACAO 77247,69763926 1.120.000,00C
    31/05/2016 - Saldo Final 77247,69763926 1.124.385,82C
    """
    
    result = parser.parse_resumo(ocr_text, 1)
    
    if result:
        print("✓ Teste BEM SUCEDIDO!")
        print(f"Tipo: {result['tipo']}")
        print("Campos extraídos:")
        for k, v in result['campos'].items():
            print(f"  {k}: {v}")
        print(f"Erro Matemático: {result['math_error']}")
        print(f"Debug: {result['math_debug']}")
    else:
        print("✗ FALHA: Nenhum resumo encontrado.")

if __name__ == "__main__":
    test_caixa()
