# (C) 2011, Ansgar Burchardt <ansgar@debian.org>
"""
SQL helper functions for database maintainance.
"""

from pet.exceptions import *

from sqlalchemy.sql import text

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
      connection.execute(text("UPDATE config SET value = :version WHERE key = 'schema_version'"), version=self.schema_version)

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
