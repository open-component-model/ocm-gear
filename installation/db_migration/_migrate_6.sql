BEGIN;

ALTER TABLE artefact_metadata ADD COLUMN allowed_processing_time VARCHAR(16);

-- Rename compliance snapshot property from `latest_processing_date` -> `due_date`
UPDATE artefact_metadata SET data = jsonb_set(data::jsonb #- '{latest_processing_date}', '{due_date}', data::jsonb #> '{latest_processing_date}') WHERE type = 'compliance/snapshots';

UPDATE artefact_metadata SET allowed_processing_time = '0s' WHERE type != 'rescorings' AND data->>'severity' IN ('BLOCKER', 'scanner-limitation', 'missing-linting');
UPDATE artefact_metadata SET allowed_processing_time = '2592000s' WHERE type != 'rescorings' AND data->>'severity' IN ('CRITICAL', 'HIGH');
UPDATE artefact_metadata SET allowed_processing_time = '7776000s' WHERE type != 'rescorings' AND data->>'severity' = 'MEDIUM';
UPDATE artefact_metadata SET allowed_processing_time = '10368000s' WHERE type != 'rescorings' AND data->>'severity' = 'LOW';

UPDATE artefact_metadata SET data = jsonb_set(data::jsonb, '{allowed_processing_time}'::text[], '"0s"'::jsonb) WHERE type = 'rescorings' AND data->>'severity' IN ('BLOCKER', 'scanner-limitation', 'missing-linting');
UPDATE artefact_metadata SET data = jsonb_set(data::jsonb, '{allowed_processing_time}'::text[], '"2592000s"'::jsonb) WHERE type = 'rescorings' AND data->>'severity' IN ('CRITICAL', 'HIGH');
UPDATE artefact_metadata SET data = jsonb_set(data::jsonb, '{allowed_processing_time}'::text[], '"7776000s"'::jsonb) WHERE type = 'rescorings' AND data->>'severity' = 'MEDIUM';
UPDATE artefact_metadata SET data = jsonb_set(data::jsonb, '{allowed_processing_time}'::text[], '"10368000s"'::jsonb) WHERE type = 'rescorings' AND data->>'severity' = 'LOW';

COMMIT;
