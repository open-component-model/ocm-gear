BEGIN;

ALTER TABLE artefact_metadata ADD COLUMN new_id CHAR(32);

COMMIT;
