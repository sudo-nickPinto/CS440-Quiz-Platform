-- 0006: classes and class memberships (see docs/CLASS_APPROVAL.md, PR #51).
--
-- A class is a group of people who play quizzes together. Anyone can create one
-- and becomes its first ORGANIZER. People join with the class code or an invite.
--
-- These are new tables. The old course_group / group_membership / quiz_group
-- tables from 0001-0002 are left alone for now and will be dropped in a later
-- cleanup migration, once quizzes and sessions point at classes.
--
-- Rules the backend enforces (not expressible here):
--   * A class always keeps at least one ACTIVE ORGANIZER (409 last_organizer).
--   * Creating a class also creates the creator's ORGANIZER / ACTIVE / CREATOR
--     membership, in the same transaction.
--   * Role and status always come from class_membership, never from account.

CREATE TABLE class (
    class_id       INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name           VARCHAR(100) NOT NULL,
    created_by_id  INT UNSIGNED NOT NULL,
    -- 8-character class code, stored without the dash (shown as K7RM-Q4XP).
    -- NULL means the class has no code, for example after it is archived.
    join_code      CHAR(8)      NULL,
    joining_open   BOOLEAN      NOT NULL DEFAULT TRUE,
    -- Archiving keeps the class and its history; it is never deleted.
    archived_at    DATETIME(3)  NULL,
    created_at     DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at     DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                                ON UPDATE CURRENT_TIMESTAMP(3),

    CONSTRAINT uq_class_join_code UNIQUE (join_code),
    -- An archived class has no code and is closed to joining.
    CONSTRAINT ck_class_archived_closed
        CHECK (archived_at IS NULL OR (join_code IS NULL AND joining_open = FALSE)),
    CONSTRAINT fk_class_created_by
        FOREIGN KEY (created_by_id) REFERENCES account (account_id)
        ON DELETE RESTRICT
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- One row per person per class. Joining again, being invited again, leaving or
-- being removed updates this row instead of adding a new one, so past results
-- (session_participant, response, result) are never touched.
CREATE TABLE class_membership (
    membership_id  INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    class_id       INT UNSIGNED NOT NULL,
    account_id     INT UNSIGNED NOT NULL,
    role           ENUM('ORGANIZER', 'MEMBER') NOT NULL DEFAULT 'MEMBER',
    status         ENUM('INVITED', 'ACTIVE', 'LEFT', 'REMOVED') NOT NULL
                   DEFAULT 'ACTIVE',
    joined_via     ENUM('CREATOR', 'CODE', 'INVITE') NOT NULL DEFAULT 'CODE',
    -- Who sent the invite, if there was one.
    invited_by_id  INT UNSIGNED NULL,
    -- Who made the most recent change (removal or role change), and when.
    decided_by_id  INT UNSIGNED NULL,
    decided_at     DATETIME(3)  NULL,
    created_at     DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at     DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                                ON UPDATE CURRENT_TIMESTAMP(3),

    CONSTRAINT uq_class_membership UNIQUE (class_id, account_id),
    CONSTRAINT fk_class_membership_class
        FOREIGN KEY (class_id) REFERENCES class (class_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_class_membership_account
        FOREIGN KEY (account_id) REFERENCES account (account_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_class_membership_invited_by
        FOREIGN KEY (invited_by_id) REFERENCES account (account_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_class_membership_decided_by
        FOREIGN KEY (decided_by_id) REFERENCES account (account_id)
        ON DELETE SET NULL
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- "My classes" (and my pending invites).
CREATE INDEX idx_class_membership_account ON class_membership (account_id, status);
-- "The roster / the organizers of class X".
CREATE INDEX idx_class_membership_roster ON class_membership (class_id, status, role);

INSERT INTO schema_migrations (version) VALUES ('0006_classes');
