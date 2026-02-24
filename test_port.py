import http.server
import socketserver

PORT = 9999
Handler = http.server.SimpleHTTPRequestHandler

print(f"Tentando abrir porta {PORT} usando http.server...")
try:
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Servidor HTTP basico rodando na porta {PORT}")
        httpd.serve_forever()
except Exception as e:
    print(f"Falha ao iniciar http.server: {e}")
