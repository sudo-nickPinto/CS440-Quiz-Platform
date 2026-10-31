-- Undo 0008. Quizzes keep everything except which class owns them.
-- Each step is its own statement: the index backs the foreign key, and dropping
-- only the column would leave the index behind on (created_at, quiz_id).

ALTER TABLE quiz DROP FOREIGN KEY fk_quiz_class;
ALTER TABLE quiz DROP INDEX idx_quiz_class_created;
ALTER TABLE quiz DROP COLUMN class_id;

DELETE FROM schema_migrations WHERE version = '0008_quiz_class';
