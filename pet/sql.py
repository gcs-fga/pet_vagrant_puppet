# vim:ts=2:sw=2:et:ai:sts=2
# Copyright 2011, Ansgar Burchardt <ansgar@debian.org>
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

"""
SQL helper functions for database maintainance.
"""

from pet.exceptions import *

import sqlalchemy.sql

class DBUpdate(object):
  def __init__(self, schema_version, statements=None, callable=None):
    self.schema_version = schema_version
    self.statements = statements
    self.callable = callable
  def run(self, connection):
    print "Upgrading to schema version {0}".format(self.schema_version)
    with connection.begin():
      if self.schema_version != 1:
        old_version = connection.execute("SELECT value FROM config WHERE key = 'schema_version'").scalar()
        if int(old_version) + 1 != self.schema_version:
          raise DatabaseError("Tried to update schema from {0} to {1}".format(old_version, self.schema_version))
      if self.statements:
        for s in self.statements:
          connection.execute(s)
      if self.callable:
        self.callable(connection)
      connection.execute(
          sqlalchemy.sql.text(
            "UPDATE config SET value = :version WHERE key = 'schema_version'"),
          version=self.schema_version)

class DBUpdater(object):
  __shared = {'updates': {}}
  def __init__(self):
    self.__dict__ = self.__shared
  def add(self, schema_version, statements=None, callable=None):
    update = DBUpdate(schema_version, statements, callable=callable)
    self.updates[schema_version] = update
  def run(self, engine, create_database=False):
    connection = engine.connect()
    try:
      if create_database:
        old_version = 0
      else:
        old_version = int(connection.execute("SELECT value FROM config WHERE key = 'schema_version'").scalar())
      new_version = max(self.updates.keys())
      for v in range(old_version + 1, new_version + 1):
        self.updates[v].run(connection)
    finally:
      connection.close()

DBUpdater().add(1, statements=[
  """
  CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT
  )""",
  """INSERT INTO config (key, value) VALUES ('schema_version', '1')""",
  ])

DBUpdater().add(2, statements=[
  """
  CREATE TABLE repository (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    root TEXT NOT NULL,
    web_root TEXT NOT NULL
  )""",
  """
  CREATE TABLE package (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    repository_id INT NOT NULL REFERENCES repository(id),
    UNIQUE (name, repository_id)
  )""",
  """
  CREATE TABLE named_tree (
    id SERIAL PRIMARY KEY,
    package_id INT NOT NULL REFERENCES package(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('branch', 'tag')),
    name TEXT, -- NULL means trunk
    commit_id TEXT NOT NULL
  )""",
  """
  COMMENT ON TABLE named_tree IS 'branches, tags and trunk are named_trees'
  """,
  """
  CREATE TABLE changelog (
    id SERIAL PRIMARY KEY,
    named_tree_id INT NOT NULL REFERENCES named_tree(id) ON DELETE CASCADE,
    changelog TEXT NOT NULL
  )""",
  """
  CREATE TABLE patch (
    named_tree_id INT NOT NULL REFERENCES named_tree(id) ON DELETE CASCADE,
    name TEXT NOT NULL
  )""",
  ])

DBUpdater().add(3, statements=[
  "DROP TABLE changelog",
  """
  CREATE TABLE file (
    id SERIAL PRIMARY KEY,
    named_tree_id INT NOT NULL REFERENCES named_tree(id) ON DELETE CASCADE,
    commit_id TEXT NOT NULL,
    name TEXT NOT NULL,
    contents TEXT
  )""",
  """
  CREATE TABLE archive (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL
  )""",
  """
  CREATE TABLE suite (
    id SERIAL PRIMARY KEY,
    archive_id INT NOT NULL REFERENCES archive(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'ftp',
    url TEXT
  )""",
  ])

DBUpdater().add(4, statements=[
  "ALTER TABLE patch ADD PRIMARY KEY (named_tree_id, name)"
  ])

