-- Undo 0007. Preserve directly added memberships by treating them as code joins.

UPDATE class_membership
SET joined_via = 'CODE'
WHERE joined_via = 'ADDED';

ALTER TABLE class_membership
    MODIFY joined_via ENUM('CREATOR', 'CODE', 'INVITE')
        NOT NULL DEFAULT 'CODE';

DELETE FROM schema_migrations
WHERE version = '0007_direct_class_membership';
