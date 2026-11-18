DELETE FROM schema_migrations WHERE version = '0015_question_bank';

ALTER TABLE question DROP FOREIGN KEY fk_question_bank_item;
ALTER TABLE question DROP INDEX idx_question_bank_item;
ALTER TABLE question DROP COLUMN bank_question_id;

DROP TABLE question_bank_item;
