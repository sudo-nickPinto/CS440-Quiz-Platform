-- 0018: remember which memberships a roster import created.
--
-- class_membership.joined_via gains ROSTER: the student is in the class
-- because a row of an imported roster (or a roster email they signed up
-- with) added them. Before this, roster additions were stored as INVITE,
-- the same as an invitation the student accepted, so a corrected roster
-- email could not tell the two apart (review of PR #173).
--
-- Only ROSTER memberships can be removed when a corrected roster email
-- moves a row to another account. Rows added before this migration stay
-- INVITE and are never removed that way; their history can't be known.
--
-- Numbered 0018 because 0017 is taken by an open branch
-- (0017_trash_and_semester). The two don't depend on each other.

ALTER TABLE class_membership
    MODIFY joined_via ENUM('CREATOR', 'CODE', 'INVITE', 'ROSTER')
        NOT NULL DEFAULT 'CODE';

INSERT INTO schema_migrations (version) VALUES ('0018_roster_membership_source');
