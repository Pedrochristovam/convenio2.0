import requests
try:
    r = requests.get("http://localhost:5053/estatisticas")
    print(r.json())
except Exception as e:
    print(f"ERRO: {e}")