DBUpdater().add(5, statements=[
  """
  ALTER TABLE named_tree
    ADD COLUMN source TEXT, -- source package name from debian/control
    ADD COLUMN maintainer TEXT,
    ADD COLUMN uploaders TEXT ARRAY,
    ADD COLUMN homepage TEXT,
    ADD COLUMN source_changelog TEXT, -- source package name from debian/changelog
    ADD COLUMN version debversion,
    ADD COLUMN distribution TEXT,
    ADD COLUMN urgency TEXT,
    ADD COLUMN last_changed TIMESTAMP(0) WITH TIME ZONE, -- time from last changelog entry
    ADD COLUMN last_changed_by TEXT -- maintainer name in last changelog entry
  """,
  ])

DBUpdater().add(6, statements=[
  """
  ALTER TABLE named_tree
    ADD COLUMN versions debversion ARRAY NOT NULL DEFAULT ARRAY[]::debversion[]
  """,
  """
  ALTER TABLE archive
    ADD COLUMN web_root TEXT NOT NULL DEFAULT 'http://packages.qa.debian.org/'
  """,
  """
  ALTER TABLE archive
    ALTER COLUMN web_root DROP DEFAULT
  """,
  """
  ALTER TABLE suite
    ADD COLUMN components TEXT ARRAY NOT NULL DEFAULT ARRAY['main', 'contrib', 'non-free']
  """,
  """
  CREATE TABLE suite_package (
    suite_id INT NOT NULL REFERENCES suite(id),
    source TEXT NOT NULL,
    version debversion NOT NULL,
    component TEXT NOT NULL,
    maintainer TEXT NOT NULL,
    uploaders TEXT,
    dsc TEXT NOT NULL, -- link to .dsc, relative to archive url
    PRIMARY KEY (suite_id, source, version)
  )""",
  ])

DBUpdater().add(7, statements=[
  """
  CREATE TABLE bug_tracker (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    url TEXT NOT NULL,
    web_url TEXT NOT NULL
  )""",
  "INSERT INTO bug_tracker (name, type, url, web_url) VALUES ('debian', 'debianbts', 'http://bugs.debian.org/cgi-bin/soap.cgi', 'http://bugs.debian.org/')",
  """
  CREATE TYPE severity
    AS ENUM ('wishlist', 'minor', 'normal', 'important', 'serious', 'grave', 'critical')
  """,
  """
  CREATE TABLE bug (
    id SERIAL PRIMARY KEY,
    bug_tracker_id INT NOT NULL REFERENCES bug_tracker(id) ON DELETE CASCADE,
    bug_number INT NOT NULL,
    done BOOLEAN NOT NULL,
    severity severity NOT NULL,
    tags TEXT ARRAY NOT NULL DEFAULT ARRAY[]::TEXT[],
    subject TEXT NOT NULL,
    submitter TEXT NOT NULL,
    created TIMESTAMP(0) WITH TIME ZONE NOT NULL,
    owner TEXT NOT NULL,
    last_changed TIMESTAMP(0) WITH TIME ZONE NOT NULL,
    fixed_versions debversion ARRAY NOT NULL DEFAULT ARRAY[]::debversion[],
    found_versions debversion ARRAY NOT NULL DEFAULT ARRAY[]::debversion[],
    forwarded TEXT,
    blocks INT ARRAY NOT NULL DEFAULT ARRAY[]::INT[],
    blocked_by INT ARRAY NOT NULL DEFAULT ARRAY[]::INT[]
  )""",
  """
  CREATE OR REPLACE
    FUNCTION affects (versions debversion[], found debversion[], fixed debversion[])
    RETURNS BOOLEAN
    IMMUTABLE
    STRICT
    LANGUAGE sql AS $function$

  SELECT
    (found_ IS NOT NULL AND fixed_ IS NOT NULL AND found_ >= fixed_)
    OR
    (fixed_ IS NULL AND (found_is_empty OR found_ IS NOT NULL))
  FROM
    (SELECT
        MAX(found__) AS found_,
        MAX(fixed__) AS fixed_,
        $2 = ARRAY[]::debversion[] AS found_is_empty
     FROM
       (SELECT
          (SELECT UNNEST($2) INTERSECT SELECT UNNEST($1)) AS found__,
          (SELECT UNNEST($3) INTERSECT SELECT UNNEST($1)) AS fixed__
       ) AS t2
    ) AS t1

  $function$
  """,
  """
  COMMENT ON FUNCTION affects (versions debversion[], found debversion[], fixed debversion[])
    IS 'check if a bug found (fixed) in the given versions affects the package with versions "versions"'
  """,
  """
  CREATE TABLE bug_source (
    bug_id INT REFERENCES bug(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    PRIMARY KEY (bug_id, source)
  )""",
  ])

