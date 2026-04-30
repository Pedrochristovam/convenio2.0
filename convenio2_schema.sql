-- Script de migração do Convênio 2.0 para MySQL
-- Execute este script no seu MySQL Workbench ou Terminal MySQL

-- 1. Criar o Banco de Dados
CREATE DATABASE IF NOT EXISTS convenio2 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE convenio2;

-- 2. Tabela de Extrações Brutas
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
) ENGINE=InnoDB;

-- 3. Tabela de Resumos Mensais (Investimento)
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
) ENGINE=InnoDB;

-- 4. Tabela de Movimentações de Conta Corrente (Detalhamento)
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
) ENGINE=InnoDB;
