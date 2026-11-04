-- 0010: class quiz submission and approval foundation (V3 task 4).
--
-- quiz.class_id is the authoritative class. quiz_submission.class_id repeats
-- it only for class-scoped indexes and active-submission uniqueness; backend
-- code must verify the values match before inserting a row.

CREATE TABLE quiz_submission (
    submission_id    INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    class_id         INT UNSIGNED NOT NULL,
    quiz_version_id  INT UNSIGNED NOT NULL,
    submitted_by_id  INT UNSIGNED NOT NULL,
    status           ENUM('PENDING', 'APPROVED', 'REJECTED', 'WITHDRAWN')
                     NOT NULL DEFAULT 'PENDING',
    decided_by_id    INT UNSIGNED NULL,
    submitted_at     DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    decided_at       DATETIME(3) NULL,
    -- MySQL unique keys allow many NULL values. Only pending and approved rows
    -- therefore occupy the active uniqueness slot for a class/version pair.
    active_version_id INT UNSIGNED GENERATED ALWAYS AS (
        CASE
            WHEN status IN ('PENDING', 'APPROVED') THEN quiz_version_id
            ELSE NULL
        END
    ) STORED,

    CONSTRAINT uq_quiz_submission_active
        UNIQUE (class_id, active_version_id),
    CONSTRAINT ck_quiz_submission_decision CHECK (
        (status = 'PENDING' AND decided_by_id IS NULL AND decided_at IS NULL)
        OR
        (status IN ('APPROVED', 'REJECTED', 'WITHDRAWN')
         AND decided_by_id IS NOT NULL AND decided_at IS NOT NULL)
    ),
    CONSTRAINT fk_quiz_submission_class
        FOREIGN KEY (class_id) REFERENCES class (class_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_quiz_submission_version
        FOREIGN KEY (quiz_version_id) REFERENCES quiz_version (quiz_version_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_quiz_submission_submitted_by
        FOREIGN KEY (submitted_by_id) REFERENCES account (account_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_quiz_submission_decided_by
        FOREIGN KEY (decided_by_id) REFERENCES account (account_id)
        ON DELETE RESTRICT,
    INDEX idx_quiz_submission_class_status_newest
        (class_id, status, submitted_at, submission_id),
    INDEX idx_quiz_submission_member_newest
        (class_id, submitted_by_id, submitted_at, submission_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

INSERT INTO schema_migrations (version)
VALUES ('0010_quiz_submission');
