DELETE FROM schema_migrations
WHERE version = '0013_session_answer_correction';

DROP TABLE session_answer_correction;
DROP TABLE session_question_correct_choice;

ALTER TABLE live_session
    DROP FOREIGN KEY fk_live_session_rescored_by,
    DROP CHECK ck_live_session_score_revision,
    DROP COLUMN rescored_by_id,
    DROP COLUMN rescored_at,
    DROP COLUMN score_revision;
