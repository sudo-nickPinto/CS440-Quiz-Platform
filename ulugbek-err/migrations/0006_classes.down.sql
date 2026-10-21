-- Undo 0006. This deletes every class and membership.

DROP TABLE IF EXISTS class_membership;
DROP TABLE IF EXISTS class;

DELETE FROM schema_migrations WHERE version = '0006_classes';
