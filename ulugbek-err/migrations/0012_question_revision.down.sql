DELETE FROM schema_migrations
WHERE version = '0012_question_revision';

ALTER TABLE question
    DROP CHECK ck_question_revision,
    DROP COLUMN revision;
