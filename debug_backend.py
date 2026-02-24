try:
    from backend.main import app
    print("Sucesso: App importado corretamente")
except Exception as e:
    import traceback
    traceback.print_exc()
