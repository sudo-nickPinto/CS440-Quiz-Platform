-- Undo 0017. Everything in the trash comes back, and semester labels are lost.

DELETE FROM schema_migrations WHERE version = '0017_trash_and_semester';

ALTER TABLE live_session DROP COLUMN deleted_at;

ALTER TABLE quiz DROP COLUMN deleted_at;

ALTER TABLE class
    DROP COLUMN deleted_at,
    DROP COLUMN semester;
