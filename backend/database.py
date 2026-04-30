import pymysql
import pymysql.cursors
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging
import json
import os
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


class ExtractionDatabase:
    """
    Banco de dados MySQL para armazenar todas as extrações
    Substitui o SQLite para maior robustez e escalabilidade
    """
    
    def __init__(self):
        self.host = os.getenv("MYSQL_HOST", "localhost")
        try:
            port_str = os.getenv("MYSQL_PORT", "3306").strip()
            self.port = int(port_str) if port_str else 3306
        except Exception:
            self.port = 3306
        self.user = os.getenv("MYSQL_USER", "root")
        self.password = os.getenv("MYSQL_PASSWORD", "")
        self.database = os.getenv("MYSQL_DATABASE", "convenio2")
        self._init_database()
    
    def _get_connection(self):
        return pymysql.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database,
            port=self.port,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )
    
    def _init_database(self):
        """Inicializa as tabelas se não existirem (no MySQL)"""
        try:
            conn = self._get_connection()
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

            conn.close()
            logger.info("✅ MySQL Conectado e Tabelas Verificadas.")
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
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM extracoes")
        extracoes_removidas = cursor.rowcount
        
        cursor.execute("DELETE FROM resumos_mensais")
        resumos_removidos = cursor.rowcount
        
        cursor.execute("DELETE FROM movimentacoes_cc")
        cc_removidas = cursor.rowcount
        
        conn.close()
        
        logger.warning(f"BANCO LIMPO: {extracoes_removidas} extracoes + {resumos_removidos} resumos removidos")
        return {"extracoes": extracoes_removidas, "resumos": resumos_removidos, "cc": cc_removidas}
    
    def limpar_arquivo(self, arquivo_nome: str):
        """
        Remove apenas os dados de um arquivo específico
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM extracoes WHERE arquivo_nome = %s", (arquivo_nome,))
        extracoes_removidas = cursor.rowcount
        
        cursor.execute("DELETE FROM resumos_mensais WHERE arquivo_nome = %s", (arquivo_nome,))
        resumos_removidos = cursor.rowcount
        
        cursor.execute("DELETE FROM movimentacoes_cc WHERE arquivo_nome = %s", (arquivo_nome,))
        cc_removidos = cursor.rowcount
        
        conn.close()
        
        if extracoes_removidas > 0 or resumos_removidos > 0 or cc_removidos > 0:
            logger.info(f"Removidos dados antigos para '{arquivo_nome}'")
    
    def salvar_resumo_individual(
        self,
        arquivo_nome: str,
        pagina: int,
        campos: Dict[str, Optional[float]],
        data_processamento: Optional[str] = None
    ) -> int:
        """
        Salva UM resumo mensal IMEDIATAMENTE no banco
        """
        if data_processamento is None:
            data_processamento = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
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
        
        resumo_id = cursor.lastrowid
        conn.close()
        
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
        conn = self._get_connection()
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
        return row_id

    def listar_movimentacoes_cc(self, arquivo_nome: str) -> List[Dict[str, Any]]:
        """Retorna todas as movimentações CC de um arquivo, ordenadas por id."""
        conn = self._get_connection()
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
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM movimentacoes_cc WHERE arquivo_nome = %s", (arquivo_nome,))
        conn.close()
