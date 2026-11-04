DELETE FROM schema_migrations
WHERE version = '0010_quiz_submission';

DROP TABLE quiz_submission;
