-- 0009: the profile a person fills in once, right after signing up.
--
-- Auth0 only collects email and password. The app then asks for a first and
-- last name and a preset avatar (a figure and a color, e.g. 'owl.sky').
-- display_name stays the name every screen shows; the backend sets it to
-- "first last" whenever the profile is saved.
--
-- Rules the backend enforces (not expressible here):
--   * Names are trimmed, 1 to 50 characters, with no control characters.
--   * avatar_key is NULL (initials) or one of the presets in backend/app/avatars.py.
--   * NULL first_name or last_name means the profile is not set up yet, so the
--     app shows the setup screen. Accounts made before 0009 start that way.

ALTER TABLE account
    ADD COLUMN first_name VARCHAR(50) NULL AFTER display_name,
    ADD COLUMN last_name  VARCHAR(50) NULL AFTER first_name,
    ADD COLUMN avatar_key VARCHAR(32) NULL AFTER last_name;

INSERT INTO schema_migrations (version) VALUES ('0009_account_profile');
