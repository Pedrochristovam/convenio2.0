import pymysql
import pymysql.cursors
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging
import json
import os
import re
from dotenv import load_dotenv
# Carrega .env do diretório raiz do projeto (um nível acima de /backend)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_PATH, override=True)

logger = logging.getLogger(__name__)

# Log de auditoria de configuração (seguro)
db_host = os.getenv("MYSQL_HOST", "localhost")
db_user = os.getenv("MYSQL_USER", "root")
db_name = os.getenv("MYSQL_DATABASE", "convenio2")
logger.info(f"DB CONFIG: Host={db_host}, User={db_user}, DB={db_name} (Loaded from {ENV_PATH})")

# Com DATABASE_URL (PostgreSQL do Render) o mesmo SQL escrito para MySQL é traduzido em _CursorPg
DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()

# Chave única usada pelos "ON DUPLICATE KEY UPDATE" de cada tabela (no PostgreSQL vira ON CONFLICT)
CHAVES_UNICAS = {
    "ocr_paginas": "arquivo_nome, data_processamento, pagina",
    "pasta_arquivos": "arquivo_nome",
}


def _tipo_pg(definicao: str) -> str:
    for de, para in (
        (r"INT AUTO_INCREMENT PRIMARY KEY", "SERIAL PRIMARY KEY"),
        (r"\b(?:MEDIUM|LONG)TEXT\b", "TEXT"),
        (r"\bTINYINT\(1\)", "SMALLINT"),
        (r"\bJSON\b", "TEXT"),
        (r"\s+ON UPDATE CURRENT_TIMESTAMP", ""),
    ):
        definicao = re.sub(de, para, definicao)
    return definicao


def _ddl_pg(sql: str) -> List[str]:
    """CREATE TABLE do MySQL -> comandos PostgreSQL (índices à parte e gatilho para updated_at)."""
    tabela = re.search(r"CREATE TABLE IF NOT EXISTS (\w+)", sql).group(1)
    corpo = sql[sql.index("(") + 1 : sql.rindex(")")]
    colunas, extras = [], []
    for linha in corpo.splitlines():
        linha = linha.strip().rstrip(",")
        if not linha:
            continue
        indice = re.match(r"INDEX (\w+) \((.+)\)$", linha)
        unica = re.match(r"UNIQUE KEY (\w+) \((.+)\)$", linha)
        if indice:
            extras.append(f"CREATE INDEX IF NOT EXISTS {indice[1]} ON {tabela} ({indice[2]})")
        elif unica:
            colunas.append(f"CONSTRAINT {unica[1]} UNIQUE ({unica[2]})")
        else:
            colunas.append(_tipo_pg(linha))
    comandos = [f"CREATE TABLE IF NOT EXISTS {tabela} ({', '.join(colunas)})"] + extras
    if "ON UPDATE CURRENT_TIMESTAMP" in sql:
        comandos += [
            "CREATE OR REPLACE FUNCTION atualizar_updated_at() RETURNS trigger AS $$ "
            "BEGIN NEW.updated_at = CURRENT_TIMESTAMP; RETURN NEW; END $$ LANGUAGE plpgsql",
            f"DROP TRIGGER IF EXISTS trg_{tabela}_updated_at ON {tabela}",
            f"CREATE TRIGGER trg_{tabela}_updated_at BEFORE UPDATE ON {tabela} "
            "FOR EACH ROW EXECUTE FUNCTION atualizar_updated_at()",
        ]
    return comandos


def _dml_pg(sql: str) -> str:
    duplicado = re.search(r"ON DUPLICATE KEY UPDATE", sql)
    if duplicado:
        tabela = re.search(r"INSERT INTO (\w+)", sql).group(1)
        sql = sql.replace(duplicado.group(0), f"ON CONFLICT ({CHAVES_UNICAS[tabela]}) DO UPDATE SET")
        sql = re.sub(r"VALUES\((\w+)\)", r"EXCLUDED.\1", sql)
    return sql


class _CursorPg:
    """Cursor psycopg2 com a interface usada aqui (dicts, lastrowid) e o SQL do MySQL traduzido."""

    def __init__(self, cursor):
        self._cursor = cursor
        self.lastrowid = None

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def execute(self, sql: str, params=None):
        if sql.lstrip().startswith("CREATE TABLE"):
            for comando in _ddl_pg(sql):
                self._cursor.execute(comando)
            return
        sql = _dml_pg(sql)
        insercao = sql.lstrip().upper().startswith("INSERT")
        if insercao:
            sql = sql.rstrip().rstrip(";") + " RETURNING id"
        if params is not None:
            # PostgreSQL recusa o caractere NUL em texto (aparece em OCR de PDFs nativos)
            params = tuple(p.replace("\x00", "") if isinstance(p, str) else p for p in params)
        self._cursor.execute(sql, params)
        self.lastrowid = self._cursor.fetchone()["id"] if insercao else None

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class _ConexaoPg:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return _CursorPg(self._conn.cursor())

    def close(self):
        self._conn.close()


