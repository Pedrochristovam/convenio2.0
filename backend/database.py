import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging
import json

logger = logging.getLogger(__name__)


class ExtractionDatabase:
    """
    Banco de dados SQLite para armazenar todas as extracoes
    Isso elimina alucinacoes e cria um historico confiavel
    """
    
    def __init__(self, db_path: str = "extractions.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Cria as tabelas se nao existirem"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabela principal de extrações
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extracoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                arquivo_nome TEXT NOT NULL,
                data_processamento TEXT NOT NULL,
                campo TEXT NOT NULL,
                valor REAL NOT NULL,
                data_extracao TEXT NOT NULL,
                pagina INTEGER NOT NULL,
                linha_ocr TEXT,
                confianca TEXT,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Nova tabela para resumos mensais
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS resumos_mensais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                arquivo_nome TEXT NOT NULL,
                data_processamento TEXT NOT NULL,
                pagina INTEGER NOT NULL,
                saldo_anterior REAL,
                aplicacoes REAL,
                resgates REAL,
                rendimento_bruto REAL,
                imposto_renda REAL,
                iof REAL,
                rendimento_liquido REAL,
                saldo_atual REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(arquivo_nome, data_processamento, pagina)
            )
        """)
        
        # Índices para busca rápida
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_arquivo 
            ON extracoes(arquivo_nome)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_data_processamento 
            ON extracoes(data_processamento)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_campo 
            ON extracoes(campo)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_resumos_arquivo 
            ON resumos_mensais(arquivo_nome)
        """)
        
        conn.commit()
        conn.close()
        logger.info(f"Banco de dados inicializado: {self.db_path}")
    
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
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO extracoes 
            (arquivo_nome, data_processamento, campo, valor, data_extracao, 
             pagina, linha_ocr, confianca, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        conn.commit()
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
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # REMOVE extrações antigas deste arquivo (evita duplicatas)
        cursor.execute("DELETE FROM extracoes WHERE arquivo_nome = ?", (arquivo_nome,))
        linhas_removidas = cursor.rowcount
        if linhas_removidas > 0:
            logger.info(f"Removidas {linhas_removidas} extracoes antigas de {arquivo_nome}")
        
        for pagina, resultados in resultados_por_pagina.items():
            for res in resultados:
                cursor.execute("""
                    INSERT INTO extracoes 
                    (arquivo_nome, data_processamento, campo, valor, data_extracao, 
                     pagina, linha_ocr, confianca, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        
        conn.commit()
        conn.close()
        
        logger.info(f"Salvos {total_salvos} registros no banco para {arquivo_nome}")
        return total_salvos
    
    def listar_ultima_extracao(self, arquivo_nome: str) -> List[Dict[str, Any]]:
        """Lista a última extração de um arquivo específico"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Busca a última data de processamento deste arquivo
        cursor.execute("""
            SELECT DISTINCT data_processamento 
            FROM extracoes 
            WHERE arquivo_nome = ?
            ORDER BY data_processamento DESC
            LIMIT 1
        """, (arquivo_nome,))
        
        result = cursor.fetchone()
        if not result:
            conn.close()
            return []
        
        ultima_data = result[0]
        
        # Busca todos os registros desta extração
        cursor.execute("""
            SELECT id, campo, valor, data_extracao, pagina, linha_ocr, confianca, status
            FROM extracoes
            WHERE arquivo_nome = ? AND data_processamento = ?
            ORDER BY pagina, id
        """, (arquivo_nome, ultima_data))
        
        rows = cursor.fetchall()
        conn.close()
        
        registros = []
        for row in rows:
            registros.append({
                "id": row[0],
                "campo": row[1],
                "valor": row[2],
                "data_extracao": row[3],
                "pagina": row[4],
                "linha_ocr": row[5],
                "confianca": row[6],
                "status": row[7]
            })
        
        return registros
    
    def listar_todas_extracoes(self, limite: int = 100) -> List[Dict[str, Any]]:
        """Lista todas as extrações do banco"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, arquivo_nome, data_processamento, campo, valor, 
                   data_extracao, pagina, linha_ocr, confianca, status
            FROM extracoes
            ORDER BY created_at DESC
            LIMIT ?
        """, (limite,))
        
        rows = cursor.fetchall()
        conn.close()
        
        registros = []
        for row in rows:
            registros.append({
                "id": row[0],
                "arquivo_nome": row[1],
                "data_processamento": row[2],
                "campo": row[3],
                "valor": row[4],
                "data_extracao": row[5],
                "pagina": row[6],
                "linha_ocr": row[7],
                "confianca": row[8],
                "status": row[9]
            })
        
        return registros
    
    def estatisticas(self) -> Dict[str, Any]:
        """Retorna estatísticas do banco"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Total de registros
        cursor.execute("SELECT COUNT(*) FROM extracoes")
        total_registros = cursor.fetchone()[0]
        
        # Total de arquivos processados
        cursor.execute("SELECT COUNT(DISTINCT arquivo_nome) FROM extracoes")
        total_arquivos = cursor.fetchone()[0]
        
        # Distribuição por campo
        cursor.execute("""
            SELECT campo, COUNT(*) as count
            FROM extracoes
            GROUP BY campo
            ORDER BY count DESC
        """)
        distribuicao_campos = {row[0]: row[1] for row in cursor.fetchall()}
        
        conn.close()
        
        return {
            "total_registros": total_registros,
            "total_arquivos": total_arquivos,
            "distribuicao_campos": distribuicao_campos
        }
    
    def salvar_resumos_mensais(
        self,
        arquivo_nome: str,
        resumos: Dict[int, Dict[str, Any]]
    ) -> int:
        """
        Salva resumos mensais no banco
        
        Args:
            arquivo_nome: Nome do arquivo processado
            resumos: Dict[pagina, resumo_data]
        
        Returns:
            Número de resumos salvos
        """
        data_processamento = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_salvos = 0
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # REMOVE resumos antigos deste arquivo (evita duplicatas)
        cursor.execute("DELETE FROM resumos_mensais WHERE arquivo_nome = ?", (arquivo_nome,))
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        
        conn.commit()
        conn.close()
        
        logger.info(f"Salvos {total_salvos} resumos mensais no banco para {arquivo_nome}")
        return total_salvos
    
    def listar_resumos_mensais(self, arquivo_nome: str) -> Dict[int, Dict[str, Any]]:
        """
        Lista os resumos mensais da última extração de um arquivo
        
        Returns:
            Dict[pagina, resumo_data]
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Busca a última data de processamento deste arquivo
        cursor.execute("""
            SELECT DISTINCT data_processamento 
            FROM resumos_mensais 
            WHERE arquivo_nome = ?
            ORDER BY data_processamento DESC
            LIMIT 1
        """, (arquivo_nome,))
        
        result = cursor.fetchone()
        if not result:
            conn.close()
            return {}
        
        ultima_data = result[0]
        
        # Busca todos os resumos desta extração
        cursor.execute("""
            SELECT pagina, saldo_anterior, aplicacoes, resgates, rendimento_bruto,
                   imposto_renda, iof, rendimento_liquido, saldo_atual
            FROM resumos_mensais
            WHERE arquivo_nome = ? AND data_processamento = ?
            ORDER BY pagina
        """, (arquivo_nome, ultima_data))
        
        rows = cursor.fetchall()
        conn.close()
        
        resumos = {}
        for row in rows:
            pagina = row[0]
            resumos[pagina] = {
                "tipo": "RESUMO_MENSAL",
                "pagina": pagina,
                "campos": {
                    "saldo_anterior": row[1],
                    "aplicacoes": row[2],
                    "resgates": row[3],
                    "rendimento_bruto": row[4],
                    "imposto_renda": row[5],
                    "iof": row[6],
                    "rendimento_liquido": row[7],
                    "saldo_atual": row[8]
                }
            }
        
        return resumos
    
    def limpar_banco(self):
        """
        CUIDADO: Remove TODOS os dados do banco
        Útil para testes ou reset completo
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM extracoes")
        extracoes_removidas = cursor.rowcount
        
        cursor.execute("DELETE FROM resumos_mensais")
        resumos_removidos = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        logger.warning(f"BANCO LIMPO: {extracoes_removidas} extracoes + {resumos_removidos} resumos removidos")
        return {"extracoes": extracoes_removidas, "resumos": resumos_removidos}
    
    def limpar_arquivo(self, arquivo_nome: str):
        """
        Remove apenas os dados de um arquivo específico
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM extracoes WHERE arquivo_nome = ?", (arquivo_nome,))
        extracoes_removidas = cursor.rowcount
        
        cursor.execute("DELETE FROM resumos_mensais WHERE arquivo_nome = ?", (arquivo_nome,))
        resumos_removidos = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        if extracoes_removidas > 0 or resumos_removidos > 0:
            logger.info(f"Removidos dados antigos: {extracoes_removidas} extracoes + {resumos_removidos} resumos de '{arquivo_nome}'")
    
    def salvar_resumo_individual(
        self,
        arquivo_nome: str,
        pagina: int,
        campos: Dict[str, Optional[float]],
        data_processamento: Optional[str] = None
    ) -> int:
        """
        Salva UM resumo mensal IMEDIATAMENTE no banco
        (Gravação incremental página por página)
        
        Args:
            data_processamento: Se fornecida, usa esta data (para manter consistência no lote)
        """
        if data_processamento is None:
            data_processamento = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO resumos_mensais 
            (arquivo_nome, data_processamento, pagina,
             saldo_anterior, aplicacoes, resgates, rendimento_bruto,
             imposto_renda, iof, rendimento_liquido, saldo_atual)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        conn.commit()
        conn.close()
        
        logger.debug(f"Resumo da pagina {pagina} gravado no banco (ID: {resumo_id})")
        return resumo_id
