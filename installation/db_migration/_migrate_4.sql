BEGIN;

ALTER TABLE artefact_metadata DROP COLUMN cfg_name;

-- Delete compliance snapshots once because their data key has changed
-- -> Compliance snapshots will be created ad-hoc again eventually
DELETE FROM artefact_metadata WHERE type = 'compliance/snapshots';

COMMIT;
