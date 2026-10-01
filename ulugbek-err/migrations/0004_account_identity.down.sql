-- Undo 0004. account.auth0_sub still holds each account's first login.
-- Logins that were linked later are forgotten.

DROP TABLE account_identity;

DELETE FROM schema_migrations WHERE version = '0004_account_identity';
