DELETE FROM schema_migrations
WHERE version = '0009_quiz_collaboration';

ALTER TABLE quiz_collaborator
    DROP FOREIGN KEY fk_quiz_collaborator_revoked_by,
    DROP FOREIGN KEY fk_quiz_collaborator_shared_by,
    DROP INDEX idx_quiz_collaborator_active,
    DROP COLUMN revoked_by_id,
    DROP COLUMN revoked_at,
    DROP COLUMN shared_by_id,
    DROP COLUMN permission,
    CHANGE COLUMN created_at added_at DATETIME(3) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(3);

ALTER TABLE quiz
    DROP CHECK ck_quiz_revision,
    DROP COLUMN revision;
