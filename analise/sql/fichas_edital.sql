-- Ficha do edital (26/nov/2026): tudo que sai da leitura do TR/aviso, pra decidir participar
-- e preparar proposta + habilitação sem abrir o PDF de novo. Preenchida no Claude Code
-- (/licit-fila); o dashboard só lê. Regra: todo campo vem do TR/aviso, nunca da API do PNCP
-- (spec de item) nem de suposição — campo que o documento não traz fica NULL.

-- 1 linha por edital: o que decide participar ou não
CREATE TABLE IF NOT EXISTS fila.fichas (
    numero_controle_pncp   text PRIMARY KEY REFERENCES fila.editais ON DELETE CASCADE,
    certame                text,          -- ex: Dispensa Eletrônica 127/2026
    processo               text,
    orgao                  text,
    municipio              text,
    uf                     text,
    endereco_orgao         text,
    portal                 text,          -- onde a disputa acontece
    portal_url             text,
    cadastro_portal        text,          -- o que precisa pra entrar
    criterio_julgamento    text,          -- menor preço por item / lote / desconto
    exclusivo_me_epp       boolean,
    encerramento_proposta  timestamptz,
    sessao_lances          text,          -- como funcionam os lances (aberto, tempo, prorrogação)
    valor_referencia_total numeric,
    valor_sigiloso         boolean,
    validade_proposta_dias int,
    prazo_entrega          text,
    local_entrega          text,
    garantia_produto       text,
    amostra                text,
    vistoria               text,
    garantia_proposta      text,
    garantia_contrato      text,
    instrumento            text,          -- contrato / empenho
    prazo_pagamento        text,
    condicoes_pagamento    text,
    contato_esclarecimento text,
    links_documentos       jsonb,         -- [{titulo, url}]
    alertas                text[],        -- pegadinhas e contradições achadas no texto
    veredito               text,          -- participar | nao_participar | avaliar
    veredito_motivo        text,
    lido_em                timestamptz NOT NULL DEFAULT now()
);

-- 1 linha por item: o que precisa pra precificar
CREATE TABLE IF NOT EXISTS fila.ficha_itens (
    numero_controle_pncp text REFERENCES fila.fichas ON DELETE CASCADE,
    item                 int,
    lote                 text,
    descricao_tr         text,           -- texto literal do TR
    criterios            jsonb,          -- spec estruturada pra cotação (casar.py)
    quantidade           numeric,
    unidade              text,
    valor_ref_unit       numeric,
    valor_ref_total      numeric,
    garantia             text,
    exige_no_item        text,           -- ficha técnica, catálogo, marca, registro etc.
    produto_ofertado     text,           -- preenchido na cotação
    fornecedor           text,
    custo_unit           numeric,
    link_produto         text,
    obs                  text,
    PRIMARY KEY (numero_controle_pncp, item)
);

-- 1 linha por documento: checklist do que preparar, por fase
CREATE TABLE IF NOT EXISTS fila.ficha_documentos (
    numero_controle_pncp text REFERENCES fila.fichas ON DELETE CASCADE,
    ordem                int,
    fase                 text,           -- proposta | habilitacao | contratacao | pagamento
    documento            text,
    referencia           text,           -- item do TR/aviso
    observacao           text,
    PRIMARY KEY (numero_controle_pncp, ordem)
);
