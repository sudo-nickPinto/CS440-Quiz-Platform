-- 0007: a live session can belong to a class (task 6).
--
-- The host picks the class when creating the session (quizzes have no class).
-- Only an active organizer of a non-archived class, or a global Admin, may pick
-- it. NULL is an open session: anyone with the join code can join, exactly as
-- before classes existed.
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

INSERT INTO schema_migrations (version) VALUES ('0007_session_class');
