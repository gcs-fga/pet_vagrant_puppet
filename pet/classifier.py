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

from pet.models import *

import apt_pkg
import sqlalchemy
import sqlalchemy.orm

class ClassifiedPackage(object):
  def __init__(self, named_tree, bugs, suite_packages, tags):
    self.named_tree = named_tree
    self.bugs = bugs
    self.suite_packages = suite_packages
    self.tags = tags
    self.watch = self.named_tree.watch_result
  name = property(lambda self: self.named_tree.package.name)
  source = property(lambda self: self.named_tree.source)
  version = property(lambda self: self.named_tree.version)
  distribution = property(lambda self: self.named_tree.distribution)
  last_changed_by = property(lambda self: self.named_tree.last_changed_by)
  last_changed = property(lambda self: self.named_tree.last_changed)
  todo = property(lambda self: self.named_tree.todo)

  @property
  def has_rc_bugs(self):
    for b in self.bugs:
      if b.severity in ('serious', 'grave', 'critical'):
        return True
    return False

  @property
  def ready_for_upload(self):
    highest_tag = self.highest_tag
    if self.distribution is not None and self.distribution != 'UNRELEASED' and not self.is_tagged and not self.is_in_archive:
      return True
    return False

  @property
  def is_tagged(self):
    for t in self.tags:
      if t.version == self.version:
        return True
    return False

  @property
  def missing_tag(self):
    if self.is_in_archive and not self.is_tagged:
      return True
    return False

  @property
  def is_in_archive(self):
    for sp in self.suite_packages:
      if sp.version == self.version:
        return True
    return False

  @property
  def highest_tag(self):
    try:
      return self.tags[0]
    except IndexError:
      return None

  @property
  def highest_archive(self):
    try:
      return self.suite_packages[0]
    except IndexError:
      return None

  @property
  def todo_bugs(self):
    for b in self.bugs:
      if not b.forwarded and 'fixed-upstream' not in b.tags and 'pending' not in b.tags and 'wontfix' not in b.tags and 'moreinfo' not in b.tags:
        return True
    return False

  @property
  def newer_upstream(self):
    if self.watch and self.watch.upstream_version:
      return apt_pkg.version_compare(self.watch.upstream_version,
          self.watch.debian_version) > 0
    return False

  @property
  def watch_problem(self):
    if self.watch:
      if self.watch.error is not None:
        return True
      if apt_pkg.version_compare(self.watch.upstream_version,
          self.watch.debian_version) < 0:
        return True
    return False

class Classifier(object):
  def __init__(self, session, named_trees, suite_condition, bug_tracker_condition):
    self.session = session
    sorted_named_trees = named_trees.join(NamedTree.package) \
        .options(sqlalchemy.orm.joinedload(NamedTree.watch_result)) \
        .order_by(Package.name, Package.repository_id, Package.id)

    bug_sources = session.query(BugSource) \
        .join(BugSource.bug).join((NamedTree, BugSource.source == NamedTree.source)) \
        .filter(NamedTree.id.in_(named_trees.from_self(NamedTree.id).subquery())) \
        .filter(bug_tracker_condition) \
        .order_by(Bug.severity.desc(), Bug.bug_number) \
        .filter(Bug.done == False) \
        .options(sqlalchemy.orm.joinedload(BugSource.bug))
    bugs = {}
    for bs in bug_sources:
      bugs.setdefault(bs.source, []).append(bs.bug)

    suite_packages_query = session.query(SuitePackage).join(SuitePackage.suite) \
        .join((NamedTree, SuitePackage.source == NamedTree.source)) \
        .filter(NamedTree.id.in_(named_trees.from_self(NamedTree.id).subquery())) \
        .filter(suite_condition) \
        .order_by(SuitePackage.version.desc()) \
        .options(sqlalchemy.orm.joinedload(SuitePackage.suite))
    suite_packages = {}
    for sp in suite_packages_query:
      suite_packages.setdefault(sp.source, []).append(sp)

    Tags = sqlalchemy.orm.aliased(NamedTree)
    Reference = sqlalchemy.orm.aliased(NamedTree)
    max_version = session.query(sqlalchemy.func.max(Reference.version)) \
        .filter(Reference.type == 'tag') \
        .filter(Reference.package_id == Tags.package_id) \
        .correlate(Tags) \
        .as_scalar()

    tags_query = session.query(Tags) \
        .filter(Tags.type == 'tag') \
        .filter(Tags.version == max_version) \
        .order_by(Tags.package_id, Tags.version.desc()) \
        .filter(Tags.package_id.in_(named_trees.from_self(NamedTree.package_id).subquery()))
    tags = {}
    for t in tags_query:
      tags.setdefault(t.package_id, []).append(t)

    self.packages = []
    for nt in sorted_named_trees:
      self.packages.append(ClassifiedPackage(nt, bugs.get(nt.source, []), suite_packages.get(nt.source, []), tags.get(nt.package_id, [])))

  def classify(self):
    classified = dict()
    for p in self.packages:
      if p.ready_for_upload:
        cls = 'ready_for_upload'
      elif p.has_rc_bugs:
        cls = 'rc_bugs'
      elif p.missing_tag:
        cls = 'missing_tag'
      elif not p.tags:
        cls = 'new'
      elif p.newer_upstream:
        cls = 'new_upstream'
      elif p.watch_problem:
        cls = 'watch_problem'
      elif p.bugs:
        cls = 'bugs'
      elif not p.is_tagged:
        cls = 'wip'
      else:
        cls = 'other'
      classified.setdefault(cls, []).append(p)
    return classified
  def classes(self):
    return [
      { 'name': "Ready For Upload", 'key': 'ready_for_upload' },
      { 'name': "Packages with RC bugs", 'key': 'rc_bugs' },
      { 'name': "Missing tags", 'key': 'missing_tag' },
      { 'name': "Newer upstream version", 'key': 'new_upstream' },
      { 'name': 'Problems with debian/watch', 'key': 'watch_problem' },
      { 'name': 'New packages', 'key': 'new' },
      { 'name': 'With bugs', 'key': 'bugs' },
      { 'name': 'Work in progress', 'key': 'wip' },
      #{ 'name': "Other packages", 'key': 'other' },
      ]
