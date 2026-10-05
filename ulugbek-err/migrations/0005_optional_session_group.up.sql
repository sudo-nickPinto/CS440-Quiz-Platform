-- 0005: a live session no longer has to belong to a group.
-- The MVP has one shared class and no group management, so there is no
-- course_group row for a session to point to. group_id stays in the table
-- for when multiple classes are added back.

ALTER TABLE live_session MODIFY group_id INT UNSIGNED NULL;

INSERT INTO schema_migrations (version) VALUES ('0005_optional_session_group');
