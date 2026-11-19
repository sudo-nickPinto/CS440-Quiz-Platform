-- Undo 0018. Roster-created memberships become INVITE again (what they
-- were stored as before 0018).

DELETE FROM schema_migrations WHERE version = '0018_roster_membership_source';

UPDATE class_membership
SET joined_via = 'INVITE'
WHERE joined_via = 'ROSTER';

ALTER TABLE class_membership
    MODIFY joined_via ENUM('CREATOR', 'CODE', 'INVITE')
        NOT NULL DEFAULT 'CODE';
