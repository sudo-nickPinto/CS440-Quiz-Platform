-- 0014: let faculty grant and remove faculty status in the app (issue #116),
-- with an append-only history of every change.
--
-- Faculty status itself stays where it was: account.account_type =
-- 'ADMINISTRATOR'. This table only records who changed it and when.

CREATE TABLE faculty_access_event (
    event_id    INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    -- The account whose faculty status changed.
    account_id  INT UNSIGNED NOT NULL,
    action      ENUM('GRANTED', 'REVOKED') NOT NULL,
    -- The faculty member who made the change.
    actor_id    INT UNSIGNED NOT NULL,
    occurred_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    CONSTRAINT fk_faculty_access_event_account
        FOREIGN KEY (account_id) REFERENCES account (account_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_faculty_access_event_actor
        FOREIGN KEY (actor_id) REFERENCES account (account_id)
        ON DELETE RESTRICT,
    INDEX idx_faculty_access_event_account
        (account_id, occurred_at, event_id),
    INDEX idx_faculty_access_event_time
        (occurred_at, event_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

INSERT INTO schema_migrations (version)
VALUES ('0014_faculty_access');
