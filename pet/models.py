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

import pet
from sqlalchemy import engine_from_config
import sqlalchemy.dialects.postgresql
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import backref, exc, relation, sessionmaker
from sqlalchemy.schema import MetaData
import sqlalchemy.types

class DebVersion(sqlalchemy.types.UserDefinedType):
  """database type for PostgreSQL's debversion type"""
  def get_col_spec(self):
    return "DEBVERSION"
  def bind_processor(self, dialect):
    def process(value):
      return value
    return process
  def result_processor(self, dialect, coltype):
    def process(value):
      return value
    return process

# XXX: Shouldn't there be an API for this?
sqlalchemy.dialects.postgresql.base.ischema_names['debversion'] = DebVersion

engine = pet.engine()
metadata = MetaData()
metadata.reflect(bind=engine)
Session = sessionmaker(bind=engine)
Base = declarative_base(metadata=metadata)

class Config(Base):
  """configuration settings"""
  __tablename__ = 'config'

class Team(Base):
  """model for a team

  A team owns one more more `Repository`s.
  """
  __tablename__ = 'team'

class Repository(Base):
  """model for a repository

  A `Repository` represents a group of packages stored in a common VCS
  location, such as a Subversion repository or a directory of Git
  repositories.
  """
  __tablename__ = 'repository'
  team = relation('Team', backref='repositories')
  @property
  def vcs(self):
    """returns the version control backend for the repository.

    See `pet.vcs` for more information about the returned object.
    """
    if '_vcs' not in self.__dict__:
      from pet.vcs import vcs_backend
      self._vcs = vcs_backend(self)
    return self._vcs

class Package(Base):
  """model for a package

  A `Package` represents a single (source) package in a `Repository`.
  Here "package" refers to the directory struckture in the VCS, the
  name can differ from the Debian package name.
  """
  __tablename__ = 'package'
  repository = relation('Repository', backref='packages')
  @property
  def trunk(self):
    return self.branches[None]
  def _named_trees(self, type):
    session = Session.object_session(self)
    named_trees = {}
    for nt in session.query(NamedTree).filter_by(package=self, type=type):
      named_trees[nt.name] = nt
    return named_trees
  @property
  def branches(self):
    """returns a list of branches as `NamedTree` objects"""
    return self._named_trees('branch')
  @property
  def tags(self):
    """returns a list of tags as `NamedTree` objects"""
    return self._named_trees('tag')

class NamedTree(Base):
  """model for branches and tags

  This class represents branches and tags.  The trunk is available as
  the branch with name None.
  """
  __tablename__ = 'named_tree'
  package = relation('Package', lazy='joined', backref=backref('named_trees',  passive_deletes=True))
  def _file(self, filename):
    session = Session.object_session(self)
    return session.query(File).filter_by(named_tree=self, name=filename, commit_id=self.commit_id)
  def has_file(self, filename):
    return self._file(filename).count() != 0
  def file(self, filename):
    """retrieve a file from the cache"""
    return self._file(filename).one()
  def link(self, filename, directory=False):
    """provide a link to the VCS web interface"""
    return self.package.repository.vcs.link(self.package.name, filename, directory, named_tree=self)

class WatchResult(Base):
  """result of checking debian/watch

  This class represents the results of checking debian/watch for
  upstream versions.  It provides information about the latest
  upstream version available.
  """
  __tablename__ = 'watch_result'
  named_tree = relation('NamedTree', backref=backref('watch_result', uselist=False))

class Wait(Base):
  """model for WAITS-FOR entries

  This class is used to keep track of WAITS-FOR entries in
  debian/changelog.  It gives the package/version we are waiting for.
  """
  __tablename__ = 'wait'
  named_tree = relation('NamedTree', backref='waits')

class File(Base):
  """file retrieved from a VCS

  This class represents a file belonging to a `NamedTree`.
  """
  __tablename__ = 'file'
  named_tree = relation('NamedTree', backref=backref('files', passive_deletes=True))

class Patch(Base):
  """patches present in debian/patches/series"""
  __tablename__ = 'patch'
  named_tree = relation('NamedTree', backref=backref('patches', passive_deletes=True))

class Archive(Base):
  """model for an archive"""
  __tablename__ = 'archive'

class Suite(Base):
  """model for a suite

  This class represents a suite in an `Archive`.
  """
  __tablename__ = 'suite'
  archive = relation('Archive', backref='suites')

class SuitePackage(Base):
  """model for a source package in a suite

  This class represents a source package in a `Suite`.
  """
  __tablename__ = 'suite_package'
  suite = relation('Suite', backref='packages')

class SuiteBinary(Base):
  """model for a binary package in a suite

  This class represents a binary package in a `Suite`.
  """
  __tablename__ = 'suite_binary'
  source = relation('SuitePackage', backref='binaries')
  """returns the source package for this binary"""

class BugTracker(Base):
  """model for a bug tracker

  This class represents a bug tracker such as Debian's BTS or Ubuntu's
  bug tracker component in Launchpad.
  """
  __tablename__ = 'bug_tracker'

class Bug(Base):
  """model for a bug

  A `Bug` represents a single bug report retrieved from a
  `BugTracker`.
  """
  __tablename__ = 'bug'
  bug_tracker = relation('BugTracker', backref='bugs')

class BugSource(Base):
  """associates bugs with source packages

  This class is used to associate `Bug` objects with source package
  names.  It also provides information about affected versions.
  """
  __tablename__ = 'bug_source'
  bug = relation('Bug', backref='bug_sources')
