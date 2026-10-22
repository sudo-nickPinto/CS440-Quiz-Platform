-- 0007: distinguish direct roster additions from invitations and code joins.

ALTER TABLE class_membership
    MODIFY joined_via ENUM('CREATOR', 'CODE', 'INVITE', 'ADDED')
        NOT NULL DEFAULT 'CODE';

INSERT INTO schema_migrations (version)
VALUES ('0007_direct_class_membership');
