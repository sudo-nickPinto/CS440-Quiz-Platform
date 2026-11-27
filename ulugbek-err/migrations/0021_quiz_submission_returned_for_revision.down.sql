DELETE FROM schema_migrations
WHERE version = '0021_quiz_submission_returned_for_revision';

ALTER TABLE quiz_submission
    DROP COLUMN returned_for_revision;
