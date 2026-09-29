-- Reverts 0002. Run 0003 down first.

DROP TABLE IF EXISTS answer_choice;
DROP TABLE IF EXISTS question;
DROP TABLE IF EXISTS quiz_version;
DROP TABLE IF EXISTS quiz_group;
DROP TABLE IF EXISTS quiz_collaborator;
DROP TABLE IF EXISTS quiz;

DELETE FROM schema_migrations WHERE version = '0002_quizzes';
