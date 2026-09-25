-- MARKET-DATA-KRAKEN-REST-001 — migración 0014 aplicada a mano en Neon.
--
-- Equivale EXACTAMENTE a `alembic upgrade 0014_kraken_data_source` (un test lo comprueba
-- comparando el resultado de este script con el de Alembic). Solo datos: no cambia el
-- esquema y no toca ninguna fila existente. Añade la fuente KRAKEN y sus 4 mapeos de
-- análisis (Kraken llama XBT a Bitcoin) y sube alembic_version de 0013 a 0014.
--
-- Cómo usarlo: pégalo entero en el SQL Editor de Neon y ejecútalo una sola vez, contra la
-- base de producción. Es todo o nada (un único bloque): si algo no cuadra, aborta con un
-- mensaje y no cambia nada. Ejecutarlo dos veces también aborta, sin efectos.
DO $$
DECLARE
    instrument uuid;
    mapping record;
BEGIN
    IF (SELECT version_num FROM alembic_version) <> '0013_market_data_persistence' THEN
        RAISE EXCEPTION '0014 abortada: la base no está en 0013_market_data_persistence (esperado). No se ha cambiado nada.';
    END IF;

    INSERT INTO freyja2_data_sources (id, code, display_name, source_type, is_active)
    VALUES ('12fbd279-7908-55d0-ba1d-9f9b31d0a485', 'KRAKEN', 'Kraken', 'EXCHANGE', true);

    FOR mapping IN
        SELECT * FROM (VALUES
            ('BTC/USDT', 'XBTUSDT', 'a30d5af3-3cf1-5fb6-8268-5555fc04bfc1'::uuid),
            ('ETH/USDT', 'ETHUSDT', 'c48e224a-4164-57e7-ad7d-26abe6da3a4f'::uuid),
            ('SOL/USDT', 'SOLUSDT', 'b09c3874-f293-5126-9acb-aaec8ab6f2a1'::uuid),
            ('XRP/USDT', 'XRPUSDT', '655e5da1-eb87-5551-9789-4611a2637c65'::uuid)
        ) AS v(canonical_symbol, provider_symbol, mapping_id)
    LOOP
        SELECT i.instrument_id INTO STRICT instrument
        FROM freyja2_instruments i
        JOIN freyja2_underlying_markets m ON m.id = i.underlying_market_id
        JOIN freyja2_product_types p ON p.id = i.product_type_id
        WHERE m.code = 'CRYPTO' AND p.code = 'SPOT' AND i.canonical_symbol = mapping.canonical_symbol;

        INSERT INTO freyja2_data_source_instruments
            (id, data_source_id, instrument_id, provider_symbol, purpose, is_active)
        VALUES (mapping.mapping_id, '12fbd279-7908-55d0-ba1d-9f9b31d0a485', instrument, mapping.provider_symbol,
                'ANALYSIS'::freyja2_data_source_instrument_purpose, true);
    END LOOP;

    UPDATE alembic_version SET version_num = '0014_kraken_data_source'
    WHERE version_num = '0013_market_data_persistence';
END
$$;
