-- 0006: account.status tells a pending signup apart from a disabled account.
--   PENDING  = an email/password signup waiting for an Admin to approve it
--   ACTIVE   = can use the app
--   DISABLED = turned off on purpose; approving or rejecting signups never touches it
-- is_active stays so existing code keeps working. It must always equal
-- (status = 'ACTIVE'); the CHECK rule enforces that on MySQL 8.0.16+.

ALTER TABLE account
    ADD COLUMN status ENUM('PENDING', 'ACTIVE', 'DISABLED') NOT NULL DEFAULT 'ACTIVE'
    AFTER account_type;

-- Existing inactive accounts can't be told apart, so treat them as disabled.
-- An Admin can set a real pending signup back to PENDING by hand.
UPDATE account SET status = IF(is_active, 'ACTIVE', 'DISABLED');

ALTER TABLE account
    ADD CONSTRAINT chk_account_status_active CHECK (is_active = (status = 'ACTIVE'));

INSERT INTO schema_migrations (version) VALUES ('0006_account_status');
