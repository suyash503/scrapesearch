#!/bin/sh
# Runs once, when the MySQL container initializes an EMPTY data volume (docker-entrypoint-initdb.d).
# Django's test runner creates and drops a database named test_<NAME>, so the app user needs rights
# on that database too. Only that one: it still can't touch any other database.
set -eu
mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e \
  "GRANT ALL PRIVILEGES ON \`test_${MYSQL_DATABASE}\`.* TO '${MYSQL_USER}'@'%';"
