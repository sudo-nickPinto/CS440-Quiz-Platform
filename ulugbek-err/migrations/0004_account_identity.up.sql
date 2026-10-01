-- 0004: one account can have several Auth0 logins (e.g. Google and email/password).
-- Each login's Auth0 id (sub) now lives in account_identity instead of only on account.
-- account.auth0_sub is kept (the first login) so this migration changes no existing table.

CREATE TABLE account_identity (
    auth0_sub   VARCHAR(255) NOT NULL PRIMARY KEY,
    account_id  INT UNSIGNED NOT NULL,
    created_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    CONSTRAINT fk_account_identity_account
        FOREIGN KEY (account_id) REFERENCES account (account_id)
        ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE INDEX idx_account_identity_account ON account_identity (account_id);

-- Every existing account keeps its current login.
INSERT INTO account_identity (auth0_sub, account_id)
SELECT auth0_sub, account_id FROM account;

INSERT INTO schema_migrations (version) VALUES ('0004_account_identity');
