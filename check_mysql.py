import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

def check_db():
    try:
        conn = pymysql.connect(
            host=os.getenv('MYSQL_HOST', 'localhost'),
            user=os.getenv('MYSQL_USER', 'root'),
            password=os.getenv('MYSQL_PASSWORD'),
            database=os.getenv('MYSQL_DATABASE', 'convenio2'),
            port=int(os.getenv('MYSQL_PORT', 3306)),
            cursorclass=pymysql.cursors.DictCursor
        )
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) as count FROM resumos_mensais")
        resumos = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM movimentacoes_cc")
        ccs = cursor.fetchone()['count']
        
        cursor.execute("SELECT DISTINCT arquivo_nome FROM resumos_mensais")
        arquivos = [r['arquivo_nome'] for r in cursor.fetchall()]
        
        print(f"Resumos: {resumos}")
        print(f"CCs: {ccs}")
        print(f"Arquivos: {arquivos}")
        
        conn.close()
    except Exception as e:
        print(f"ERRO: {e}")

if __name__ == "__main__":
    check_db()
