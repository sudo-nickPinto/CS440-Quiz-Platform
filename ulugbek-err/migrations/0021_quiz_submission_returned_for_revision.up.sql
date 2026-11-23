-- Record which withdrawals were explicitly sent back by an organizer.
ALTER TABLE quiz_submission
    ADD COLUMN returned_for_revision BOOLEAN NOT NULL DEFAULT FALSE;

INSERT INTO schema_migrations (version)
VALUES ('0021_quiz_submission_returned_for_revision');
