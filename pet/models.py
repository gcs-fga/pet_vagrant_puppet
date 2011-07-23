# (C) 2011, Ansgar Burchardt <ansgar@debian.org>
import pet
from sqlalchemy import engine_from_config
import sqlalchemy.dialects.postgresql
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import backref, relation, sessionmaker
from sqlalchemy.schema import MetaData
import sqlalchemy.types

class DebVersion(sqlalchemy.types.UserDefinedType):
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
  __tablename__ = 'config'

class Team(Base):
  __tablename__ = 'team'

class Repository(Base):
  __tablename__ = 'repository'
  team = relation('Team', backref='repositories')

class Package(Base):
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
    return self._named_trees('branch')
  @property
  def tags(self):
    return self._named_trees('tag')

class NamedTree(Base):
  __tablename__ = 'named_tree'
  package = relation('Package', lazy='joined', backref='named_trees')
  def _file(self, filename):
    session = Session.object_session(self)
    return session.query(File).filter_by(named_tree=self, name=filename, commit_id=self.commit_id)
  def has_file(self, filename):
    return self._file(filename).count() != 0
  def file(self, filename):
    return self._file(filename).one()

class Wait(Base):
  __tablename__ = 'wait'
  named_tree = relation('NamedTree', backref='waits')

class File(Base):
  __tablename__ = 'file'
  named_tree = relation('NamedTree', backref='files')

class Patch(Base):
  __tablename__ = 'patch'
  named_tree = relation('NamedTree', backref='patches')

class Archive(Base):
  __tablename__ = 'archive'

class Suite(Base):
  __tablename__ = 'suite'
  archive = relation('Archive', backref='suites')

class SuitePackage(Base):
  __tablename__ = 'suite_package'
  suite = relation('Suite', backref='packages')

class SuiteBinary(Base):
  __tablename__ = 'suite_binary'
  source = relation('SuitePackage', backref='binaries')

class BugTracker(Base):
  __tablename__ = 'bug_tracker'

class Bug(Base):
  __tablename__ = 'bug'
  bug_tracker = relation('BugTracker', backref='bugs')

class BugSource(Base):
  __tablename__ = 'bug_source'
  bug = relation('Bug', backref='bug_sources')
