-- Undo 0015. Pending and rejected join requests become LEFT, so the person
-- can use the class code again; the imported rosters are deleted.

DELETE FROM schema_migrations WHERE version = '0015_class_roster';

DROP TABLE IF EXISTS class_roster_entry;

UPDATE class_membership
SET status = 'LEFT'
WHERE status IN ('REQUESTED', 'REJECTED');

ALTER TABLE class_membership
    MODIFY status ENUM('INVITED', 'ACTIVE', 'LEFT', 'REMOVED')
        NOT NULL DEFAULT 'ACTIVE';
