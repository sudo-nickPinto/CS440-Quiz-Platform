-- Reverts 0003.

DROP TABLE IF EXISTS result;
DROP TABLE IF EXISTS response;
DROP TABLE IF EXISTS session_question;
DROP TABLE IF EXISTS session_participant;
DROP TABLE IF EXISTS live_session;

DELETE FROM schema_migrations WHERE version = '0003_live_sessions';
