DELETE FROM schema_migrations
WHERE version = '0008_quiz_collaboration';

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
    DROP FOREIGN KEY fk_quiz_class,
    DROP CHECK ck_quiz_revision,
    DROP INDEX idx_quiz_class_created,
    DROP COLUMN revision,
    DROP COLUMN class_id;
