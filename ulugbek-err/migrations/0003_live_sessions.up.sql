-- 0003: live sessions, participants, per-question timing, responses, and results.
--
-- Rules the backend enforces (not expressible here without extra complexity):
--   * quiz_version_id must point to a published version.
--   * session_question.question_id must belong to the session's quiz version.
--   * response.choice_id must belong to the session_question's question.
--   * If group_id is set, only members of that group may join.
--   * The host presents only and is never a session_participant.

CREATE TABLE live_session (
    session_id              INT UNSIGNED      NOT NULL AUTO_INCREMENT PRIMARY KEY,
    quiz_version_id         INT UNSIGNED      NOT NULL,
    host_id                 INT UNSIGNED      NOT NULL,
    -- Nullable until the team decides whether sessions can run without a group.
    group_id                INT UNSIGNED      NULL,
    join_code               CHAR(6)           NOT NULL,
    status                  ENUM('LOBBY', 'ACTIVE', 'COMPLETED', 'CANCELLED') NOT NULL
                            DEFAULT 'LOBBY',
    current_question_order  SMALLINT UNSIGNED NULL,
    created_at              DATETIME(3)       NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    started_at              DATETIME(3)       NULL,
    ended_at                DATETIME(3)       NULL,
    -- Equals join_code while the session is running and NULL once it has
    -- finished, so codes are unique among running sessions but reusable later.
    -- Look up running sessions by this column.
    active_join_code        CHAR(6) GENERATED ALWAYS AS
                            (IF(status IN ('LOBBY', 'ACTIVE'), join_code, NULL)) STORED,

    CONSTRAINT uq_live_session_active_join_code UNIQUE (active_join_code),
    -- RESTRICT keeps played quiz versions from being deleted.
    CONSTRAINT fk_live_session_quiz_version
        FOREIGN KEY (quiz_version_id) REFERENCES quiz_version (quiz_version_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_live_session_host
        FOREIGN KEY (host_id) REFERENCES account (account_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_live_session_group
        FOREIGN KEY (group_id) REFERENCES course_group (group_id)
        ON DELETE RESTRICT
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Everyone who joined, including people who never answered.
-- Connection status and heartbeats live in server memory, not here.
CREATE TABLE session_participant (
    session_participant_id  INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    session_id              INT UNSIGNED NOT NULL,
    account_id              INT UNSIGNED NOT NULL,
    joined_at               DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    left_at                 DATETIME(3)  NULL,

    CONSTRAINT uq_session_participant UNIQUE (session_id, account_id),
    CONSTRAINT fk_session_participant_session
        FOREIGN KEY (session_id) REFERENCES live_session (session_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_session_participant_account
        FOREIGN KEY (account_id) REFERENCES account (account_id)
        ON DELETE RESTRICT
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- One row per question as it is played. closes_at is the server deadline;
-- answers submitted after it are rejected.
CREATE TABLE session_question (
    session_question_id  INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    session_id           INT UNSIGNED NOT NULL,
    question_id          INT UNSIGNED NOT NULL,
    status               ENUM('PENDING', 'OPEN', 'CLOSED') NOT NULL DEFAULT 'PENDING',
    opened_at            DATETIME(3)  NULL,
    closes_at            DATETIME(3)  NULL,
    closed_at            DATETIME(3)  NULL,

    CONSTRAINT uq_session_question UNIQUE (session_id, question_id),
    CONSTRAINT fk_session_question_session
        FOREIGN KEY (session_id) REFERENCES live_session (session_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_session_question_question
        FOREIGN KEY (question_id) REFERENCES question (question_id)
        ON DELETE RESTRICT
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- is_correct, points_awarded, and response_time_ms are stored exactly as the
-- server calculated them, so later scoring-formula changes don't rewrite history.
CREATE TABLE response (
    response_id             INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    session_participant_id  INT UNSIGNED NOT NULL,
    session_question_id     INT UNSIGNED NOT NULL,
    choice_id               INT UNSIGNED NULL,
    text_answer             VARCHAR(255) NULL,
    submitted_at            DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    response_time_ms        INT UNSIGNED NOT NULL,
    is_correct              BOOLEAN      NOT NULL,
    points_awarded          INT UNSIGNED NOT NULL DEFAULT 0,

    CONSTRAINT uq_response_once_per_question
        UNIQUE (session_participant_id, session_question_id),
    -- A response is either a chosen option or a typed answer, never both or neither.
    CONSTRAINT ck_response_answer
        CHECK ((choice_id IS NULL) <> (text_answer IS NULL)),
    CONSTRAINT ck_response_points CHECK (is_correct OR points_awarded = 0),
    CONSTRAINT fk_response_participant
        FOREIGN KEY (session_participant_id)
        REFERENCES session_participant (session_participant_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_response_session_question
        FOREIGN KEY (session_question_id)
        REFERENCES session_question (session_question_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_response_choice
        FOREIGN KEY (choice_id) REFERENCES answer_choice (choice_id)
        ON DELETE RESTRICT
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Final standing per participant, written when the session completes.
-- Ties share a rank and the next rank is skipped (1, 2, 3, 3, 5), i.e. RANK().
CREATE TABLE result (
    result_id               INT UNSIGNED      NOT NULL AUTO_INCREMENT PRIMARY KEY,
    session_participant_id  INT UNSIGNED      NOT NULL,
    total_score             INT UNSIGNED      NOT NULL DEFAULT 0,
    correct_count           SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    final_rank              SMALLINT UNSIGNED NOT NULL,
    computed_at             DATETIME(3)       NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    CONSTRAINT uq_result_participant UNIQUE (session_participant_id),
    CONSTRAINT ck_result_rank CHECK (final_rank >= 1),
    CONSTRAINT fk_result_participant
        FOREIGN KEY (session_participant_id)
        REFERENCES session_participant (session_participant_id)
        ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

INSERT INTO schema_migrations (version) VALUES ('0003_live_sessions');
