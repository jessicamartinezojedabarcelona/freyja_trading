-- POINT2-SNAPSHOT-001 — migración 0015 aplicada a mano en Neon.
--
-- Equivale EXACTAMENTE a `alembic upgrade 0015_context_snapshots` (un test compara el esquema
-- que deja este script con el que deja Alembic: columnas, restricciones, índice, trigger y
-- función). Crea la tabla freyja2_context_snapshots (instantáneas inmutables del contexto y la
-- tendencia con las que se evaluó una hipótesis), su índice, y el trigger que rechaza cualquier
-- UPDATE. No toca ninguna fila ni tabla existente y sube alembic_version de 0014 a 0015.
--
-- Cómo usarlo: pégalo entero en el SQL Editor de Neon y ejecútalo una sola vez, contra la base
-- de producción. Es todo o nada (un único bloque): si algo no cuadra, aborta con un mensaje y
-- no cambia nada. Ejecutarlo dos veces también aborta, sin efectos.
DO $script$
BEGIN
    IF (SELECT version_num FROM alembic_version) <> '0014_kraken_data_source' THEN
        RAISE EXCEPTION '0015 abortada: la base no está en 0014_kraken_data_source (esperado). No se ha cambiado nada.';
    END IF;

    CREATE TABLE freyja2_context_snapshots (
        id uuid NOT NULL,
        content_hash varchar(64) NOT NULL,
        snapshot_version varchar(32) NOT NULL,
        instrument_id uuid NOT NULL,
        data_source_id uuid NOT NULL,
        signal_timeframe_id uuid NOT NULL,
        context_timeframe_id uuid NOT NULL,
        observed_at timestamptz NOT NULL,
        computed_at timestamptz NOT NULL,
        signal_trend varchar(24) NOT NULL,
        context_trend varchar(24) NOT NULL,
        signal_data_quality freyja2_data_quality NOT NULL,
        context_data_quality freyja2_data_quality NOT NULL,
        market_session varchar(32),
        policy_version varchar(200),
        required_relationship varchar(24),
        orientation varchar(16) NOT NULL,
        policy_outcome varchar(24) NOT NULL,
        context_compatible boolean,
        reasons varchar(48)[] NOT NULL,
        document jsonb NOT NULL,
        CONSTRAINT pk_freyja2_context_snapshots PRIMARY KEY (id),
        CONSTRAINT uq_freyja2_context_snapshots_content_hash UNIQUE (content_hash),
        CONSTRAINT fk_freyja2_context_snapshots_instrument
            FOREIGN KEY (instrument_id) REFERENCES freyja2_instruments (instrument_id),
        CONSTRAINT fk_freyja2_context_snapshots_data_source
            FOREIGN KEY (data_source_id) REFERENCES freyja2_data_sources (id),
        CONSTRAINT fk_freyja2_context_snapshots_signal_timeframe
            FOREIGN KEY (signal_timeframe_id) REFERENCES freyja2_timeframes (id),
        CONSTRAINT fk_freyja2_context_snapshots_context_timeframe
            FOREIGN KEY (context_timeframe_id) REFERENCES freyja2_timeframes (id),
        CONSTRAINT ck_freyja2_context_snapshots_hash_length CHECK (char_length(content_hash) = 64),
        CONSTRAINT ck_freyja2_context_snapshots_computed_after_observed CHECK (computed_at >= observed_at),
        CONSTRAINT ck_freyja2_context_snapshots_trends CHECK (
            signal_trend IN ('UPTREND', 'DOWNTREND', 'RANGE', 'TRANSITION', 'INSUFFICIENT_DATA')
            AND context_trend IN ('UPTREND', 'DOWNTREND', 'RANGE', 'TRANSITION', 'INSUFFICIENT_DATA')),
        CONSTRAINT ck_freyja2_context_snapshots_relationship CHECK (
            required_relationship IS NULL
            OR required_relationship IN ('WITH_TREND', 'COUNTER_TREND', 'RANGE_ONLY', 'TRANSITION_ONLY', 'ANY')),
        CONSTRAINT ck_freyja2_context_snapshots_orientation CHECK (orientation IN ('BULLISH', 'BEARISH')),
        CONSTRAINT ck_freyja2_context_snapshots_outcome CHECK (
            policy_outcome IN ('COMPATIBLE', 'INCOMPATIBLE', 'INSUFFICIENT_CONTEXT')),
        CONSTRAINT ck_freyja2_context_snapshots_policy_pair CHECK (
            (policy_version IS NULL) = (required_relationship IS NULL)),
        CONSTRAINT ck_freyja2_context_snapshots_compatibility CHECK (
            (policy_outcome = 'COMPATIBLE' AND context_compatible IS TRUE)
            OR (policy_outcome = 'INCOMPATIBLE' AND context_compatible IS FALSE)
            OR (policy_outcome = 'INSUFFICIENT_CONTEXT' AND context_compatible IS NULL)),
        CONSTRAINT ck_freyja2_context_snapshots_reasons CHECK (
            (cardinality(reasons) = 0) = (policy_outcome = 'COMPATIBLE')),
        CONSTRAINT ck_freyja2_context_snapshots_document_object CHECK (jsonb_typeof(document) = 'object'),
        CONSTRAINT ck_freyja2_context_snapshots_document_matches_columns CHECK (
            document ->> 'snapshot_version' = snapshot_version
            AND document #>> '{observed,signal,trend}' = signal_trend
            AND document #>> '{observed,context,trend}' = context_trend
            AND document #>> '{observed,signal,data_quality}' = signal_data_quality::text
            AND document #>> '{observed,context,data_quality}' = context_data_quality::text
            AND (document #>> '{observed,market_session}') IS NOT DISTINCT FROM market_session
            AND (document #>> '{judged,policy_version}') IS NOT DISTINCT FROM policy_version
            AND (document #>> '{judged,required_relationship}') IS NOT DISTINCT FROM required_relationship
            AND document #>> '{judged,orientation}' = orientation
            AND document #>> '{judged,outcome}' = policy_outcome
            AND (document #>> '{judged,context_compatible}')::boolean IS NOT DISTINCT FROM context_compatible)
    );

    CREATE INDEX ix_freyja2_context_snapshots_instrument_observed
        ON freyja2_context_snapshots (instrument_id, observed_at);

    CREATE FUNCTION freyja2_context_snapshots_reject_update() RETURNS trigger AS $fn$
    BEGIN
        RAISE EXCEPTION
            'freyja2_context_snapshots rows are immutable: a snapshot cannot be updated'
            USING ERRCODE = 'restrict_violation';
    END;
    $fn$ LANGUAGE plpgsql;

    CREATE TRIGGER trg_freyja2_context_snapshots_immutable
        BEFORE UPDATE ON freyja2_context_snapshots
        FOR EACH ROW EXECUTE FUNCTION freyja2_context_snapshots_reject_update();

    UPDATE alembic_version SET version_num = '0015_context_snapshots';
END
$script$;
