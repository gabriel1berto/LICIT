-- Vertical Informática (19/nov/2026) — schema isolado de public/oncologia/pecas_automotivas.
-- Só editais abertos/futuros (busca PNCP status=recebendo_proposta) + itens deles.
-- Categoria/cobertura GET NÃO é gravada: calculada na leitura (conectar_informatica.py),
-- então ajuste no filtro_informatica.py vale na hora, sem script de recompute.

CREATE SCHEMA IF NOT EXISTS informatica;

CREATE TABLE IF NOT EXISTS informatica.editais (
    numero_controle_pncp      text PRIMARY KEY,
    uf                        text,
    codigo_ibge               integer,
    municipio_nome            text,
    orgao_nome                text,
    orgao_cnpj                text,
    unidade_nome              text,
    modalidade_licitacao_nome text,
    titulo                    text,
    descricao                 text,
    ano                       text,
    numero_sequencial         text,
    srp                       boolean,
    link_sistema_origem       text,
    data_publicacao_pncp      text,
    data_inicio_vigencia      text,   -- abertura de proposta (search API)
    data_fim_vigencia         text,   -- fim de proposta (ou vigência de ata em SRP/credenciamento)
    situacao_nome             text,
    cancelado                 boolean,
    valor_total_estimado      numeric,
    termos                    text[] NOT NULL DEFAULT '{}',
    coletado_em               timestamptz NOT NULL DEFAULT now(),
    itens_coletados_em        timestamptz
);

CREATE TABLE IF NOT EXISTS informatica.itens (
    numero_controle_pncp    text NOT NULL REFERENCES informatica.editais ON DELETE CASCADE,
    numero_item             integer NOT NULL,
    descricao               text,
    quantidade              numeric,
    unidade_medida          text,
    valor_unitario_estimado numeric,
    valor_total             numeric,
    material_ou_servico     text,
    beneficio_nome          text,
    orcamento_sigiloso      boolean,
    PRIMARY KEY (numero_controle_pncp, numero_item)
);

CREATE TABLE IF NOT EXISTS informatica.vocabulario_termos (
    termo              text PRIMARY KEY,
    total_ultima_busca integer,
    ultima_busca_em    timestamptz
);

CREATE INDEX IF NOT EXISTS editais_fim_idx ON informatica.editais (data_fim_vigencia);
