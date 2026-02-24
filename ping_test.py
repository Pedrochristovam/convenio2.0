import time
import sys

print("Iniciando teste de persistencia...")
sys.stdout.flush()

try:
    for i in range(10):
        print(f"Ping {i}...")
        sys.stdout.flush()
        time.sleep(1)
except Exception as e:
    print(f"Erro: {e}")
