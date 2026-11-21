-- 0019: trash expires, and semesters of one course stay linked.
--
-- * purged_at is set when a trashed row is retired (by hand, or 30 days
--   after deleted_at). The row stays, because results still point at it,
--   but it leaves the trash and cannot be restored.
-- * class.parent_class_id points a later semester at the first class of
--   that course. NULL means this class is the first one.

ALTER TABLE class
    ADD COLUMN parent_class_id INT UNSIGNED NULL AFTER semester,
    ADD COLUMN purged_at DATETIME(3) NULL AFTER deleted_at,
    ADD INDEX idx_class_parent (parent_class_id),
    ADD CONSTRAINT fk_class_parent
        FOREIGN KEY (parent_class_id) REFERENCES class (class_id)
        ON DELETE RESTRICT;

ALTER TABLE quiz
    ADD COLUMN purged_at DATETIME(3) NULL AFTER deleted_at;

ALTER TABLE live_session
    ADD COLUMN purged_at DATETIME(3) NULL AFTER deleted_at;

INSERT INTO schema_migrations (version) VALUES ('0019_trash_expiry_and_semester_family');
