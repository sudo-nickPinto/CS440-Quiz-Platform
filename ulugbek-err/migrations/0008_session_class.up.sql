-- 0008: a live session belongs to the class of the quiz it plays (task 6).
--
-- class_id is copied from the quiz when the session is created, so later
-- changes to the quiz never move a running or finished game to another class.
-- NULL means the session has no class and anyone with the join code can join,
-- exactly as before. (0007 is taken by the class membership PR, #58.)
--
-- Rules the backend enforces (not expressible here):
--   * Only an ACTIVE class_membership in class_id may join or answer; a
--     nonmember gets 403 not_class_member even with the join code.
--   * The join code stays numeric and unique among live sessions, as in 0003.

ALTER TABLE live_session
    ADD COLUMN class_id INT UNSIGNED NULL AFTER group_id,
    ADD CONSTRAINT fk_live_session_class
        FOREIGN KEY (class_id) REFERENCES class (class_id)
        ON DELETE RESTRICT,
    -- The class page's "active sessions" lookup.
    ADD INDEX idx_live_session_class_status (class_id, status);

INSERT INTO schema_migrations (version) VALUES ('0008_session_class');
