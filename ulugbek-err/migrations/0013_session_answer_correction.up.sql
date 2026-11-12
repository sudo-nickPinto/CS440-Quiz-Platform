-- 0013: audited, session-specific correct-answer corrections and rescoring.

ALTER TABLE live_session
    ADD COLUMN score_revision SMALLINT UNSIGNED NOT NULL DEFAULT 0 AFTER ended_at,
    ADD COLUMN rescored_at DATETIME(3) NULL AFTER score_revision,
    ADD COLUMN rescored_by_id INT UNSIGNED NULL AFTER rescored_at,
    ADD CONSTRAINT ck_live_session_score_revision CHECK (score_revision >= 0),
    ADD CONSTRAINT fk_live_session_rescored_by
        FOREIGN KEY (rescored_by_id) REFERENCES account (account_id)
        ON DELETE RESTRICT;

CREATE TABLE session_question_correct_choice (
    session_question_id INT UNSIGNED NOT NULL,
    choice_id           INT UNSIGNED NOT NULL,

    PRIMARY KEY (session_question_id, choice_id),
    CONSTRAINT fk_session_correct_choice_question
        FOREIGN KEY (session_question_id)
        REFERENCES session_question (session_question_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_session_correct_choice_choice
        FOREIGN KEY (choice_id) REFERENCES answer_choice (choice_id)
        ON DELETE RESTRICT
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE session_answer_correction (
    correction_id              INT UNSIGNED      NOT NULL AUTO_INCREMENT PRIMARY KEY,
    session_id                 INT UNSIGNED      NOT NULL,
    session_question_id        INT UNSIGNED      NOT NULL,
    selected_choice_id         INT UNSIGNED      NOT NULL,
    correction_mode            ENUM('REPLACE', 'ADD') NOT NULL,
    previous_correct_choice_ids JSON             NOT NULL,
    corrected_choice_ids        JSON             NOT NULL,
    corrected_by_id            INT UNSIGNED      NOT NULL,
    score_revision             SMALLINT UNSIGNED NOT NULL,
    corrected_at               DATETIME(3)       NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    CONSTRAINT uq_session_answer_correction_revision
        UNIQUE (session_id, score_revision),
    CONSTRAINT ck_session_answer_correction_revision
        CHECK (score_revision >= 1),
    CONSTRAINT fk_session_answer_correction_session
        FOREIGN KEY (session_id) REFERENCES live_session (session_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_session_answer_correction_question
        FOREIGN KEY (session_question_id)
        REFERENCES session_question (session_question_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_session_answer_correction_selected_choice
        FOREIGN KEY (selected_choice_id) REFERENCES answer_choice (choice_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_session_answer_correction_actor
        FOREIGN KEY (corrected_by_id) REFERENCES account (account_id)
        ON DELETE RESTRICT,

    INDEX idx_session_answer_correction_question
        (session_question_id, corrected_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

INSERT INTO schema_migrations (version)
VALUES ('0013_session_answer_correction');
