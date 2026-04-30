import sys
import traceback

try:
    from backend.main import app
    import uvicorn
    print("Iniciando Uvicorn...")
    uvicorn.run(app, host="0.0.0.0", port=5053)
except Exception as e:
    print(f"ERRO FATAL NA INICIALIZAÇÃO: {e}")
    traceback.print_exc()
    sys.exit(1)
