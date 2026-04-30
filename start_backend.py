import uvicorn
import sys
import os

# Adiciona o diretorio atual ao sys.path para evitar problemas de importação
sys.path.append(os.getcwd())

try:
    from backend.main import app
    port = int(os.environ.get("PORT", 5053))
    print(f"App importado com sucesso. Iniciando servidor em 0.0.0.0:{port}...", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="debug")
except Exception as e:
    import traceback
    print("ERRO CRITICAL NA INICIALIZACAO:")
    traceback.print_exc()
    with open("critical_startup_error.log", "w") as f:
        traceback.print_exc(file=f)
