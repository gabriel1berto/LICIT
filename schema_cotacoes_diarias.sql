-- schema_cotacoes_diarias.sql — Schema Postgres pro fluxo de coleta diária de
-- preços por medida (separado do pipeline de mercado PNCP em analise/, mesmo
-- projeto Supabase LICIT — koqsgnvmnzkqzxnskzgq). Idempotente (IF NOT EXISTS).
--
-- Schema `cotacao_fornecedor` (namespace próprio, separado de `public` onde
-- vivem as tabelas do pipeline PNCP — editais/filas/detalhes/itens/resultados/
-- progresso_detalhe). Motivo: mesmo projeto Supabase, dois pipelines com
-- propósito diferente (mercado nacional PNCP vs cotação direta de fornecedor
-- cadastrado) — schema evita confusão entre os dois grupos de tabela.
--
-- cotacoes é append-only (nunca UPDATE/DELETE). aliases_medida só recebe
-- aprovado_por_humano=true depois de revisão manual (ver revisar_aliases_pendentes.py).

CREATE SCHEMA IF NOT EXISTS cotacao_fornecedor;

CREATE TABLE IF NOT EXISTS cotacao_fornecedor.medidas (
    id              SERIAL PRIMARY KEY,
    largura         INTEGER,
    perfil          INTEGER,
    construcao      TEXT DEFAULT 'R',
    aro             NUMERIC,
    tipo_produto    TEXT,
    texto_canonico  TEXT UNIQUE,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cotacao_fornecedor.aliases_medida (
    id                  SERIAL PRIMARY KEY,
    medida_id           INTEGER REFERENCES cotacao_fornecedor.medidas(id),
    fornecedor          TEXT,
    texto_bruto         TEXT,
    inferido            BOOLEAN DEFAULT FALSE,
    aprovado_por_humano BOOLEAN DEFAULT FALSE,
    data_aprovacao      TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW(),
    UNIQUE (fornecedor, texto_bruto)
);

CREATE TABLE IF NOT EXISTS cotacao_fornecedor.cotacoes (
    id                  SERIAL PRIMARY KEY,
    medida_id           INTEGER REFERENCES cotacao_fornecedor.medidas(id),
    fornecedor          TEXT,
    preco               NUMERIC(10,2),
    timestamp           TIMESTAMP DEFAULT NOW(),
    confianca_match     TEXT CHECK (confianca_match IN ('exato', 'parcial', 'sem_match')),
    texto_bruto_origem  TEXT,
    observacao          TEXT,
    marca               TEXT,
    url                 TEXT,
    apto                BOOLEAN,  -- passou critério de habilitação (sempre TRUE em cotação
                                  -- de mercado sem critério, útil quando orquestrador
                                  -- rodar com critério real de edital)
    -- Detalhamento técnico (mesmos critérios usados em habilitação de edital —
    -- ver *_scraper.py; nem todo fornecedor publica todos os campos, NULL é
    -- esperado, não é dado faltando por bug):
    ic                  INTEGER,  -- índice de carga
    iv                  TEXT,     -- índice de velocidade
    treadwear           INTEGER,  -- UTQG
    construcao          TEXT,     -- nylon/poliester/aco/radial (varia por fornecedor)
    num_lonas           INTEGER,
    tipo_terreno        TEXT,     -- AT/HT/MT (Cantu/GP)
    inmetro             TEXT,     -- nº de registro (GP)
    created_at          TIMESTAMP DEFAULT NOW()
);

ALTER TABLE cotacao_fornecedor.medidas ENABLE ROW LEVEL SECURITY;
ALTER TABLE cotacao_fornecedor.aliases_medida ENABLE ROW LEVEL SECURITY;
ALTER TABLE cotacao_fornecedor.cotacoes ENABLE ROW LEVEL SECURITY;
