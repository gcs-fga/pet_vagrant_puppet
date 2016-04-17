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

from pet.exceptions import *
from pet.models import *
import pet.vcs
import pet.bts
import pet.watch

import debian
import debian.changelog
import debian.deb822
import os.path
import re
import shutil
import sqlalchemy.orm
import sqlalchemy.orm.exc
import subprocess
import tempfile

re_ignore = re.compile("IGNORE[ -]VERSION:?\s*(?P<version>\S+)", re.IGNORECASE)
re_waits_for = re.compile(r"""
  WAITS[ -]FOR:?\s*
  (?P<package>\S*)                           # package name
  (?:
    \s+(:?\([<=>]*\s*)?(?P<version>\S+?)\)?  # optional version number
    (?:\s+(?P<comment>.*))?                  # and comment
  )?$""", re.IGNORECASE | re.VERBOSE)
re_todo = re.compile(r"\A\s*(?:\* )?(?:TODO|PROBLEM|QUESTION):")

class NamedTreeUpdater(object):
  """update a `pet.models.NamedTree`"""
  def delete_old_files(self):
    """remove all outdated versions of files for this named tree"""
    self.session.query(File).filter((File.named_tree == self.named_tree) & (File.commit_id != self.named_tree.commit_id)).delete()
  def _get(self, filename):
    """
    get contents of a file for the current named tree as a string,
    or None if the file does not exist
    """
    if self.named_tree.type == 'tag':
      contents = self.vcs.file(self.package.name, filename, tag=self.named_tree.name)
    elif self.named_tree.type == 'branch':
      contents = self.vcs.file(self.package.name, filename, branch=self.named_tree.name)
    else:
      raise ValueError("unknown NamedTree type '{0}'".format(self.named_tree.type))

    if contents is not None:
      try:
        contents = unicode(contents, 'utf-8')
      except UnicodeDecodeError:
        contents = unicode(contents, 'iso-8859-1')
    return contents
  def file(self, filename):
    """retrieve the named file from the VCS and store it in the database.

    Returns a tuple (file, changed) with file a `pet.models.File`
    object and changed a Boolean indicating that the file was
    updated.
    """
    try:
      f = self.named_tree.file(filename)
      changed = False
    except sqlalchemy.orm.exc.NoResultFound:
      try:
        contents = self._get(filename)
      except FileNotFound:
        contents = None
      f = File(named_tree=self.named_tree, commit_id=self.named_tree.commit_id, name=filename, contents=contents)
      self.session.add(f)
      changed = True
    return f, changed
  def update_patches(self):
    """update list of patches for named tree"""
    patches, changed = self.file("debian/patches/series")
    if not changed and not self.force: return
    self.session.query(Patch).filter_by(named_tree=self.named_tree).delete()
    if patches.contents:
      for line in patches.contents.splitlines():
        if line.startswith("#"):
          continue
        fields = line.split()
        if len(fields):
          patch = Patch(named_tree=self.named_tree, name=fields[0])
          self.session.add(patch)
  def update_control(self):
    """update information extracted from debian/control"""
    control_file, changed = self.file("debian/control")
    if not changed and not self.force: return
    nt = self.named_tree
    if control_file.contents:
      control = debian.deb822.Deb822(control_file.contents)
      nt.source = control.get("Source")
      if "Maintainer" in control:
        nt.maintainer = control["Maintainer"].strip()
      else:
        nt.maintainer = None
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
    """update information extracted from debian/changelog"""
    changelog_file, changed = self.file("debian/changelog")
    if not changed and not self.force: return
    nt = self.named_tree
    nt.ignore = nt.todo = False
    self.session.query(Wait).filter_by(named_tree=self.named_tree).delete()

    if changelog_file.contents:
      changelog = debian.changelog.Changelog(changelog_file.contents,
          strict=False)
      nt.source_changelog = changelog.package
      nt.version = str(changelog.version)
      nt.versions = [ str(v) for v in changelog.versions ]
      nt.distribution = changelog.distributions
      nt.urgency = changelog.urgency
      nt.last_changed = changelog.date
      nt.last_changed_by = changelog.author

      # TODO: Use public API once #634849 is fixed.
      for line in changelog._blocks[0].changes():
        match = re_ignore.search(line)
        if match and match.group('version') == nt.version:
          nt.ignore = True

        match = re_waits_for.search(line)
        if match:
          wait = Wait(named_tree=self.named_tree, name=match.group('package'), version=match.group('version'), comment=match.group('comment'))
          self.session.add(wait)

        if re_todo.search(line):
          nt.todo = True
    else:
      nt.source_changelog = nt.version = nt.distribution = nt.urgency = nt.last_changed = nt.last_changed_by = None
      nt.versions = []
  def update_watch(self):
    """update cached version of debian/watch"""
    watch_file, changed = self.file("debian/watch")
  def run(self, named_tree, package, vcs, force=False):
    self.session = Session.object_session(named_tree)
    self.named_tree = named_tree
    self.package = package
    self.vcs = vcs
    self.force = force

    print "I: updating {0}, {1} {2}".format(self.package.name, self.named_tree.type, self.named_tree.name)

    self.delete_old_files()
    self.update_patches()
    self.update_control()
    self.update_changelog()
    self.update_watch()

