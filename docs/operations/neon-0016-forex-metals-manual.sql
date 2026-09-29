-- MARKET-DATA-TWELVEDATA-CATALOG-001 — migración 0016 aplicada a mano en Neon.
--
-- Equivale EXACTAMENTE a `alembic upgrade 0016_forex_metals_catalog` (un test lo comprueba
-- comparando el resultado de este script con el de Alembic). Solo datos: no cambia el
-- esquema y no toca ninguna fila existente. Añade el mercado METALS, 4 activos nuevos
-- (GBP, JPY, CHF, XAU), 4 instrumentos nuevos (GBP/USD, USD/JPY, USD/CHF en FOREX; XAU/USD
-- en METALS) y sus 20 asociaciones de temporalidad (5 cada uno), y sube alembic_version de
-- 0015 a 0016. EUR/USD y el mercado FOREX ya existían desde el catálogo v1 congelado: no se
-- tocan aquí.
--
-- Decisión de Jessica (29-09-2026): el oro (XAU/USD) no es un par de divisas y no se
-- cataloga como FOREX — va en su propio mercado, METALS.
--
-- Cómo usarlo: pégalo entero en el SQL Editor de Neon y ejecútalo una sola vez, contra la
-- base de producción. Es todo o nada (un único bloque): si algo no cuadra, aborta con un
-- mensaje y no cambia nada. Ejecutarlo dos veces también aborta, sin efectos.
DO $$
DECLARE
    spot_product uuid;
    row_data record;
    tf record;
BEGIN
    IF (SELECT version_num FROM alembic_version) <> '0015_context_snapshots' THEN
        RAISE EXCEPTION '0016 abortada: la base no está en 0015_context_snapshots (esperado). No se ha cambiado nada.';
    END IF;

    SELECT id INTO STRICT spot_product FROM freyja2_product_types WHERE code = 'SPOT';

    INSERT INTO freyja2_underlying_markets (id, code, display_name, is_active)
    VALUES ('f0724608-6071-5132-9863-c1757b0f973f', 'METALS', 'Metals', true);

    INSERT INTO freyja2_assets (id, code, display_name, is_active) VALUES
        ('a3ee2306-c46b-5e0c-a7cf-0b976ca0c50c', 'GBP', 'British pound', true),
        ('944d269e-b327-5d72-9cf1-dbfd34f33b87', 'JPY', 'Japanese yen', true),
        ('f052ea05-b06c-5242-a67a-d2c92888446b', 'CHF', 'Swiss franc', true),
        ('d9be2f45-2f77-51a3-baf3-d47dba962318', 'XAU', 'Gold', true);

    FOR row_data IN
        SELECT * FROM (VALUES
            ('7ad1433c-52dc-5c1d-b3cf-ac3e3f5681ec'::uuid, 'FOREX', 'GBP/USD',
             'a3ee2306-c46b-5e0c-a7cf-0b976ca0c50c'::uuid, (SELECT id FROM freyja2_assets WHERE code = 'USD')),
            ('9ccd7be2-5568-59e6-bdfe-9781f6472de6'::uuid, 'FOREX', 'USD/JPY',
             (SELECT id FROM freyja2_assets WHERE code = 'USD'), '944d269e-b327-5d72-9cf1-dbfd34f33b87'::uuid),
            ('e15922c2-061e-5f02-824d-44d3de6d8fbe'::uuid, 'FOREX', 'USD/CHF',
             (SELECT id FROM freyja2_assets WHERE code = 'USD'), 'f052ea05-b06c-5242-a67a-d2c92888446b'::uuid),
            ('0964c63d-3e63-5c9a-aa56-63c5dda6fa19'::uuid, 'METALS', 'XAU/USD',
             'd9be2f45-2f77-51a3-baf3-d47dba962318'::uuid, (SELECT id FROM freyja2_assets WHERE code = 'USD'))
        ) AS v(instrument_id, market_code, symbol, base_asset_id, quote_asset_id)
    LOOP
        INSERT INTO freyja2_instruments (
            instrument_id, underlying_market_id, product_type_id, canonical_symbol,
            base_asset_id, quote_asset_id, underlying_asset_id, underlying_instrument_id, is_active
        )
        SELECT row_data.instrument_id, m.id, spot_product, row_data.symbol,
               row_data.base_asset_id, row_data.quote_asset_id, NULL, NULL, true
        FROM freyja2_underlying_markets m WHERE m.code = row_data.market_code;

        FOR tf IN
            SELECT id FROM freyja2_timeframes WHERE code IN ('1m', '5m', '15m', '1h', '4h')
        LOOP
            INSERT INTO freyja2_instrument_timeframes (instrument_id, timeframe_id, is_active)
            VALUES (row_data.instrument_id, tf.id, true);
        END LOOP;
    END LOOP;

    UPDATE alembic_version SET version_num = '0016_forex_metals_catalog'
    WHERE version_num = '0015_context_snapshots';
END
$$;
