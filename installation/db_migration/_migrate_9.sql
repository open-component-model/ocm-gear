BEGIN;

UPDATE artefact_metadata SET data = jsonb_set(data::jsonb, '{severity}'::text[], '"one-or-more-patchlevel-behind"'::jsonb) WHERE type = 'finding/osid' AND data->>'severity' IN ('more-than-one-patchlevel-behind', 'one-patchlevel-behind');

COMMIT;
