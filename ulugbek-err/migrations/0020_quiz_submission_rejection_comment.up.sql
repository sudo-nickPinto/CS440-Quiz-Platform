-- Store optional feedback on the audited rejection.
ALTER TABLE quiz_submission
    ADD COLUMN rejection_comment VARCHAR(1000) NULL;

INSERT INTO schema_migrations (version)
VALUES ('0020_quiz_submission_rejection_comment');
