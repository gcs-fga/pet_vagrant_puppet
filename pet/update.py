# (C) 2011, Ansgar Burchardt <ansgar@debian.org>
from pet.models import *
from pet.vcs import FileNotFound, vcs_backend
from debian import deb822
from debian.changelog import Changelog
import shutil
import tempfile
import os.path
import subprocess

class NamedTreeUpdater(object):
  def __init__(self, named_tree, package, vcs):
    self.session = Session.object_session(named_tree)
    self.named_tree = named_tree
    self.package = package
    self.vcs = vcs
  def delete_old_files(self):
    """
    remove all outdated versions of files for this named tree
    """
    self.session.query(File).filter((File.named_tree == self.named_tree) & (File.commit_id != self.named_tree.commit_id)).delete()
  def _get(self, filename):
    """
    get contents of a file for the current named tree as a string,
    or None if the file does not exist
    """
    if self.named_tree.type == 'tag':
      return self.vcs.file(self.package.name, filename, tag=self.named_tree.name)
    elif self.named_tree.type == 'branch':
      return self.vcs.file(self.package.name, filename, branch=self.named_tree.name)
    else:
      raise ValueError("unknown NamedTree type '{0}'".format(self.named_tree.type))
  def retrieve_files(self):
    """
    retrieve current versions of files for this named tree
    """
    for fn in ['debian/changelog', 'debian/control', 'debian/patches/series']:
      if not self.named_tree.has_file(fn):
        try:
          contents = self._get(fn)
        except FileNotFound:
          contents = None
        file = File(named_tree=self.named_tree, commit_id=self.named_tree.commit_id, name=fn, contents=contents)
        self.session.add(file)
  def update_patches(self):
    """
    update list of patches for named tree
    """
    self.session.query(Patch).filter_by(named_tree=self.named_tree).delete()
    patches = self.named_tree.file("debian/patches/series").contents
    if patches:
      for line in patches.splitlines():
        fields = line.split()
        if len(fields):
          patch = Patch(named_tree=self.named_tree, name=fields[0])
          self.session.add(patch)
  def update_control(self):
    control_contents = self.named_tree.file("debian/control").contents
    nt = self.named_tree
    if control_contents:
      control = deb822.Deb822(control_contents)
      nt.source = control["Source"]
      nt.maintainer = control["Maintainer"].strip()
      if "Uploaders" in control:
        nt.uploaders = [ u.strip() for u in control["Uploaders"].split(",") ]
      else:
        nt.uploaders = None
      if "Homepage" in control:
        nt.homepage = control["Homepage"].strip()
      else:
        nt.homepage = None
    else:
      nt.source = nt.maintainer = nt.uploaders = nt.homepage = None
  def update_changelog(self):
    changelog_contents = self.named_tree.file("debian/changelog").contents
    nt = self.named_tree
    if changelog_contents:
      changelog = Changelog(changelog_contents, strict=False)
      nt.source_changelog = changelog.package
      nt.version = str(changelog.version)
      nt.versions = [ str(v) for v in changelog.versions ]
      nt.distribution = changelog.distributions
      nt.urgency = changelog.urgency
      nt.last_changed = changelog.date
      nt.last_changed_by = changelog.author
    else:
      nt.source_changelog = nt.version = nt.distribution = nt.urgency = nt.last_changed = nt.last_changed_by = None
      nt.versions = []
  def run(self):
    print "I: updating {0}, {1} {2}".format(self.package.name, self.named_tree.type, self.named_tree.name)
    self.session.begin_nested()
    try:
      self.delete_old_files()
      self.retrieve_files()
      self.update_patches()
      self.update_control()
      self.update_changelog()
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
      ntu = NamedTreeUpdater(nt, self.package, self.vcs)
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

      for name, p in known_packages.items():
        if name not in existing_packages:
          self.session.delete(p)
      for name in existing_packages:
        if name not in known_packages:
          package = Package(name=name, repository=self.repository)
          self.session.add(package)
      self.session.commit()
    except:
      self.session.rollback()
      raise
  def update_packages(self):
    for p in self.repository.packages:
      self.session.begin_nested()
      try:
        print "I: Updating package {0}".format(p.name)
        pu = PackageUpdater(p, self.vcs)
        pu.run()
        self.session.commit()
      # XXX: Do we want to catch all exceptions here? Probably yes.
      except Exception as e:
        self.session.rollback()
        print "E: error while updating package {0}: {1}".format(p.name, e)
      except:
        self.session.rollback()
        raise
  def run(self):
    self.update_package_list()
    self.update_packages()

class SuiteUpdater(object):
  def __init__(self, suite, archive, tmpdir=None):
    self.session = Session.object_session(suite)
    self.suite = suite
    self.archive = archive
    if tmpdir:
      self.tmpdir = tmpdir
      self.cleantmp = False
    else:
      self.tmpdir = tempfile.mkdtemp(prefix="pet-suite-{0}".format(self.suite.name))
      self.cleantmp = True
  def __del__(self):
    pass
    #if self.cleantmp:
    #  shutil.rmtree(self.tmpdir)
  def delete_package_list(self):
    self.session.query(SuitePackage).filter_by(suite=self.suite).delete()
  def _download(self, source, target):
    target_gz = target + ".gz"
    r = subprocess.call(['wget', '--quiet', '-O', target_gz, '--', source])
    if r:
      raise IOError("wget failed.")
    with open(target, 'w') as fh:
      r = subprocess.call(['gzip', '--decompress', '--to-stdout', '--', target_gz], stdout=fh)
      if r:
        raise IOError("gzip failed.")
  def add_package_list(self):
    for component in self.suite.components:
      url = "{0}/dists/{1}/{2}/source/Sources.gz".format(self.archive.url, self.suite.name, component)
      target = os.path.join(self.tmpdir, "sources-{0}-{1}-{2}".format(self.archive.id, self.suite.id, component))
      self._download(url, target)
      with open(target, 'r') as fh:
        for s in deb822.Sources.iter_paragraphs(fh):
          if "Uploaders" in s:
            uploaders = [ u.strip() for u in s["Uploaders"].split(",") ]
          else:
            uploaders = None
          sp = SuitePackage(
            suite      = self.suite,
            source     = s["Package"],
            version    = s["Version"],
            component  = component,
            maintainer = s["Maintainer"].strip(),
            uploaders  = uploaders,
            dsc        = "{0}/{1}_{2}.dsc".format(s["Directory"], s["Package"], s["Version"]),
            )
          self.session.add(sp)
  def run(self):
    self.session.begin_nested()
    try:
      self.delete_package_list()
      self.add_package_list()
      self.session.commit()
    except:
      self.session.rollback()
      raise

class ArchiveUpdater(object):
  def __init__(self, archive):
    self.archive = archive
  def run(self):
    for suite in self.archive.suites:
      su = SuiteUpdater(suite, self.archive)
      su.run()

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
