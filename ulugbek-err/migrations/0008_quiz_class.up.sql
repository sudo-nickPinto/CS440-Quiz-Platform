-- 0008: every quiz belongs to a class (V3 task 2).
--
-- quiz.class_id is the class that owns the quiz. Only that class's active
-- members can create quizzes in it, and only the owner and the class's
-- organizers can see a quiz. There is no app-wide quiz list any more, and
-- quiz.visibility = 'PUBLIC' no longer shows a quiz outside its class.
--
-- The column allows NULL for now, only so quizzes made before V3 survive this
-- migration. New quizzes always get a class. Before V3 is deployed, every
-- quiz still NULL here must be given a class or removed (see README.md), and
-- a later migration makes the column NOT NULL.

ALTER TABLE quiz
    ADD COLUMN class_id INT UNSIGNED NULL AFTER author_id,
    ADD CONSTRAINT fk_quiz_class
        FOREIGN KEY (class_id) REFERENCES class (class_id)
        ON DELETE RESTRICT,
    -- A class's quiz list, newest first.
    ADD INDEX idx_quiz_class_created (class_id, created_at, quiz_id);

-- Give a class to every quiz that was only ever played in one class. Quizzes
-- played in several classes, or never played in one, stay NULL for a person
-- to decide.
UPDATE quiz
JOIN (
    SELECT quiz_version.quiz_id, MIN(live_session.class_id) AS class_id
    FROM live_session
    JOIN quiz_version
        ON quiz_version.quiz_version_id = live_session.quiz_version_id
    WHERE live_session.class_id IS NOT NULL
    GROUP BY quiz_version.quiz_id
    HAVING COUNT(DISTINCT live_session.class_id) = 1
) AS played ON played.quiz_id = quiz.quiz_id
SET quiz.class_id = played.class_id;

INSERT INTO schema_migrations (version) VALUES ('0008_quiz_class');
