-- 0001: accounts, course groups, and group membership.
-- Also creates schema_migrations, which records which migrations have been applied.

CREATE TABLE schema_migrations (
    version     VARCHAR(100) NOT NULL PRIMARY KEY,
    applied_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- One row per person who has logged in through Auth0 (Google).
CREATE TABLE account (
    account_id    INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    auth0_sub     VARCHAR(255) NOT NULL,
    email         VARCHAR(320) NOT NULL,
    display_name  VARCHAR(100) NOT NULL,
    -- NULL until the user picks Student or Professor at first login.
    -- ADMINISTRATOR is only ever set manually by the team.
    account_type  ENUM('STUDENT', 'PROFESSOR', 'ADMINISTRATOR') NULL,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    CONSTRAINT uq_account_auth0_sub UNIQUE (auth0_sub),
    CONSTRAINT uq_account_email     UNIQUE (email)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- A class (e.g. "CS440 Fall 2026"), run by exactly one teacher.
CREATE TABLE course_group (
    group_id    INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    group_name  VARCHAR(100) NOT NULL,
    teacher_id  INT UNSIGNED NOT NULL,
    created_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    CONSTRAINT fk_course_group_teacher
        FOREIGN KEY (teacher_id) REFERENCES account (account_id)
        ON DELETE RESTRICT
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE group_membership (
    group_id    INT UNSIGNED NOT NULL,
    account_id  INT UNSIGNED NOT NULL,
    joined_at   DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    PRIMARY KEY (group_id, account_id),
    CONSTRAINT fk_group_membership_group
        FOREIGN KEY (group_id) REFERENCES course_group (group_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_group_membership_account
        FOREIGN KEY (account_id) REFERENCES account (account_id)
        ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

INSERT INTO schema_migrations (version) VALUES ('0001_accounts_and_groups');
