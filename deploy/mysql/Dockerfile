# MySQL with InnoDB encryption at rest (docs/DEPLOYMENT.md, "Database
# encryption at rest"). The keyring component holds the master key; it lives
# in its own volume (/var/lib/mysql-keyring), apart from the data volume.
FROM mysql:8.0

# The server loads the keyring component from this manifest, next to mysqld.
COPY mysqld.my /usr/sbin/mysqld.my
# Where the component keeps the key file.
COPY component_keyring_file.cnf /usr/lib64/mysql/plugin/component_keyring_file.cnf

# Owned by mysql here, so the named volume mounted on it starts out owned by
# mysql too (Docker copies the image directory's ownership into a new volume).
# The empty key file is created up front: the image's entrypoint first runs
# mysqld as root to read its settings, and would otherwise create the file
# owned by root, which the server (running as mysql) then can't read.
RUN mkdir -p /var/lib/mysql-keyring \
    && touch /var/lib/mysql-keyring/component_keyring_file \
    && chown -R mysql:mysql /var/lib/mysql-keyring \
    && chmod 750 /var/lib/mysql-keyring \
    && chmod 600 /var/lib/mysql-keyring/component_keyring_file
