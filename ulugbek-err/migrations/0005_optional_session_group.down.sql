-- Undo 0005. This fails if any session has no group, because group_id
-- becomes required again. Give those sessions a group (or delete them) first.

ALTER TABLE live_session MODIFY group_id INT UNSIGNED NOT NULL;

DELETE FROM schema_migrations WHERE version = '0005_optional_session_group';