class PackageUpdater(object):
  """update a `pet.models.Package`"""
  def _update_named_tree_list(self, type, known, existing):
    changed = []

    for name, nt in known.iteritems():
      commit_id = existing.get(name, None)
      if commit_id is None:
        self.session.delete(nt)
      else:
        nt.commit_id = str(commit_id)
        changed.append(nt)

    for name, commit_id in existing.iteritems():
      if name not in known:
        nt = NamedTree(type=type, name=name, commit_id=str(commit_id), package=self.package)
        self.session.add(nt)
        changed.append(nt)

    return changed
  def update_tag_list(self):
    known = self.package.tags
    existing = self.vcs.tags(self.package.name)
    return self._update_named_tree_list('tag', known, existing)
  def update_branch_list(self):
    known = self.package.branches
    existing = self.vcs.branches(self.package.name)
    return self._update_named_tree_list('branch', known, existing)
  def update_named_trees(self):
    ntu = NamedTreeUpdater()
    for nt in self.package.named_trees:
      ntu.run(nt, self.package, self.vcs, force=self.force)
  def run(self, package, vcs, force=False):
    self.session = Session.object_session(package)
    self.package = package
    self.vcs = vcs
    self.force = force

    self.update_tag_list()
    self.update_branch_list()
    self.update_named_trees()

class RepositoryUpdater(object):
  """update a `pet.models.Repository`"""
  def __init__(self, repository, force=False):
    self.session = Session.object_session(repository)
    self.repository = repository
    self.vcs = pet.vcs.vcs_backend(repository)
    self.force = force
  def update_package_list(self):
    self.session.begin_nested()
    try:
      known_packages = {}
      for p in self.repository.packages:
        known_packages[p.name] = p
      existing_packages = self.vcs.packages

      for name, p in known_packages.iteritems():
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
  def update_changed_packages(self):
    self.session.begin_nested()
    try:
      named_trees_by_package = {}
      for p in self.repository.packages:
        named_trees_by_package[p] = []
      for nt in self.session.query(NamedTree).join(NamedTree.package).filter(Package.repository==self.repository):
        named_trees_by_package[nt.package].append(nt)
      print "D: Looking for changes in {0} packages.".format(len(named_trees_by_package))
      changed = self.vcs.changed_named_trees(self.session, named_trees_by_package)
      print "D: Found {0} changed packages.".format(len(changed))

      ntu = NamedTreeUpdater()
      for p, nts in changed.iteritems():
        for nt in nts:
          ntu.run(nt, p, self.vcs)
      self.session.commit()
    except:
      self.session.rollback()
      raise
  def update_all_packages(self):
    for p in self.repository.packages:
      pu = PackageUpdater()
      self.session.begin_nested()
      try:
        print "I: Updating package {0}".format(p.name)
        pu.run(p, self.vcs, force=self.force)
        self.session.commit()
      # XXX: Do we want to catch all exceptions here? Probably yes.
      #except Exception as e:
      #  self.session.rollback()
      #  print "E: error while updating package {0}: {1}".format(p.name, e)
      except:
        self.session.rollback()
        raise
  def run(self):
    self.update_package_list()
    if self.force:
      self.update_all_packages()
    else:
      self.update_changed_packages()

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
    if self.cleantmp:
      shutil.rmtree(self.tmpdir)
  def delete_package_list(self):
    self.session.query(SuitePackage).filter_by(suite=self.suite).delete()
  def _download(self, source, target):
    target_xz = target + ".xz"
    r = subprocess.call(['wget', '--quiet', '-O', target_xz, '--', source])
    if r:
      raise IOError("wget failed for {0}.".format(source))
    with open(target, 'w') as fh:
      r = subprocess.call(['xz', '--decompress', '--stdout', '--', target_xz], stdout=fh)
      if r:
        raise IOError("xz failed for {0}.".format(source))
  def add_package_list(self):
    for component in self.suite.components:
      url = "{0}/dists/{1}/{2}/source/Sources.xz".format(self.archive.url, self.suite.name, component)
      target = os.path.join(self.tmpdir, "sources-{0}-{1}-{2}".format(self.archive.id, self.suite.id, component))
      self._download(url, target)
      with open(target, 'r') as fh:
        for s in debian.deb822.Sources.iter_paragraphs(fh):
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

