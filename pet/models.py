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
  def tags(self):
    session = Session.object_session(self)
    return session.query(NamedTree).filter(package=self)

class NamedTree(Base):
  __tablename__ = 'named_tree'
  package = relation('Package', backref='named_trees')

class Changelog(Base):
  __tablename__ = 'changelog'
  named_tree = relation('NamedTree', backref='changelog')
