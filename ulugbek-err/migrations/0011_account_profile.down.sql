-- Undo 0011. Accounts keep their display_name; only the profile fields go.

ALTER TABLE account
    DROP COLUMN avatar_key,
    DROP COLUMN last_name,
    DROP COLUMN first_name;

DELETE FROM schema_migrations WHERE version = '0011_account_profile';
