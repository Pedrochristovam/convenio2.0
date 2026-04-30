import uvicorn
import sys
import os

# Adiciona o diretorio atual ao sys.path para evitar problemas de importação
sys.path.append(os.getcwd())

try:
    from backend.main import app
    print("App importado com sucesso. Iniciando servidor na porta 5053...", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=5053, log_level="debug")
except Exception as e:
    import traceback
    print("ERRO CRITICAL NA INICIALIZACAO:")
    traceback.print_exc()
    with open("critical_startup_error.log", "w") as f:
        traceback.print_exc(file=f)
