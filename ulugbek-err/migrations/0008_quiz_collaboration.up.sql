-- 0008: V3 class-scoped quiz collaboration and optimistic revision checks.
--
-- quiz.class_id is temporarily nullable so existing installations can assign
-- their pre-V3 quizzes before a later migration enforces class-only creation.

ALTER TABLE quiz
    ADD COLUMN class_id INT UNSIGNED NULL AFTER author_id,
    ADD COLUMN revision INT UNSIGNED NOT NULL DEFAULT 1 AFTER class_id,
    ADD CONSTRAINT fk_quiz_class
        FOREIGN KEY (class_id) REFERENCES class (class_id)
        ON DELETE RESTRICT,
    ADD CONSTRAINT ck_quiz_revision CHECK (revision >= 1),
    ADD INDEX idx_quiz_class_created (class_id, created_at, quiz_id);

ALTER TABLE quiz_collaborator
    CHANGE COLUMN added_at created_at DATETIME(3) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(3),
    ADD COLUMN permission ENUM('EDITOR') NOT NULL DEFAULT 'EDITOR'
        AFTER account_id,
    ADD COLUMN shared_by_id INT UNSIGNED NULL AFTER permission,
    ADD COLUMN revoked_at DATETIME(3) NULL AFTER created_at,
    ADD COLUMN revoked_by_id INT UNSIGNED NULL AFTER revoked_at;

-- Preserve any legacy collaborator rows by attributing the original share to
-- the quiz owner before making shared_by_id required.
UPDATE quiz_collaborator AS collaborator
JOIN quiz ON quiz.quiz_id = collaborator.quiz_id
SET collaborator.shared_by_id = quiz.author_id
WHERE collaborator.shared_by_id IS NULL;

ALTER TABLE quiz_collaborator
    MODIFY COLUMN shared_by_id INT UNSIGNED NOT NULL,
    ADD CONSTRAINT fk_quiz_collaborator_shared_by
        FOREIGN KEY (shared_by_id) REFERENCES account (account_id)
        ON DELETE RESTRICT,
    ADD CONSTRAINT fk_quiz_collaborator_revoked_by
        FOREIGN KEY (revoked_by_id) REFERENCES account (account_id)
        ON DELETE RESTRICT,
    ADD INDEX idx_quiz_collaborator_active
        (quiz_id, revoked_at, account_id);

INSERT INTO schema_migrations (version)
VALUES ('0008_quiz_collaboration');
