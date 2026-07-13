-- ============================================================================
-- 020_broker_icon.sql — add a logo/icon column to the brokers dimension.
--
-- The brokers directory (broker code → firm name) is now refreshed live from
-- SMTM's authoritative /general/broker_list (see refresh_brokers.py) instead of
-- the hand-seeded hamroshare list in 015_brokers.sql. SMTM also ships an
-- official logo path per broker, stored here so the surveillance board / broker
-- tools can show a broker's mark. The live refresh sets source='smtm'.
-- Idempotent.
-- ============================================================================

ALTER TABLE brokers ADD COLUMN IF NOT EXISTS icon TEXT;
