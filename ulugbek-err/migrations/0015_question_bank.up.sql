CREATE TABLE question_bank_item (
    bank_question_id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    owner_id INT UNSIGNED NOT NULL,
    source_class_id INT UNSIGNED NULL,
    source_quiz_id INT UNSIGNED NULL,
    source_question_id INT UNSIGNED NULL,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    question_type ENUM('MULTIPLE_CHOICE', 'FILL_IN_BLANK') NOT NULL DEFAULT 'MULTIPLE_CHOICE',
    question_text TEXT NOT NULL,
    explanation TEXT NULL,
    choices_json JSON NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT fk_bank_owner FOREIGN KEY (owner_id) REFERENCES account(account_id) ON DELETE CASCADE,
    CONSTRAINT fk_bank_class FOREIGN KEY (source_class_id) REFERENCES class(class_id) ON DELETE SET NULL,
    CONSTRAINT fk_bank_quiz FOREIGN KEY (source_quiz_id) REFERENCES quiz(quiz_id) ON DELETE SET NULL,
    UNIQUE KEY uq_bank_source_question (source_question_id),
    INDEX idx_bank_owner_current (owner_id, is_current, updated_at),
    INDEX idx_bank_class_current (source_class_id, is_current, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE question
    ADD COLUMN bank_question_id INT UNSIGNED NULL AFTER question_id,
    ADD CONSTRAINT fk_question_bank_item
        FOREIGN KEY (bank_question_id) REFERENCES question_bank_item(bank_question_id)
        ON DELETE SET NULL,
    ADD INDEX idx_question_bank_item (bank_question_id);

INSERT INTO schema_migrations (version) VALUES ('0015_question_bank');
