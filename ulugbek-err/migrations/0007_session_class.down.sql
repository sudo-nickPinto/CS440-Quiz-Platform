-- Undo 0007. Sessions keep everything except which class they belonged to.
-- Each step is its own statement: the index backs the foreign key, and dropping
-- only the column would leave the index behind on (status).

ALTER TABLE live_session DROP FOREIGN KEY fk_live_session_class;
ALTER TABLE live_session DROP INDEX idx_live_session_class_status;
ALTER TABLE live_session DROP COLUMN class_id;

DELETE FROM schema_migrations WHERE version = '0007_session_class';
