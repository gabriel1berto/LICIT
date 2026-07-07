-- schema_supabase.sql — Schema Postgres para o pipeline PNCP (migrado de
-- pncp_raw.db, SQLite). Aplicar uma única vez contra o projeto Supabase novo,
-- antes de rodar migrar_para_supabase.py. Idempotente (IF NOT EXISTS em tudo).
--
-- Diferenças vs. schema SQLite original:
--   - REAL -> DOUBLE PRECISION
--   - 7 colunas flag (INTEGER 0/1) -> BOOLEAN de verdade: editais.tem_resultado,
--     editais.dentro_periodo_alvo, filas.concluida, detalhes.srp,
--     detalhes.existe_resultado, itens.tem_resultado, itens.eh_pneu
--   - 3 índices novos (não existiam no SQLite local — arquivo local não tinha
--     latência de rede pra justificar; aqui cada leitura vira round-trip)

CREATE TABLE IF NOT EXISTS editais (
    numero_controle_pncp      TEXT PRIMARY KEY,
    uf                        TEXT,
    modalidade_licitacao_id   TEXT,
    modalidade_licitacao_nome TEXT,
    municipio_nome            TEXT,
    orgao_nome                TEXT,
    orgao_cnpj                TEXT,
    unidade_nome              TEXT,
    titulo                    TEXT,
    descricao                 TEXT,
    ano                       TEXT,
    numero_sequencial         TEXT,
    data_publicacao_pncp      TEXT,
    data_atualizacao_pncp     TEXT,
    situacao_nome              TEXT,
    valor_global               DOUBLE PRECISION,
    tem_resultado               BOOLEAN,
    item_url                    TEXT,
    classificacao                TEXT,
    dentro_periodo_alvo          BOOLEAN,
    json_bruto                    TEXT,
    coletado_em                   TEXT
);

CREATE TABLE IF NOT EXISTS filas (
    uf              TEXT PRIMARY KEY,
    proxima_pagina  INTEGER DEFAULT 1,
    total_esperado  INTEGER,
    concluida       BOOLEAN DEFAULT FALSE,
    atualizado_em   TEXT
);

CREATE TABLE IF NOT EXISTS detalhes (
    numero_controle_pncp        TEXT PRIMARY KEY,
    valor_total_estimado        DOUBLE PRECISION,
    valor_total_homologado      DOUBLE PRECISION,
    srp                         BOOLEAN,
    objeto_compra                TEXT,
    municipio_nome                TEXT,
    codigo_ibge                    TEXT,
    uf_sigla                        TEXT,
    modalidade_nome                  TEXT,
    modo_disputa_nome                 TEXT,
    poder_id                           TEXT,
    esfera_id                           TEXT,
    situacao_compra_nome                 TEXT,
    existe_resultado                      BOOLEAN,
    data_abertura_proposta                 TEXT,
    data_encerramento_proposta              TEXT,
    link_sistema_origem                      TEXT,
    usuario_nome                              TEXT,
    coletado_em                                TEXT
);

CREATE TABLE IF NOT EXISTS itens (
    numero_controle_pncp     TEXT,
    numero_item              INTEGER,
    descricao                 TEXT,
    material_ou_servico        TEXT,
    valor_unitario_estimado     DOUBLE PRECISION,
    valor_total                  DOUBLE PRECISION,
    quantidade                    DOUBLE PRECISION,
    unidade_medida                 TEXT,
    situacao_item_nome              TEXT,
    criterio_julgamento_nome         TEXT,
    tipo_beneficio_nome               TEXT,
    ncm_nbs_codigo                      TEXT,
    tem_resultado                        BOOLEAN,
    eh_pneu                               BOOLEAN,
    categoria                              TEXT,
    PRIMARY KEY (numero_controle_pncp, numero_item)
);

CREATE TABLE IF NOT EXISTS resultados (
    numero_controle_pncp        TEXT,
    numero_item                 INTEGER,
    ni_fornecedor                 TEXT,
    nome_fornecedor                 TEXT,
    tipo_pessoa                       TEXT,
    porte_fornecedor_nome               TEXT,
    valor_unitario_homologado             DOUBLE PRECISION,
    valor_total_homologado                  DOUBLE PRECISION,
    percentual_desconto                       DOUBLE PRECISION,
    quantidade_homologada                       DOUBLE PRECISION,
    ordem_classificacao_srp                       INTEGER,
    data_resultado                                  TEXT,
    PRIMARY KEY (numero_controle_pncp, numero_item, ni_fornecedor)
);

CREATE TABLE IF NOT EXISTS progresso_detalhe (
    numero_controle_pncp  TEXT PRIMARY KEY,
    status                TEXT DEFAULT 'pendente',
    tentativas            INTEGER DEFAULT 0,
    atualizado_em         TEXT
);

CREATE INDEX IF NOT EXISTS idx_progresso_detalhe_status ON progresso_detalhe (status);
CREATE INDEX IF NOT EXISTS idx_editais_dentro_periodo ON editais (dentro_periodo_alvo) WHERE dentro_periodo_alvo = TRUE;
CREATE INDEX IF NOT EXISTS idx_itens_eh_pneu ON itens (eh_pneu) WHERE eh_pneu = TRUE;
