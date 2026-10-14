-- Undo 0006. is_active already matches status, so nothing is lost except the
-- difference between PENDING and DISABLED (both become is_active = FALSE).

ALTER TABLE account DROP CHECK chk_account_status_active;
ALTER TABLE account DROP COLUMN status;

DELETE FROM schema_migrations WHERE version = '0006_account_status';