class ExtractionDatabase:
    """
    Banco de dados MySQL para armazenar todas as extrações
    Substitui o SQLite para maior robustez e escalabilidade
    """
    
    def __init__(self):
        self.pg = bool(DATABASE_URL)
        self.host = os.getenv("MYSQL_HOST", "localhost")
        try:
            port_str = os.getenv("MYSQL_PORT", "3306").strip()
            self.port = int(port_str) if port_str else 3306
        except Exception:
            self.port = 3306
        self.user = os.getenv("MYSQL_USER", "root")
        self.password = os.getenv("MYSQL_PASSWORD", "")
        self.database = os.getenv("MYSQL_DATABASE", "convenio2")
        # MySQL gerenciado (Aiven, Railway...) exige TLS; com o certificado da CA a identidade do servidor é verificada
        ca = (os.getenv("MYSQL_SSL_CA") or "").strip()
        if ca:
            self.ssl = {"ca": ca}
        elif (os.getenv("MYSQL_SSL") or "").strip() == "1":
            self.ssl = {"check_hostname": False}
        else:
            self.ssl = None
        self._init_database()
    
    def _get_connection(self):
        if self.pg:
            try:
                import psycopg2
                import psycopg2.extras

                conn = psycopg2.connect(
                    DATABASE_URL,
                    cursor_factory=psycopg2.extras.RealDictCursor,
                    connect_timeout=10,
                    # Horário de Brasília em formato POSIX: não depende da base de fusos do servidor
                    options="-c timezone=<-03>+03",
                )
                conn.autocommit = True
                return _ConexaoPg(conn)
            except Exception as e:
                logger.error("Falha ao conectar PostgreSQL: %s", e)
                return None
        try:
            return pymysql.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                port=self.port,
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
                connect_timeout=5,
                charset="utf8mb4",
                ssl=self.ssl,
            )
        except Exception as e:
            logger.error("Falha ao conectar MySQL: %s", e)
            return None

    def require_connection(self):
        """Obtém conexão ou levanta erro explícito (produção)."""
        conn = self._get_connection()
        if not conn:
            if self.pg:
                raise RuntimeError("PostgreSQL indisponível. Verifique DATABASE_URL e se o banco está ativo.")
            raise RuntimeError(
                f"MySQL indisponível ({self.host}:{self.port}/{self.database}). "
                "Verifique MYSQL_* no .env e se o serviço está rodando."
            )
        return conn

    def _ensure_column(self, cursor, table: str, column: str, definition: str):
        if self.pg:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {_tipo_pg(definition)}")
            return
        cursor.execute(
            """
            SELECT COUNT(*) AS c FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
            """,
            (self.database, table, column),
        )
        row = cursor.fetchone()
        if row and int(row["c"]) == 0:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            logger.info("Coluna adicionada: %s.%s", table, column)

    def _init_database(self):
        """Inicializa as tabelas se não existirem (no MySQL)"""
        try:
            conn = self._get_connection()
            if not conn:
                logger.error("❌ MySQL offline no init — tabelas não verificadas")
                return
            cursor = conn.cursor()
            
            # Tabela principal de extrações
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS extracoes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    arquivo_nome VARCHAR(255) NOT NULL,
                    data_processamento VARCHAR(100) NOT NULL,
                    campo VARCHAR(100) NOT NULL,
                    valor DECIMAL(15, 2) NOT NULL,
                    data_extracao VARCHAR(100) NOT NULL,
                    pagina INT NOT NULL,
                    linha_ocr TEXT,
                    confianca VARCHAR(50),
                    status VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_arquivo (arquivo_nome),
                    INDEX idx_data_processamento (data_processamento),
                    INDEX idx_campo (campo)
                ) ENGINE=InnoDB
            """)
            
            # Tabela para resumos mensais
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS resumos_mensais (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    arquivo_nome VARCHAR(255) NOT NULL,
                    data_processamento VARCHAR(100) NOT NULL,
                    pagina INT NOT NULL,
                    saldo_anterior DECIMAL(15, 2),
                    aplicacoes DECIMAL(15, 2),
                    resgates DECIMAL(15, 2),
                    rendimento_bruto DECIMAL(15, 2),
                    imposto_renda DECIMAL(15, 2),
                    iof DECIMAL(15, 2),
                    rendimento_liquido DECIMAL(15, 2),
                    saldo_atual DECIMAL(15, 2),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_resumo (arquivo_nome, data_processamento, pagina),
                    INDEX idx_resumos_arquivo (arquivo_nome)
                ) ENGINE=InnoDB
            """)
            
            # Tabela de movimentações de conta corrente
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS movimentacoes_cc (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    arquivo_nome VARCHAR(255) NOT NULL,
                    data_processamento VARCHAR(100) NOT NULL,
                    pagina INT NOT NULL,
                    agencia VARCHAR(50),
                    conta VARCHAR(50),
                    titular VARCHAR(255),
                    periodo VARCHAR(100),
                    data_balancete VARCHAR(50),
                    data_movimento VARCHAR(50),
                    historico TEXT,
                    valor DECIMAL(15, 2),
                    valor_tipo CHAR(1),
                    saldo DECIMAL(15, 2),
                    saldo_tipo CHAR(1),
                    documento VARCHAR(100),
                    raw_line TEXT,
                    editado_manualmente TINYINT(1) DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_cc_arquivo (arquivo_nome)
                ) ENGINE=InnoDB
            """)

            # OCR por página (fonte única para reprocessamento)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ocr_paginas (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    arquivo_nome VARCHAR(255) NOT NULL,
                    data_processamento VARCHAR(100) NOT NULL,
                    pagina INT NOT NULL,
                    engine VARCHAR(50) NOT NULL,
                    texto MEDIUMTEXT,
                    char_count INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_ocr (arquivo_nome, data_processamento, pagina),
                    INDEX idx_ocr_arquivo (arquivo_nome)
                ) ENGINE=InnoDB
            """)

            # Metadados do job de processamento
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processamento_jobs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    arquivo_nome VARCHAR(255) NOT NULL,
                    data_processamento VARCHAR(100) NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    total_paginas INT DEFAULT 0,
                    total_resumos INT DEFAULT 0,
                    total_cc INT DEFAULT 0,
                    mensagem TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_job_arquivo (arquivo_nome),
                    INDEX idx_job_status (status)
                ) ENGINE=InnoDB
            """)

            # Dossiê de Análise Documental (vários arquivos de um mesmo convênio)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dossies (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nome VARCHAR(255) NOT NULL,
                    arquivos JSON NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    progresso INT DEFAULT 0,
                    mensagem TEXT,
                    resultado LONGTEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_dossie_status (status)
                ) ENGINE=InnoDB
            """)

            # Pasta do convênio: agrupa os volumes (arquivos) de um mesmo processo
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pastas (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nome VARCHAR(255) NOT NULL,
                    numero_convenio VARCHAR(100) NULL,
                    convenente VARCHAR(255) NULL,
                    observacao TEXT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB
            """)

            # Um arquivo pertence a uma única pasta; "ordem" é a ordem do processo (volume 1, 2, ...)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pasta_arquivos (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    pasta_id INT NOT NULL,
                    arquivo_nome VARCHAR(255) NOT NULL,
                    ordem INT NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_pasta_arquivo (arquivo_nome),
                    INDEX idx_pasta (pasta_id)
                ) ENGINE=InnoDB
            """)

            self._ensure_column(cursor, "resumos_mensais", "fonte_parser", "VARCHAR(50) NULL")
            self._ensure_column(cursor, "resumos_mensais", "math_ok", "TINYINT(1) NULL")
            self._ensure_column(cursor, "dossies", "pasta_id", "INT NULL")

            conn.close()
            logger.info("✅ %s conectado e tabelas verificadas.", "PostgreSQL" if self.pg else "MySQL")
        except Exception as e:
            logger.error(f"❌ ERRO CRÍTICO NA CONEXÃO MYSQL: {e}")
            # Não levantamos erro aqui para não travar o backend no init, 
            # mas as chamadas futuras falharão com logs claros.
    
    def salvar_extracao(
        self,
        arquivo_nome: str,
        data_processamento: str,
        campo: str,
        valor: float,
        data_extracao: str,
        pagina: int,
        linha_ocr: str = "",
        confianca: str = "ALTA",
        status: str = "SUCESSO"
    ) -> int:
        """Salva uma extração no banco"""
        conn = self._get_connection()
        if not conn: return 0
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO extracoes 
            (arquivo_nome, data_processamento, campo, valor, data_extracao, 
             pagina, linha_ocr, confianca, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            arquivo_nome,
            data_processamento,
            campo,
            valor,
            data_extracao,
            pagina,
            linha_ocr,
            confianca,
            status
        ))
        
        extraction_id = cursor.lastrowid
        conn.close()
        
        return extraction_id
    
    def salvar_lote(
        self,
        arquivo_nome: str,
        resultados_por_pagina: Dict[int, List[Any]]
    ) -> int:
        """
        Salva um lote completo de extrações
        ATENÇÃO: Remove extrações antigas do mesmo arquivo antes de salvar
        """
        data_processamento = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_salvos = 0
        
        conn = self._get_connection()
        if not conn: return 0
        cursor = conn.cursor()
        
        # REMOVE extrações antigas deste arquivo (evita duplicatas)
        cursor.execute("DELETE FROM extracoes WHERE arquivo_nome = %s", (arquivo_nome,))
        linhas_removidas = cursor.rowcount
        if linhas_removidas > 0:
            logger.info(f"Removidas {linhas_removidas} extracoes antigas de {arquivo_nome}")
        
        for pagina, resultados in resultados_por_pagina.items():
            for res in resultados:
                cursor.execute("""
                    INSERT INTO extracoes 
                    (arquivo_nome, data_processamento, campo, valor, data_extracao, 
                     pagina, linha_ocr, confianca, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    arquivo_nome,
                    data_processamento,
                    res.campo,
                    res.valor,
                    res.data_extracao,
                    res.pagina,
                    res.linha_ocr,
                    res.confianca,
                    res.status
                ))
                total_salvos += 1
        
        conn.close()
        
        logger.info(f"Salvos {total_salvos} registros no banco para {arquivo_nome}")
        return total_salvos
    
    def listar_ultima_extracao(self, arquivo_nome: str) -> List[Dict[str, Any]]:
        """Lista a última extração de um arquivo específico"""
        conn = self._get_connection()
        if not conn: return []
        cursor = conn.cursor()
        
        # Busca a última data de processamento deste arquivo
        cursor.execute("""
            SELECT DISTINCT data_processamento 
            FROM extracoes 
            WHERE arquivo_nome = %s
            ORDER BY data_processamento DESC
            LIMIT 1
        """, (arquivo_nome,))
        
        result = cursor.fetchone()
        if not result:
            conn.close()
            return []
        
        ultima_data = result['data_processamento']
        
        # Busca todos os registros desta extração
        cursor.execute("""
            SELECT id, campo, valor, data_extracao, pagina, linha_ocr, confianca, status
            FROM extracoes
            WHERE arquivo_nome = %s AND data_processamento = %s
            ORDER BY pagina, id
        """, (arquivo_nome, ultima_data))
        
        rows = cursor.fetchall()
        conn.close()
        
        return rows
    
    def listar_todas_extracoes(self, limite: int = 100) -> List[Dict[str, Any]]:
        """Lista todas as extrações do banco"""
        conn = self._get_connection()
        if not conn: return []
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, arquivo_nome, data_processamento, campo, valor, 
                   data_extracao, pagina, linha_ocr, confianca, status
            FROM extracoes
            ORDER BY created_at DESC
            LIMIT %s
        """, (limite,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return rows
    
    def estatisticas(self) -> Dict[str, Any]:
        """Retorna estatísticas do banco com tratamento de erro"""
        try:
            conn = self._get_connection()
            if not conn: return {}
            cursor = conn.cursor()
            
            # Total de Resumos Mensais (Nova Tabela)
            cursor.execute("SELECT COUNT(*) as count FROM resumos_mensais")
            resumos = cursor.fetchone()['count'] if cursor.rowcount > 0 else 0
            
            # Total de Lançamentos CC (Nova Tabela)
            cursor.execute("SELECT COUNT(*) as count FROM movimentacoes_cc")
            ccs = cursor.fetchone()['count'] if cursor.rowcount > 0 else 0
            
            # Total de Arquivos Únicos
            cursor.execute("""
                SELECT COUNT(DISTINCT arquivo_nome) as count 
                FROM (
                    SELECT arquivo_nome FROM resumos_mensais
                    UNION
                    SELECT arquivo_nome FROM movimentacoes_cc
                ) as arquivos
            """)
            result_arquivos = cursor.fetchone()
            total_arquivos = result_arquivos['count'] if result_arquivos else 0
            
            conn.close()
            
            return {
                "total_registros": resumos + ccs,
                "total_arquivos": total_arquivos,
                "resumos": resumos,
                "ccs": ccs,
                "distribuicao_campos": {} # Opcional agora
            }
        except Exception as e:
            logger.error(f"Erro ao buscar estatísticas: {e}")
            return {
                "total_registros": 0,
                "total_arquivos": 0,
                "distribuicao_campos": {}
            }
    
    def salvar_resumos_mensais(
        self,
        arquivo_nome: str,
        resumos: Dict[int, Dict[str, Any]]
    ) -> int:
        """
        Salva resumos mensais no banco
        """
        data_processamento = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_salvos = 0
        
        conn = self._get_connection()
        if not conn: return 0
        cursor = conn.cursor()
        
        # REMOVE resumos antigos deste arquivo (evita duplicatas)
        cursor.execute("DELETE FROM resumos_mensais WHERE arquivo_nome = %s", (arquivo_nome,))
        linhas_removidas = cursor.rowcount
        if linhas_removidas > 0:
            logger.info(f"Removidos {linhas_removidas} resumos antigos de {arquivo_nome}")
        
        for pagina, resumo_data in resumos.items():
            campos = resumo_data.get("campos", {})
            
            cursor.execute("""
                INSERT INTO resumos_mensais 
                (arquivo_nome, data_processamento, pagina,
                 saldo_anterior, aplicacoes, resgates, rendimento_bruto,
                 imposto_renda, iof, rendimento_liquido, saldo_atual)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                arquivo_nome,
                data_processamento,
                pagina,
                campos.get("saldo_anterior"),
                campos.get("aplicacoes"),
                campos.get("resgates"),
                campos.get("rendimento_bruto"),
                campos.get("imposto_renda"),
                campos.get("iof"),
                campos.get("rendimento_liquido"),
                campos.get("saldo_atual")
            ))
            total_salvos += 1
        
        conn.close()
        
        logger.info(f"Salvos {total_salvos} resumos mensais no banco para {arquivo_nome}")
        return total_salvos
    
    def listar_resumos_mensais(self, arquivo_nome: str) -> Dict[int, Dict[str, Any]]:
        """
        Lista os resumos mensais da última extração de um arquivo
        """
        conn = self._get_connection()
        if not conn: return {}
        cursor = conn.cursor()
        
        # Busca a última data de processamento deste arquivo
        cursor.execute("""
            SELECT DISTINCT data_processamento 
            FROM resumos_mensais 
            WHERE arquivo_nome = %s
            ORDER BY data_processamento DESC
            LIMIT 1
        """, (arquivo_nome,))
        
        result = cursor.fetchone()
        if not result:
            logger.warning(f"Nenhum resumo encontrado no banco para o arquivo: {arquivo_nome}")
            conn.close()
            return {}
        
        ultima_data = result['data_processamento']
        logger.info(f"Buscando resumos para {arquivo_nome} da data {ultima_data}")
        
        # Busca todos os resumos desta extração
        cursor.execute("""
            SELECT pagina, saldo_anterior, aplicacoes, resgates, rendimento_bruto,
                   imposto_renda, iof, rendimento_liquido, saldo_atual
            FROM resumos_mensais
            WHERE arquivo_nome = %s AND data_processamento = %s
            ORDER BY pagina
        """, (arquivo_nome, ultima_data))
        
        rows = cursor.fetchall()
        conn.close()
        
        def to_f(v):
            if v is None: return None
            try: return float(v)
            except: return None

        resumos = {}
        for row in rows:
            p = row['pagina']
            resumos[p] = {
                "tipo": "RESUMO_MENSAL",
                "pagina": p,
                "campos": {
                    "saldo_anterior": to_f(row['saldo_anterior']),
                    "aplicacoes": to_f(row['aplicacoes']),
                    "resgates": to_f(row['resgates']),
                    "rendimento_bruto": to_f(row['rendimento_bruto']),
                    "imposto_renda": to_f(row['imposto_renda']),
                    "iof": to_f(row['iof']),
                    "rendimento_liquido": to_f(row['rendimento_liquido']),
                    "saldo_atual": to_f(row['saldo_atual'])
                }
            }
        
        logger.info(f"Retornando {len(resumos)} resumos para o frontend.")
        return resumos
    
    def limpar_banco(self):
        """
        CUIDADO: Remove TODOS os dados do banco
        """
        conn = self.require_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM extracoes")
        extracoes_removidas = cursor.rowcount
        
        cursor.execute("DELETE FROM resumos_mensais")
        resumos_removidos = cursor.rowcount
        
        cursor.execute("DELETE FROM movimentacoes_cc")
        cc_removidas = cursor.rowcount

        cursor.execute("DELETE FROM ocr_paginas")
        ocr_removidas = cursor.rowcount

        cursor.execute("DELETE FROM processamento_jobs")
        jobs_removidos = cursor.rowcount

        cursor.execute("DELETE FROM dossies")
        dossies_removidos = cursor.rowcount

        cursor.execute("DELETE FROM pasta_arquivos")
        cursor.execute("DELETE FROM pastas")
        
        conn.close()
        
        logger.warning(
            "BANCO LIMPO: %s extracoes + %s resumos + %s cc + %s ocr + %s jobs + %s dossies",
            extracoes_removidas, resumos_removidos, cc_removidas, ocr_removidas, jobs_removidos, dossies_removidos,
        )
        return {
            "extracoes": extracoes_removidas,
            "resumos": resumos_removidos,
            "cc": cc_removidas,
            "ocr": ocr_removidas,
            "jobs": jobs_removidos,
            "dossies": dossies_removidos,
        }
    
    def limpar_arquivo(self, arquivo_nome: str):
        """
        Remove apenas os dados de um arquivo específico
        """
        conn = self.require_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM extracoes WHERE arquivo_nome = %s", (arquivo_nome,))
        extracoes_removidas = cursor.rowcount
        
        cursor.execute("DELETE FROM resumos_mensais WHERE arquivo_nome = %s", (arquivo_nome,))
        resumos_removidos = cursor.rowcount
        
        cursor.execute("DELETE FROM movimentacoes_cc WHERE arquivo_nome = %s", (arquivo_nome,))
        cc_removidos = cursor.rowcount

        cursor.execute("DELETE FROM ocr_paginas WHERE arquivo_nome = %s", (arquivo_nome,))
        ocr_removidos = cursor.rowcount
        
        conn.close()
        
        if extracoes_removidas or resumos_removidos or cc_removidos or ocr_removidos:
            logger.info(
                "Removidos dados antigos para '%s' (resumos=%s cc=%s ocr=%s)",
                arquivo_nome, resumos_removidos, cc_removidos, ocr_removidos,
            )
    
    def salvar_resumo_individual(
        self,
        arquivo_nome: str,
        pagina: int,
        campos: Dict[str, Optional[float]],
        data_processamento: Optional[str] = None,
        fonte_parser: Optional[str] = None,
        math_ok: Optional[bool] = None,
    ) -> int:
        """
        Salva UM resumo mensal IMEDIATAMENTE no banco
        """
        if data_processamento is None:
            data_processamento = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        conn = self.require_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO resumos_mensais 
            (arquivo_nome, data_processamento, pagina,
             saldo_anterior, aplicacoes, resgates, rendimento_bruto,
             imposto_renda, iof, rendimento_liquido, saldo_atual,
             fonte_parser, math_ok)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            arquivo_nome,
            data_processamento,
            pagina,
            campos.get("saldo_anterior"),
            campos.get("aplicacoes"),
            campos.get("resgates"),
            campos.get("rendimento_bruto"),
            campos.get("imposto_renda"),
            campos.get("iof"),
            campos.get("rendimento_liquido"),
            campos.get("saldo_atual"),
            fonte_parser,
            None if math_ok is None else (1 if math_ok else 0),
        ))
        
        resumo_id = cursor.lastrowid
        conn.close()
        if not resumo_id:
            raise RuntimeError(f"Falha ao gravar resumo página {pagina} de {arquivo_nome}")
        return resumo_id

    # ─────────────────────────────────────────────────────────────────────────
    # CONTA CORRENTE
    # ─────────────────────────────────────────────────────────────────────────

    def salvar_movimentacao_cc(
        self,
        arquivo_nome: str,
        data_processamento: str,
        pagina: int,
        header: Dict[str, str],
        transacao: Dict[str, Any],
    ) -> int:
        """Salva uma única linha de lançamento de conta corrente."""
        conn = self.require_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO movimentacoes_cc
            (arquivo_nome, data_processamento, pagina,
             agencia, conta, titular, periodo,
             data_balancete, data_movimento, historico,
             valor, valor_tipo, saldo, saldo_tipo, documento, raw_line)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            arquivo_nome,
            data_processamento,
            pagina,
            header.get("agencia", ""),
            header.get("conta", ""),
            header.get("titular", ""),
            header.get("periodo", ""),
            transacao.get("data_balancete", ""),
            transacao.get("data_movimento", ""),
            transacao.get("historico", ""),
            transacao.get("valor"),
            transacao.get("valor_tipo", "C"),
            transacao.get("saldo"),
            transacao.get("saldo_tipo", "C"),
            transacao.get("documento", ""),
            transacao.get("raw_line", ""),
        ))
        row_id = cursor.lastrowid
        conn.close()
        if not row_id:
            raise RuntimeError(f"Falha ao gravar movimentação CC página {pagina} de {arquivo_nome}")
        return row_id

    def listar_movimentacoes_cc(self, arquivo_nome: str) -> List[Dict[str, Any]]:
        """Retorna todas as movimentações CC de um arquivo, ordenadas por id."""
        conn = self._get_connection()
        if not conn: return []
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM movimentacoes_cc
            WHERE arquivo_nome = %s
            ORDER BY pagina, id
        """, (arquivo_nome,))
        rows = cursor.fetchall()
        conn.close()
        
        # Converte campos Decimal para float para evitar erro de serialização JSON
        for row in rows:
            if row.get('valor') is not None:
                row['valor'] = float(row['valor'])
            if row.get('saldo') is not None:
                row['saldo'] = float(row['saldo'])
                
        return rows

    def atualizar_campo_cc(self, row_id: int, campo: str, novo_valor: Any) -> bool:
        """Atualiza um campo editável de uma linha CC e marca como editado manualmente."""
        CAMPOS_EDITAVEIS = {
            "data_balancete", "data_movimento", "historico",
            "valor", "saldo", "valor_tipo", "saldo_tipo",
        }
        if campo not in CAMPOS_EDITAVEIS:
            return False
        conn = self._get_connection()
        if not conn: return False
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE movimentacoes_cc SET {campo} = %s, editado_manualmente = 1 WHERE id = %s",
            (novo_valor, row_id),
        )
        atualizado = cursor.rowcount > 0
        conn.close()
        return atualizado

    def atualizar_campo_resumo(self, arquivo_nome: str, pagina: int, campo: str, novo_valor: float) -> bool:
        """Atualiza um campo numérico de um resumo mensal (edição manual)."""
        CAMPOS_EDITAVEIS = {
            "saldo_anterior", "aplicacoes", "resgates",
            "rendimento_bruto", "imposto_renda", "iof",
            "rendimento_liquido", "saldo_atual",
        }
        if campo not in CAMPOS_EDITAVEIS:
            return False
        conn = self._get_connection()
        if not conn: return False
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE resumos_mensais SET {campo} = %s WHERE arquivo_nome = %s AND pagina = %s",
            (novo_valor, arquivo_nome, pagina),
        )
        atualizado = cursor.rowcount > 0
        conn.close()
        return atualizado

    def limpar_cc_arquivo(self, arquivo_nome: str):
        """Remove todas as movimentações CC de um arquivo antes de reprocessar."""
        conn = self.require_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM movimentacoes_cc WHERE arquivo_nome = %s", (arquivo_nome,))
        conn.close()

    def salvar_ocr_pagina(
        self,
        arquivo_nome: str,
        data_processamento: str,
        pagina: int,
        engine: str,
        texto: str,
    ) -> int:
        """Persiste o texto OCR de uma página (permite reprocessar sem novo OCR)."""
        conn = self.require_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ocr_paginas
            (arquivo_nome, data_processamento, pagina, engine, texto, char_count)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                engine = VALUES(engine),
                texto = VALUES(texto),
                char_count = VALUES(char_count)
            """,
            (arquivo_nome, data_processamento, pagina, engine, texto or "", len(texto or "")),
        )
        row_id = cursor.lastrowid
        conn.close()
        return row_id

    def _ultimo_processamento_ocr(self, cursor, arquivo_nome: str) -> Optional[str]:
        cursor.execute(
            "SELECT MAX(data_processamento) AS dp FROM ocr_paginas WHERE arquivo_nome = %s",
            (arquivo_nome,),
        )
        row = cursor.fetchone()
        return row["dp"] if row else None

    def listar_ocr_paginas(self, arquivo_nome: str) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        if not conn:
            return []
        cursor = conn.cursor()
        ultimo = self._ultimo_processamento_ocr(cursor, arquivo_nome)
        cursor.execute(
            """
            SELECT pagina, engine, char_count, LEFT(texto, 500) AS preview
            FROM ocr_paginas
            WHERE arquivo_nome = %s AND data_processamento = %s
            ORDER BY pagina
            """,
            (arquivo_nome, ultimo),
        )
        rows = cursor.fetchall()
        conn.close()
        return rows

    def obter_ocr_texto(self, arquivo_nome: str) -> List[Dict[str, Any]]:
        """Texto OCR completo do processamento mais recente do arquivo."""
        conn = self.require_connection()
        cursor = conn.cursor()
        ultimo = self._ultimo_processamento_ocr(cursor, arquivo_nome)
        if not ultimo:
            conn.close()
            return []
        cursor.execute(
            """
            SELECT pagina, engine, texto FROM ocr_paginas
            WHERE arquivo_nome = %s AND data_processamento = %s
            ORDER BY pagina
            """,
            (arquivo_nome, ultimo),
        )
        rows = cursor.fetchall()
        conn.close()
        return rows

    # ─────────────────────────────────────────────────────────────────────────
    # DOSSIÊS (Análise Documental)
    # ─────────────────────────────────────────────────────────────────────────

    def criar_dossie(self, nome: str, arquivos: List[str], pasta_id: Optional[int] = None) -> int:
        conn = self.require_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO dossies (nome, arquivos, status, progresso, mensagem, pasta_id) VALUES (%s, %s, 'processando', 0, 'Na fila', %s)",
            (nome, json.dumps(arquivos, ensure_ascii=False), pasta_id),
        )
        dossie_id = cursor.lastrowid
        conn.close()
        return dossie_id

    def atualizar_dossie(
        self,
        dossie_id: int,
        status: Optional[str] = None,
        progresso: Optional[int] = None,
        mensagem: Optional[str] = None,
        resultado: Optional[Dict[str, Any]] = None,
    ) -> None:
        valores = {
            "status": status,
            "progresso": progresso,
            "mensagem": mensagem[:2000] if mensagem is not None else None,
            "resultado": json.dumps(resultado, ensure_ascii=False, default=str) if resultado is not None else None,
        }
        valores = {k: v for k, v in valores.items() if v is not None}
        if not valores:
            return
        sets = [f"{k} = %s" for k in valores]
        params = list(valores.values())
        conn = self.require_connection()
        cursor = conn.cursor()
        cursor.execute(f"UPDATE dossies SET {', '.join(sets)} WHERE id = %s", (*params, dossie_id))
        conn.close()

    def listar_dossies(self, limite: int = 100) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        if not conn:
            return []
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, nome, arquivos, status, progresso, mensagem, pasta_id, created_at, updated_at
            FROM dossies ORDER BY id DESC LIMIT %s
            """,
            (limite,),
        )
        rows = cursor.fetchall()
        conn.close()
        for r in rows:
            r["arquivos"] = json.loads(r["arquivos"]) if isinstance(r["arquivos"], str) else r["arquivos"]
        return rows

    def obter_dossie(self, dossie_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        if not conn:
            return None
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM dossies WHERE id = %s", (dossie_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        row["arquivos"] = json.loads(row["arquivos"]) if isinstance(row["arquivos"], str) else row["arquivos"]
        row["resultado"] = json.loads(row["resultado"]) if row.get("resultado") else None
        return row

    def excluir_dossie(self, dossie_id: int) -> bool:
        conn = self.require_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM dossies WHERE id = %s", (dossie_id,))
        ok = cursor.rowcount > 0
        conn.close()
        return ok

    # ─────────────────────────────────────────────────────────────────────────
    # PASTAS (um convênio = uma pasta com seus volumes em ordem)
    # ─────────────────────────────────────────────────────────────────────────

    CAMPOS_PASTA = ("nome", "numero_convenio", "convenente", "observacao")

    @staticmethod
    def _ultimos_jobs(cursor, nomes: List[str]) -> Dict[str, Dict[str, Any]]:
        if not nomes:
            return {}
        marcadores = ", ".join(["%s"] * len(nomes))
        cursor.execute(
            f"""
            SELECT j.arquivo_nome, j.status, j.total_paginas, j.total_resumos, j.total_cc, j.mensagem, j.updated_at
            FROM processamento_jobs j
            INNER JOIN (
                SELECT arquivo_nome, MAX(id) AS max_id FROM processamento_jobs
                WHERE arquivo_nome IN ({marcadores}) GROUP BY arquivo_nome
            ) u ON u.max_id = j.id
            """,
            tuple(nomes),
        )
        return {r["arquivo_nome"]: r for r in cursor.fetchall()}

    @staticmethod
    def _situacao_arquivo(nome: str, ordem: int, job: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        job = job or {}
        return {
            "arquivo_nome": nome,
            "ordem": ordem,
            "status": job.get("status") or "fila",
            "total_paginas": job.get("total_paginas") or 0,
            "total_resumos": job.get("total_resumos") or 0,
            "total_cc": job.get("total_cc") or 0,
            "mensagem": job.get("mensagem") or "Aguardando OCR",
            "updated_at": job.get("updated_at"),
        }

    def criar_pasta(self, nome: str, numero_convenio: str = None, convenente: str = None, observacao: str = None) -> int:
        conn = self.require_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO pastas (nome, numero_convenio, convenente, observacao) VALUES (%s, %s, %s, %s)",
            (nome, numero_convenio or None, convenente or None, observacao or None),
        )
        pasta_id = cursor.lastrowid
        conn.close()
        return pasta_id

    def atualizar_pasta(self, pasta_id: int, campos: Dict[str, Any]) -> bool:
        valores = {k: (campos[k] or None) for k in self.CAMPOS_PASTA if k in campos}
        if valores.get("nome") is None:
            valores.pop("nome", None)
        if not valores:
            return False
        conn = self.require_connection()
        cursor = conn.cursor()
        sets = ", ".join(f"{k} = %s" for k in valores)
        cursor.execute(f"UPDATE pastas SET {sets} WHERE id = %s", (*valores.values(), pasta_id))
        conn.close()
        return True

    def listar_pastas(self) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        if not conn:
            return []
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pastas ORDER BY updated_at DESC, id DESC")
        pastas = cursor.fetchall()
        cursor.execute("SELECT pasta_id, arquivo_nome FROM pasta_arquivos")
        vinculos = cursor.fetchall()
        jobs = self._ultimos_jobs(cursor, [v["arquivo_nome"] for v in vinculos])
        cursor.execute("SELECT id, pasta_id, status, progresso FROM dossies WHERE pasta_id IS NOT NULL ORDER BY id DESC")
        ultima_analise: Dict[int, Dict[str, Any]] = {}
        for d in cursor.fetchall():
            ultima_analise.setdefault(d["pasta_id"], d)
        conn.close()

        por_pasta: Dict[int, List[str]] = {}
        for v in vinculos:
            por_pasta.setdefault(v["pasta_id"], []).append(v["arquivo_nome"])
        for p in pastas:
            nomes = por_pasta.get(p["id"], [])
            status = [(jobs.get(n) or {}).get("status") or "fila" for n in nomes]
            p["total_arquivos"] = len(nomes)
            p["total_paginas"] = sum((jobs.get(n) or {}).get("total_paginas") or 0 for n in nomes)
            p["processando"] = sum(s in ("fila", "processando") for s in status)
            p["com_erro"] = status.count("erro")
            analise = ultima_analise.get(p["id"])
            p["analise"] = {"id": analise["id"], "status": analise["status"], "progresso": analise["progresso"]} if analise else None
        return pastas

    def obter_pasta(self, pasta_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        if not conn:
            return None
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pastas WHERE id = %s", (pasta_id,))
        pasta = cursor.fetchone()
        if not pasta:
            conn.close()
            return None
        cursor.execute(
            "SELECT arquivo_nome, ordem FROM pasta_arquivos WHERE pasta_id = %s ORDER BY ordem, id", (pasta_id,)
        )
        vinculos = cursor.fetchall()
        jobs = self._ultimos_jobs(cursor, [v["arquivo_nome"] for v in vinculos])
        cursor.execute(
            """
            SELECT id, nome, arquivos, status, progresso, mensagem, created_at, updated_at
            FROM dossies WHERE pasta_id = %s ORDER BY id DESC
            """,
            (pasta_id,),
        )
        analises = cursor.fetchall()
        conn.close()
        for a in analises:
            a["arquivos"] = json.loads(a["arquivos"]) if isinstance(a["arquivos"], str) else a["arquivos"]
        pasta["arquivos"] = [self._situacao_arquivo(v["arquivo_nome"], v["ordem"], jobs.get(v["arquivo_nome"])) for v in vinculos]
        pasta["analises"] = analises
        return pasta

    def pasta_do_arquivo(self, arquivo_nome: str) -> Optional[int]:
        conn = self._get_connection()
        if not conn:
            return None
        cursor = conn.cursor()
        cursor.execute("SELECT pasta_id FROM pasta_arquivos WHERE arquivo_nome = %s", (arquivo_nome,))
        row = cursor.fetchone()
        conn.close()
        return row["pasta_id"] if row else None

    def vincular_arquivo(self, pasta_id: int, arquivo_nome: str) -> None:
        """Coloca o arquivo no fim da pasta (ou o move de outra pasta)."""
        conn = self.require_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT pasta_id FROM pasta_arquivos WHERE arquivo_nome = %s", (arquivo_nome,))
        atual = cursor.fetchone()
        if not atual or atual["pasta_id"] != pasta_id:
            cursor.execute("SELECT COALESCE(MAX(ordem), 0) + 1 AS prox FROM pasta_arquivos WHERE pasta_id = %s", (pasta_id,))
            prox = cursor.fetchone()["prox"]
            cursor.execute(
                """
                INSERT INTO pasta_arquivos (pasta_id, arquivo_nome, ordem) VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE pasta_id = VALUES(pasta_id), ordem = VALUES(ordem)
                """,
                (pasta_id, arquivo_nome, prox),
            )
        cursor.execute("UPDATE pastas SET updated_at = CURRENT_TIMESTAMP WHERE id = %s", (pasta_id,))

        # Análises criadas antes das pastas passam a pertencer à pasta que contém todos os seus arquivos
        cursor.execute("SELECT arquivo_nome FROM pasta_arquivos WHERE pasta_id = %s", (pasta_id,))
        da_pasta = {r["arquivo_nome"] for r in cursor.fetchall()}
        cursor.execute("SELECT id, arquivos FROM dossies WHERE pasta_id IS NULL")
        for d in cursor.fetchall():
            arquivos = json.loads(d["arquivos"]) if isinstance(d["arquivos"], str) else d["arquivos"]
            if arquivos and set(arquivos) <= da_pasta:
                cursor.execute("UPDATE dossies SET pasta_id = %s WHERE id = %s", (pasta_id, d["id"]))
        conn.close()

    def reordenar_pasta(self, pasta_id: int, arquivos: List[str]) -> None:
        conn = self.require_connection()
        cursor = conn.cursor()
        for i, nome in enumerate(arquivos, start=1):
            cursor.execute(
                "UPDATE pasta_arquivos SET ordem = %s WHERE pasta_id = %s AND arquivo_nome = %s", (i, pasta_id, nome)
            )
        conn.close()

    def _apagar_dados_arquivo(self, cursor, arquivo_nome: str) -> None:
        for tabela in ("extracoes", "resumos_mensais", "movimentacoes_cc", "ocr_paginas", "processamento_jobs"):
            cursor.execute(f"DELETE FROM {tabela} WHERE arquivo_nome = %s", (arquivo_nome,))

    def remover_arquivo_pasta(self, pasta_id: int, arquivo_nome: str, apagar_dados: bool = False) -> bool:
        conn = self.require_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM pasta_arquivos WHERE pasta_id = %s AND arquivo_nome = %s", (pasta_id, arquivo_nome)
        )
        ok = cursor.rowcount > 0
        if ok and apagar_dados:
            self._apagar_dados_arquivo(cursor, arquivo_nome)
        conn.close()
        return ok

    def excluir_pasta(self, pasta_id: int, apagar_dados: bool = True) -> bool:
        conn = self.require_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT arquivo_nome FROM pasta_arquivos WHERE pasta_id = %s", (pasta_id,))
        nomes = [r["arquivo_nome"] for r in cursor.fetchall()]
        if apagar_dados:
            for nome in nomes:
                self._apagar_dados_arquivo(cursor, nome)
            cursor.execute("DELETE FROM dossies WHERE pasta_id = %s", (pasta_id,))
        else:
            cursor.execute("UPDATE dossies SET pasta_id = NULL WHERE pasta_id = %s", (pasta_id,))
        cursor.execute("DELETE FROM pasta_arquivos WHERE pasta_id = %s", (pasta_id,))
        cursor.execute("DELETE FROM pastas WHERE id = %s", (pasta_id,))
        ok = cursor.rowcount > 0
        conn.close()
        return ok

    def marcar_interrompidos(self) -> None:
        """Na subida do servidor, nada pode estar rodando: jobs e análises em andamento foram interrompidos."""
        conn = self._get_connection()
        if not conn:
            return
        cursor = conn.cursor()
        if self.pg:
            cursor.execute(
                """
                UPDATE processamento_jobs
                SET status = 'erro', mensagem = 'Interrompido (servidor reiniciado). Envie o arquivo novamente.'
                WHERE status IN ('fila', 'processando')
                  AND id IN (SELECT MAX(id) FROM processamento_jobs GROUP BY arquivo_nome)
                """
            )
        else:
            cursor.execute(
                """
                UPDATE processamento_jobs j
                INNER JOIN (SELECT arquivo_nome, MAX(id) AS max_id FROM processamento_jobs GROUP BY arquivo_nome) u
                    ON u.max_id = j.id
                SET j.status = 'erro', j.mensagem = 'Interrompido (servidor reiniciado). Envie o arquivo novamente.'
                WHERE j.status IN ('fila', 'processando')
                """
            )
        cursor.execute(
            "UPDATE dossies SET status = 'erro', mensagem = 'Interrompido (servidor reiniciado). Clique em Reprocessar.' "
            "WHERE status = 'processando'"
        )
        conn.close()

    def arquivos_sem_pasta(self) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        if not conn:
            return []
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT j.arquivo_nome FROM processamento_jobs j
            LEFT JOIN pasta_arquivos pa ON pa.arquivo_nome = j.arquivo_nome
            WHERE pa.id IS NULL
            """
        )
        nomes = [r["arquivo_nome"] for r in cursor.fetchall()]
        jobs = self._ultimos_jobs(cursor, nomes)
        conn.close()
        itens = [self._situacao_arquivo(n, 0, jobs.get(n)) for n in nomes]
        return sorted(itens, key=lambda a: str(a["updated_at"] or ""), reverse=True)

    def registrar_job(
        self,
        arquivo_nome: str,
        data_processamento: str,
        status: str,
        total_paginas: int = 0,
        total_resumos: int = 0,
        total_cc: int = 0,
        mensagem: str = "",
    ) -> int:
        conn = self.require_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO processamento_jobs
            (arquivo_nome, data_processamento, status, total_paginas, total_resumos, total_cc, mensagem)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (arquivo_nome, data_processamento, status, total_paginas, total_resumos, total_cc, mensagem),
        )
        job_id = cursor.lastrowid
        conn.close()
        return job_id

    def atualizar_job(
        self,
        arquivo_nome: str,
        data_processamento: str,
        status: str,
        total_paginas: int = 0,
        total_resumos: int = 0,
        total_cc: int = 0,
        mensagem: str = "",
    ) -> None:
        conn = self.require_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id FROM processamento_jobs
            WHERE arquivo_nome = %s AND data_processamento = %s
            ORDER BY id DESC LIMIT 1
            """,
            (arquivo_nome, data_processamento),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return
        cursor.execute(
            """
            UPDATE processamento_jobs
            SET status = %s, total_paginas = %s, total_resumos = %s, total_cc = %s, mensagem = %s
            WHERE id = %s
            """,
            (status, total_paginas, total_resumos, total_cc, mensagem, row["id"]),
        )
        conn.close()

    def listar_historico_arquivos(self, limite: int = 100) -> List[Dict[str, Any]]:
        """Histórico real: jobs + contagens de resumos/CC (não usa tabela legado extracoes)."""
        conn = self._get_connection()
        if not conn:
            return []
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                j.arquivo_nome,
                j.data_processamento,
                j.status,
                j.total_paginas,
                j.total_resumos,
                j.total_cc,
                j.mensagem,
                j.updated_at
            FROM processamento_jobs j
            INNER JOIN (
                SELECT arquivo_nome, MAX(id) AS max_id
                FROM processamento_jobs
                GROUP BY arquivo_nome
            ) last_job ON last_job.max_id = j.id
            ORDER BY j.updated_at DESC
            LIMIT %s
            """,
            (limite,),
        )
        rows = cursor.fetchall()
        conn.close()
        return rows

    def obter_ultimo_job(self, arquivo_nome: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        if not conn:
            return None
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM processamento_jobs
            WHERE arquivo_nome = %s
            ORDER BY id DESC LIMIT 1
            """,
            (arquivo_nome,),
        )
        row = cursor.fetchone()
        conn.close()
        return row

    def obter_resultados_arquivo(self, arquivo_nome: str) -> Dict[str, Any]:
        """Monta o payload completo a partir do MySQL (recuperação sem WebSocket)."""
        resumos = self.listar_resumos_mensais(arquivo_nome)
        movimentacoes = self.listar_movimentacoes_cc(arquivo_nome)
        ocr_meta = self.listar_ocr_paginas(arquivo_nome)
        job = self.obter_ultimo_job(arquivo_nome)
        return {
            "arquivo": arquivo_nome,
            "resumos_mensais": resumos,
            "movimentacoes_cc": movimentacoes,
            "ocr_paginas": ocr_meta,
            "total_resumos": len(resumos),
            "total_cc": len(movimentacoes),
            "job": job,
        }
