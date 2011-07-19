# (C) 2011, Ansgar Burchardt <ansgar@debian.org>
import pet
from sqlalchemy import engine_from_config
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relation, sessionmaker
from sqlalchemy.schema import MetaData

engine = pet.engine()
metadata = MetaData()
metadata.reflect(bind=engine)
Session = sessionmaker(bind=engine)
Base = declarative_base(metadata=metadata)

class Config(Base):
  __tablename__ = 'config'

class Repository(Base):
  __tablename__ = 'repository'

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
  package = relation('Package', backref='named_trees')
  def _file(self, filename):
    session = Session.object_session(self)
    return session.query(File).filter_by(named_tree=self, name=filename, commit_id=self.commit_id)
  def has_file(self, filename):
    return self._file(filename).count() != 0
  def file(self, filename):
    return self._file(filename).one()

class File(Base):
  __tablename__ = 'file'
  named_tree = relation('NamedTree', backref='files')

class Archive(Base):
  __tablename__ = 'archive'

class Suite(Base):
  __tablename__ = 'suite'
  archive = relation('Archive', backref='suites')
