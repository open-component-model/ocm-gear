BEGIN;

-- Drop due_date from compliance snapshots
-- Delete compliance snapshots once because their data key has changed
-- -> Compliance snapshots will be created ad-hoc again eventually
DELETE FROM artefact_metadata WHERE type = 'compliance/snapshots';

-- Reset cache because it still contains `dso.model` references
DELETE FROM cache WHERE descriptor->>'type' = 'python-function' AND descriptor->>'function_name' = 'compliance_summary.component_datatype_summaries';

COMMIT;
