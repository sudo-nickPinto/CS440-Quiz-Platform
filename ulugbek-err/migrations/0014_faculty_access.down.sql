DELETE FROM schema_migrations
WHERE version = '0014_faculty_access';

DROP TABLE faculty_access_event;
