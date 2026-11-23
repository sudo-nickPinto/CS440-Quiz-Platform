DELETE FROM schema_migrations
WHERE version = '0020_quiz_submission_rejection_comment';

ALTER TABLE quiz_submission
    DROP COLUMN rejection_comment;
