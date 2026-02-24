import socket
import uvicorn
import sys
import os

sys.path.append(os.getcwd())
try:
    from backend.main import app
except ImportError:
    # Caso esteja rodando de dentro da pasta backend
    sys.path.append(os.path.join(os.getcwd(), ".."))
    from backend.main import app

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

port = get_free_port()
print(f"Porta livre encontrada: {port}")
with open("active_port.txt", "w") as f:
    f.write(str(port))
sys.stdout.flush()

try:
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="debug")
except Exception as e:
    print(f"Falha ao iniciar na porta {port}: {e}")
