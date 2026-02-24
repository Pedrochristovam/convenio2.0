from backend.parser_service import DeterministicParser

def test_parser():
    parser = DeterministicParser()
    
    # Caso 1: Sucesso simples
    ocr_text = """
    EXTRATO DE CONV\u00caNIO
    SALDO ANTERIOR 60.820,83
    RENDIMENTO BRUTO (+) 100,00
    SALDO ATUAL 60.920,83
    """
    print("--- Teste 1: Sucesso Simples ---")
    results = parser.parse(ocr_text)
    for res in results:
        if res.valor is not None:
            print(f"Campo: {res.campo} | Valor: {res.valor} | Status: {res.status}")

    # Caso 2: Ambiguide (Regra de Ouro)
    ocr_text_ambiguo = """
    SALDO ATUAL 100,00
    Texto aleat\u00f3rio com SALDO ATUAL 200,00
    """
    print("\n--- Teste 2: Ambiguidade (Dois valores para o mesmo campo) ---")
    results = parser.parse(ocr_text_ambiguo)
    for res in results:
        if res.campo == "SALDO ATUAL":
            print(f"Campo: {res.campo} | Status: {res.status} | Confian\u00e7a: {res.confianca}")

    # Caso 3: Campo ausente (Garantir null, não 0.00)
    print("\n--- Teste 3: Campo Ausente ---")
    results = parser.parse("Texto sem campos conhecidos")
    for res in results:
        if res.campo == "SALDO ANTERIOR":
            print(f"Campo: {res.campo} | Valor: {res.valor} | Status: {res.status}")

if __name__ == "__main__":
    test_parser()
