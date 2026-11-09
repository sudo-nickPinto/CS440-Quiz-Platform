-- 0012: independent optimistic revisions for collaborative question editing.
-- 0011 is reserved by the account-profile work developed in parallel.

ALTER TABLE question
    ADD COLUMN revision INT UNSIGNED NOT NULL DEFAULT 1 AFTER base_points,
    ADD CONSTRAINT ck_question_revision CHECK (revision >= 1);

INSERT INTO schema_migrations (version)
VALUES ('0012_question_revision');