DBUpdater().add(8, statements=[
  """
  ALTER TABLE bug
    DROP COLUMN fixed_versions,
    DROP COLUMN found_versions
  """,
  """
  ALTER TABLE bug_source
    ADD COLUMN fixed_versions debversion ARRAY NOT NULL DEFAULT ARRAY[]::debversion[],
    ADD COLUMN found_versions debversion ARRAY NOT NULL DEFAULT ARRAY[]::debversion[]
  """,
  ])

DBUpdater().add(9, statements=[
  "DELETE FROM bug",
  """
  ALTER TABLE bug
    ALTER COLUMN created TYPE TIMESTAMP(0) WITHOUT TIME ZONE,
    DROP COLUMN last_changed,
    ADD COLUMN last_modified TIMESTAMP(0) WITHOUT TIME ZONE
  """,
  ])

DBUpdater().add(10, statements=[
  """
  ALTER TABLE suite_package
    DROP CONSTRAINT IF EXISTS suite_package_pkey,
    ADD PRIMARY KEY (suite_id, component, source, version)
  """,
  ])

DBUpdater().add(11, statements=[
  """
  CREATE TABLE team (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    maintainer TEXT NOT NULL,
    url TEXT
  )""",
  """
  ALTER TABLE repository
    ADD COLUMN team_id INT REFERENCES team(id)
  """,
  """
  ALTER TABLE suite_package
    DROP CONSTRAINT suite_package_pkey,
    ADD COLUMN id SERIAL,
    ADD PRIMARY KEY (id),
    ADD UNIQUE (suite_id, component, source, version)
  """,
  """
  CREATE TABLE wait (
    named_tree_id INT NOT NULL REFERENCES named_tree(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    version debversion NOT NULL,
    comment TEXT,
    PRIMARY KEY (named_tree_id, name, version)
  )""",
  """
  CREATE TABLE suite_binary (
    source_id INT NOT NULL REFERENCES suite_package(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    PRIMARY KEY (source_id, name)
  )""",
  """
  CREATE INDEX ON suite_binary (name)
  """,
  """
  ALTER TABLE named_tree
    ADD COLUMN ignore BOOLEAN NOT NULL DEFAULT 'f'
  """,
  ])

DBUpdater().add(12, statements=[
  "CREATE INDEX ON named_tree (package_id)",
  ])

DBUpdater().add(13, statements=[
  """
  CREATE TABLE watch_result (
    named_tree_id INT PRIMARY KEY NOT NULL REFERENCES named_tree(id) ON DELETE CASCADE,
    homepage TEXT,
    upstream_version debversion,
    download_url TEXT,
    debian_version debversion, -- mangled Debian version
    error TEXT,
    last_checked TIMESTAMP(0) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (error IS NOT NULL != (upstream_version IS NOT NULL AND download_url IS NOT NULL AND debian_version IS NOT NULL))
  )""",
  ])

DBUpdater().add(14, statements=[
  """
  ALTER TABLE wait
    DROP CONSTRAINT wait_pkey,
    ALTER COLUMN version DROP NOT NULL,
    ADD COLUMN id SERIAL PRIMARY KEY
  """,
  ])

DBUpdater().add(15, statements=[
  """
  ALTER TABLE named_tree
    ADD COLUMN todo BOOLEAN NOT NULL DEFAULT 'f'
  """,
  ])