class BugTrackerUpdater(object):
  def __init__(self, bug_tracker):
    self.session = Session.object_session(bug_tracker)
    self.bug_tracker = bug_tracker
  def _delete_unreferenced_bugs(self, sources):
    # TODO: Should use SQL to look for source package names in named_trees.
    print self.session.query(Bug).join(Bug.bug_sources) \
        .filter((Bug.bug_tracker==self.bug_tracker) & ~ BugSource.source.in_(sources)) \
        .statement
  def _update_bugs(self, bug_reports):
    bugs = {}
    for bug in self.session.query(Bug).filter_by(bug_tracker=self.bug_tracker):
      bugs[bug.bug_number] = bug

    print "I: Updating {0} bug reports...".format(len(bug_reports))
    progress = 0
    for br in bug_reports:
      # TODO: one query per bug is SLOOOOOW!
      try:
        bug = bugs[br.bug_number]
      except KeyError:
        bug = Bug(bug_tracker=self.bug_tracker, bug_number=br.bug_number)
        self.session.add(bug)
      br.update_bug(bug)

      progress += 1
      if progress % 10 == 0:
        print "D:   {0} / {1} done".format(progress, len(bug_reports))

  def run(self, named_trees=None):
    # TODO: Add binary_source_map
    bts = pet.bts.DebianBugTracker({}, ignore_unknown_binaries=True)
    # TODO: Unify code path once _delete_unreferenced_bugs is fixed
    # to no longer need the list of sources.
    if named_trees is None:
      sources = [ s[0] for s in self.session.query(NamedTree.source).distinct() ]
      self._delete_unreferenced_bugs(sources)
      bug_numbers = [ b[0] for b in self.session.query(Bug.bug_number).filter_by(bug_tracker=self.bug_tracker).all() ]
      bug_reports = bts.search(sources, bug_numbers)
      self._update_bugs(bug_reports)
    else:
      sources = list(set([ nt.source for nt in named_trees ]))
      bug_reports = bts.search(sources)
      self._update_bugs(bug_reports)

class WatchUpdater(object):
  def __init__(self, session):
    self.session = session
    self.watcher = pet.watch.Watcher()

  def update_watch(self, watch):
    if watch.contents is None:
      return
    result = self.watcher.check(watch.contents)
    if result['errors'] is None:
      wr = WatchResult(named_tree=watch.named_tree, homepage=result['homepage'], upstream_version=str(result['version']), download_url=result['url'], debian_version=result['dversionmangle'](watch.named_tree.version))
    else:
      error = ", ".join([ str(e) for e in result['errors'] ])
      wr = WatchResult(named_tree=watch.named_tree, homepage=result.get('homepage'), error=error)
    self.session.add(wr)
  def run(self, named_trees=None):
    self.session.begin_nested()
    try:
      if named_trees is None:
        named_trees = self.session.query(NamedTree)
      named_trees = named_trees.filter((NamedTree.type=='branch') & (NamedTree.name == None))
      watches = self.session.query(File) \
          .filter(File.name == 'debian/watch') \
          .filter(File.named_tree_id.in_(named_trees.from_self(NamedTree.id).subquery())) \
          .options(sqlalchemy.orm.joinedload(File.named_tree))
      self.session.query(WatchResult) \
          .filter(WatchResult.named_tree_id.in_(named_trees.from_self(NamedTree.id).subquery())).delete(False)
      for watch in watches:
        print "D: checking watch for {0}".format(watch.named_tree.source)
        self.update_watch(watch)
    except:
      self.session.rollback()
      raise
    self.session.commit()

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
