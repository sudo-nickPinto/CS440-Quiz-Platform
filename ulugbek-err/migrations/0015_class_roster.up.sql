-- 0015: class rosters and join requests that need an organizer's approval.
--
-- * class_membership.status gains REQUESTED (someone used the class code or
--   link and is waiting for an organizer) and REJECTED (an organizer turned
--   the request down). Neither gives any access; only ACTIVE does.
-- * class_roster_entry keeps the students an organizer imported from the
--   registrar's roster file. The file has a student ID and "Last,First" name
--   but usually no email, so an entry may not point at an account yet. A join
--   request from someone whose name or email matches an entry is approved
--   automatically.

ALTER TABLE class_membership
    MODIFY status ENUM('INVITED', 'ACTIVE', 'LEFT', 'REMOVED', 'REQUESTED', 'REJECTED')
        NOT NULL DEFAULT 'ACTIVE';

CREATE TABLE class_roster_entry (
    entry_id        INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    class_id        INT UNSIGNED NOT NULL,
    -- The registrar's student ID ("ID" column), kept as text.
    student_number  VARCHAR(20)  NOT NULL,
    first_name      VARCHAR(100) NOT NULL,
    last_name       VARCHAR(100) NOT NULL,
    -- Only when the file had an email column.
    email           VARCHAR(320) NULL,
    -- The account this entry was matched to, once there is one.
    account_id      INT UNSIGNED NULL,
    imported_by_id  INT UNSIGNED NULL,
    created_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                                 ON UPDATE CURRENT_TIMESTAMP(3),

    -- Importing the same roster again updates rows instead of adding them.
    CONSTRAINT uq_class_roster_student UNIQUE (class_id, student_number),
    CONSTRAINT fk_class_roster_class
        FOREIGN KEY (class_id) REFERENCES class (class_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_class_roster_account
        FOREIGN KEY (account_id) REFERENCES account (account_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_class_roster_imported_by
        FOREIGN KEY (imported_by_id) REFERENCES account (account_id)
        ON DELETE SET NULL,
    INDEX idx_class_roster_email (email),
    INDEX idx_class_roster_account (account_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

INSERT INTO schema_migrations (version) VALUES ('0015_class_roster');
