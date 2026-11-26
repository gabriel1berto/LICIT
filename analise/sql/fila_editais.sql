-- Fila de editais marcados no dashboard (26/nov/2026). O dashboard só grava a marcação;
-- a leitura do TR e a ficha acontecem no Claude Code (/licit-fila), que preenche ficha/lido_em.
CREATE SCHEMA IF NOT EXISTS fila;

CREATE TABLE IF NOT EXISTS fila.editais (
    numero_controle_pncp text PRIMARY KEY,
    vertical             text NOT NULL,            -- pneu | informatica | pecas
    orgao_nome           text,
    uf                   text,
    pncp_url             text,
    interesse            boolean NOT NULL DEFAULT false,
    ler_tr               boolean NOT NULL DEFAULT false,
    status               text NOT NULL DEFAULT 'marcado',  -- marcado | na_fila | lido | erro
    marcado_em           timestamptz NOT NULL DEFAULT now(),
    ler_pedido_em        timestamptz,
    lido_em              timestamptz,
    ficha                jsonb,
    observacao           text
);
