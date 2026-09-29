-- 0002: quizzes, collaborators, group assignment, versions, questions, answer choices.
--
-- Versioning: a quiz_version with published_at = NULL is the editable draft.
-- Publishing sets published_at, after which the backend must not modify that
-- version or its questions/choices. Editing a published quiz creates version N+1.

CREATE TABLE quiz (
    quiz_id     INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    author_id   INT UNSIGNED NOT NULL,
    status      ENUM('DRAFT', 'PUBLISHED', 'ARCHIVED') NOT NULL DEFAULT 'DRAFT',
    -- PUBLIC = visible to members of the quiz's groups; PRIVATE = author,
    -- collaborators, and the groups' professor only.
    visibility  ENUM('PRIVATE', 'PUBLIC') NOT NULL DEFAULT 'PRIVATE',
    created_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                             ON UPDATE CURRENT_TIMESTAMP(3),

    CONSTRAINT fk_quiz_author
        FOREIGN KEY (author_id) REFERENCES account (account_id)
        ON DELETE RESTRICT
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Students (besides the author) who may edit the quiz. The professor of any
-- linked group can edit too; that comes from quiz_group, not from this table.
CREATE TABLE quiz_collaborator (
    quiz_id     INT UNSIGNED NOT NULL,
    account_id  INT UNSIGNED NOT NULL,
    added_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    PRIMARY KEY (quiz_id, account_id),
    CONSTRAINT fk_quiz_collaborator_quiz
        FOREIGN KEY (quiz_id) REFERENCES quiz (quiz_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_quiz_collaborator_account
        FOREIGN KEY (account_id) REFERENCES account (account_id)
        ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE quiz_group (
    quiz_id   INT UNSIGNED NOT NULL,
    group_id  INT UNSIGNED NOT NULL,

    PRIMARY KEY (quiz_id, group_id),
    CONSTRAINT fk_quiz_group_quiz
        FOREIGN KEY (quiz_id) REFERENCES quiz (quiz_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_quiz_group_group
        FOREIGN KEY (group_id) REFERENCES course_group (group_id)
        ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE quiz_version (
    quiz_version_id  INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    quiz_id          INT UNSIGNED NOT NULL,
    version_number   INT UNSIGNED NOT NULL,
    title            VARCHAR(200) NOT NULL,
    description      TEXT         NULL,
    created_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    published_at     DATETIME(3)  NULL,

    CONSTRAINT uq_quiz_version_number UNIQUE (quiz_id, version_number),
    CONSTRAINT ck_quiz_version_number CHECK (version_number >= 1),
    -- Versions used by a live_session cannot be deleted (see 0003), so this
    -- cascade only removes versions that were never played.
    CONSTRAINT fk_quiz_version_quiz
        FOREIGN KEY (quiz_id) REFERENCES quiz (quiz_id)
        ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE question (
    question_id         INT UNSIGNED      NOT NULL AUTO_INCREMENT PRIMARY KEY,
    quiz_version_id     INT UNSIGNED      NOT NULL,
    question_order      SMALLINT UNSIGNED NOT NULL,
    question_type       ENUM('MULTIPLE_CHOICE', 'FILL_IN_BLANK') NOT NULL
                        DEFAULT 'MULTIPLE_CHOICE',
    question_text       TEXT              NOT NULL,
    -- Shown to participants after the question closes.
    explanation         TEXT              NULL,
    time_limit_seconds  SMALLINT UNSIGNED NOT NULL DEFAULT 20,
    base_points         INT UNSIGNED      NOT NULL DEFAULT 1000,
    -- Per-question edit lock so two collaborators never edit the same question.
    -- The backend treats a lock older than its timeout as released.
    locked_by_id        INT UNSIGNED      NULL,
    locked_at           DATETIME(3)       NULL,
    updated_at          DATETIME(3)       NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                                          ON UPDATE CURRENT_TIMESTAMP(3),

    CONSTRAINT uq_question_order UNIQUE (quiz_version_id, question_order),
    CONSTRAINT ck_question_order CHECK (question_order >= 1),
    CONSTRAINT ck_question_time_limit CHECK (time_limit_seconds > 0),
    CONSTRAINT fk_question_quiz_version
        FOREIGN KEY (quiz_version_id) REFERENCES quiz_version (quiz_version_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_question_locked_by
        FOREIGN KEY (locked_by_id) REFERENCES account (account_id)
        ON DELETE SET NULL
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- For FILL_IN_BLANK questions, each accepted answer is a row with is_correct = TRUE.
-- Button color is derived from choice_order, so it is not stored.
CREATE TABLE answer_choice (
    choice_id     INT UNSIGNED     NOT NULL AUTO_INCREMENT PRIMARY KEY,
    question_id   INT UNSIGNED     NOT NULL,
    choice_order  TINYINT UNSIGNED NOT NULL,
    choice_text   VARCHAR(500)     NOT NULL,
    is_correct    BOOLEAN          NOT NULL DEFAULT FALSE,

    CONSTRAINT uq_answer_choice_order UNIQUE (question_id, choice_order),
    CONSTRAINT ck_answer_choice_order CHECK (choice_order >= 1),
    CONSTRAINT fk_answer_choice_question
        FOREIGN KEY (question_id) REFERENCES question (question_id)
        ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

INSERT INTO schema_migrations (version) VALUES ('0002_quizzes');
