BEGIN;

-- The table may contain duplicates with the same newly calculated `new_id`, hence we must drop them
-- before promoting the `new_id` to a new primary key to ensure the unique constraint.
-- Collect (old) ids of the duplicates except the latest entry for each duplicate.
CREATE TABLE tmp_ids AS (SELECT id FROM (SELECT id, ROW_NUMBER() OVER(PARTITION BY new_id ORDER BY creation_date DESC) AS row_number FROM artefact_metadata) WHERE row_number > 1);
DELETE FROM artefact_metadata WHERE id IN (SELECT id FROM tmp_ids);
DROP table tmp_ids;

COMMIT;

BEGIN;

ALTER TABLE artefact_metadata DROP CONSTRAINT artefact_metadata_pkey;
ALTER TABLE artefact_metadata ADD PRIMARY KEY (new_id);
ALTER TABLE artefact_metadata DROP COLUMN id;
ALTER TABLE artefact_metadata RENAME COLUMN new_id TO id;

COMMIT;
