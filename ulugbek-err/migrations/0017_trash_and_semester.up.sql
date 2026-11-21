-- 0017: a trash for classes, quizzes and hosted sessions, and a semester on
-- each class.
--
-- * deleted_at on class, quiz and live_session is NULL normally and set when
--   someone moves the row to the trash. Nothing is really deleted, because
--   results and history point at these rows, so restoring sets it back to
--   NULL. The backend leaves trashed rows out of every list and report.
-- * class.semester is a label like "Fall 2026". The same course runs again
--   each semester as a separate class with its own code, roster and grades.
--   Classes made before this migration have no semester (NULL).

ALTER TABLE class
    ADD COLUMN semester   VARCHAR(30) NULL AFTER name,
    ADD COLUMN deleted_at DATETIME(3) NULL AFTER archived_at;

ALTER TABLE quiz
    ADD COLUMN deleted_at DATETIME(3) NULL AFTER visibility;

ALTER TABLE live_session
    ADD COLUMN deleted_at DATETIME(3) NULL AFTER rescored_by_id;

INSERT INTO schema_migrations (version) VALUES ('0017_trash_and_semester');
