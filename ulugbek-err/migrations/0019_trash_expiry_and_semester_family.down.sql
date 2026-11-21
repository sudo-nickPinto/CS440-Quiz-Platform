-- Undo 0019. Semester links and the permanent-delete mark go away.
-- Anything already purged stays in the trash (deleted_at is still set).

DELETE FROM schema_migrations WHERE version = '0019_trash_expiry_and_semester_family';

ALTER TABLE live_session DROP COLUMN purged_at;

ALTER TABLE quiz DROP COLUMN purged_at;

ALTER TABLE class
    DROP FOREIGN KEY fk_class_parent,
    DROP INDEX idx_class_parent,
    DROP COLUMN purged_at,
    DROP COLUMN parent_class_id;
