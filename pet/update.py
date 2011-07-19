# (C) 2011, Ansgar Burchardt <ansgar@debian.org>
from pet.models import *
from pet.vcs import FileNotFound, vcs_backend

class NamedTreeUpdater(object):
  def __init__(self, named_tree, package, vcs):
    self.session = Session.object_session(named_tree)
    self.named_tree = named_tree
    self.package = package
    self.vcs = vcs
  def delete_old_files(self):
    self.session.query(File).filter((File.named_tree == self.named_tree) & (File.commit_id != self.named_tree.commit_id)).delete()
  def _get(self, filename):
    if self.named_tree.type == 'tag':
      return self.vcs.file(self.package.name, filename, tag=self.named_tree.name)
    elif self.named_tree.type == 'branch':
      return self.vcs.file(self.package.name, filename, branch=self.named_tree.name)
    else:
      raise ValueError("unknown NamedTree type '{0}'".format(self.named_tree.type))
  def retrieve_files(self):
    for fn in ['debian/changelog', 'debian/control', 'debian/patches/series']:
      if not self.named_tree.has_file(fn):
        try:
          contents = self._get(fn)
        except FileNotFound:
          contents = None
        file = File(named_tree=self.named_tree, commit_id=self.named_tree.commit_id, name=fn, contents=contents)
        self.session.add(file)
  def run(self):
    self.session.begin_nested()
    try:
      self.delete_old_files()
      self.retrieve_files()
      self.session.commit()
    except:
      self.session.rollback()
      raise

class PackageUpdater(object):
  def __init__(self, package, vcs):
    self.session = Session.object_session(package)
    self.package = package
    self.vcs = vcs
  def _update_named_tree_list(self, type, known, existing):
    self.session.begin_nested()
    try:
      for nt in known:
        if nt not in existing:
          self.session.delete(nt)
      for nt, commit_id in existing.items():
        if nt not in known:
          named_tree = NamedTree(type=type, name=nt, commit_id=commit_id, package=self.package)
          self.session.add(named_tree)
      self.session.commit()
    except:
      self.session.rollback()
      raise
  def update_tag_list(self):
    known = self.package.tags
    existing = self.vcs.tags(self.package.name)
    self._update_named_tree_list('tag', known, existing)
  def update_branch_list(self):
    known = self.package.branches
    existing = self.vcs.branches(self.package.name)
    self._update_named_tree_list('branch', known, existing)
  def update_named_trees(self):
    for nt in self.package.named_trees:
      ntu = NamedTreeUpdater(nt, package, self.vcs)
      ntu.run()
  def run(self):
    self.update_tag_list()
    self.update_branch_list()
    self.update_named_trees()

class RepositoryUpdater(object):
  def __init__(self, repository):
    self.session = Session.object_session(repository)
    self.repository = repository
    self.vcs = vcs_backend(repository)
  def update_package_list(self):
    self.session.begin_nested()
    try:
      known_packages = {}
      for p in self.repository.packages:
        known_packages[p.name] = p
      existing_packages = self.vcs.packages

      for p in known_packages:
        if p not in existing_packages:
          self.session.delete(p)
      for p in existing_packages:
        if p not in known_packages:
          package = Package(name=p, repository=self.repository)
          self.session.add(package)
      self.session.commit()
    except:
      self.session.rollback()
      raise
  def update_packages(self):
    for p in self.repository.packages:
      pu = PackageUpdater(p, self.vcs)
      pu.run()
  def run(self):
    self.update_package_list()

class Updater(object):
  def run(self):
    session = Session()
    try:
      for r in session.query(Repository).all():
        ru = RepositoryUpdater(r)
        ru.run()
      session.commit()
    except:
      session.rollback()
      raise
