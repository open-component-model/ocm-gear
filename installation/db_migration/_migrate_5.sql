BEGIN;

-- Drop correlation-id from compliance snapshots
UPDATE artefact_metadata SET data = data::jsonb #- '{correlation_id}' WHERE type = 'compliance/snapshots';

COMMIT;
