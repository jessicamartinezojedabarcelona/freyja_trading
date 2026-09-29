-- MARKET-DATA-TWELVEDATA-REST-001 (seguimiento) — migración 0017 aplicada a mano en Neon.
--
-- Equivale EXACTAMENTE a `alembic upgrade 0017_twelvedata_data_source` (un test lo
-- comprueba comparando el resultado de este script con el de Alembic). Solo datos: no
-- cambia el esquema y no toca ninguna fila existente. Añade la fuente TWELVEDATA (tipo
-- MARKET_DATA, no EXCHANGE: no es una casa de cambio) y sus 5 mapeos de análisis — 4 en
-- FOREX, 1 en METALS, los mismos instrumentos que dio de alta la migración 0016 — y sube
-- alembic_version de 0016 a 0017.
--
-- Sin esto, los 5 instrumentos de Twelve Data no aparecen en Mercados (has_market_data se
-- calcula a partir de estos mapeos), aunque el catálogo y el adaptador ya existan.
--
-- Cómo usarlo: pégalo entero en el SQL Editor de Neon y ejecútalo una sola vez, contra la
-- base de producción. Es todo o nada (un único bloque): si algo no cuadra, aborta con un
-- mensaje y no cambia nada. Ejecutarlo dos veces también aborta, sin efectos.
DO $$
DECLARE
    instrument uuid;
    mapping record;
BEGIN
    IF (SELECT version_num FROM alembic_version) <> '0016_forex_metals_catalog' THEN
        RAISE EXCEPTION '0017 abortada: la base no está en 0016_forex_metals_catalog (esperado). No se ha cambiado nada.';
    END IF;

    INSERT INTO freyja2_data_sources (id, code, display_name, source_type, is_active)
    VALUES ('bf433b5c-68d0-543b-a154-85a3dd312a39', 'TWELVEDATA', 'Twelve Data', 'MARKET_DATA', true);

    FOR mapping IN
        SELECT * FROM (VALUES
            ('FOREX', 'EUR/USD', 'EUR/USD', 'b6529d2b-a762-58ef-8541-8c06938ac9ff'::uuid),
            ('FOREX', 'GBP/USD', 'GBP/USD', '7d5205c3-6e92-59dc-bd3d-fafee2ec6d2f'::uuid),
            ('FOREX', 'USD/JPY', 'USD/JPY', '2d3adf2f-b36c-5890-9af9-480deed3b087'::uuid),
            ('FOREX', 'USD/CHF', 'USD/CHF', 'd85a212a-74eb-5edb-9e00-cd9ca15f1f99'::uuid),
            ('METALS', 'XAU/USD', 'XAU/USD', '677cdc56-265f-56fd-ba61-3fb0223f3c17'::uuid)
        ) AS v(market_code, canonical_symbol, provider_symbol, mapping_id)
    LOOP
        SELECT i.instrument_id INTO STRICT instrument
        FROM freyja2_instruments i
        JOIN freyja2_underlying_markets m ON m.id = i.underlying_market_id
        JOIN freyja2_product_types p ON p.id = i.product_type_id
        WHERE m.code = mapping.market_code AND p.code = 'SPOT' AND i.canonical_symbol = mapping.canonical_symbol;

        INSERT INTO freyja2_data_source_instruments
            (id, data_source_id, instrument_id, provider_symbol, purpose, is_active)
        VALUES (mapping.mapping_id, 'bf433b5c-68d0-543b-a154-85a3dd312a39', instrument, mapping.provider_symbol,
                'ANALYSIS'::freyja2_data_source_instrument_purpose, true);
    END LOOP;

    UPDATE alembic_version SET version_num = '0017_twelvedata_data_source'
    WHERE version_num = '0016_forex_metals_catalog';
END
$$;
