from pet.models import *

from sqlalchemy.orm import joinedload

class ClassifiedPackage(object):
  def __init__(self, named_tree, bugs, suite_packages):
    self.named_tree = named_tree
    self.bugs = bugs
    self.suite_packages = suite_packages
  name = property(lambda self: self.named_tree.package.name)
  source = property(lambda self: self.named_tree.source)
  version = property(lambda self: self.named_tree.version)
  distribution = property(lambda self: self.named_tree.distribution)

  @property
  def has_rc_bugs(self):
    for b in self.bugs:
      if b.severity in ('serious', 'grave', 'critical'):
        return True
    return False

  @property
  def ready_for_upload(self):
    if self.distribution != 'UNRELEASED':
      return True
    return False

class Classifier(object):
  def __init__(self, session, named_tree_condition, suite_condition, bug_tracker_condition):
    self.session = session
    named_trees = session.query(NamedTree).join(NamedTree.package).join(Package.repository) \
        .filter(named_tree_condition).order_by(Package.name, Package.repository_id)

    bug_sources = session.query(BugSource) \
        .join(BugSource.bug).join((NamedTree, BugSource.source == NamedTree.source)) \
        .join(NamedTree.package).join(Package.repository) \
        .filter(named_tree_condition) \
        .filter(bug_tracker_condition) \
        .order_by(Bug.severity.desc(), Bug.bug_number) \
        .filter(Bug.done == False) \
        .options(joinedload(BugSource.bug))
    print bug_sources.statement
    bugs = {}
    for bs in bug_sources:
      bugs.setdefault(bs.source, []).append(bs.bug)

    suite_packages_query = session.query(SuitePackage).join(SuitePackage.suite) \
        .join((NamedTree, SuitePackage.source == NamedTree.source)) \
        .join(NamedTree.package).join(Package.repository) \
        .filter(named_tree_condition) \
        .filter(suite_condition)
    suite_packages = {}
    for sp in suite_packages_query:
      suite_packages.setdefault(sp.source, {})[sp.suite.name] = sp.version

    self.packages = []
    for nt in named_trees:
      self.packages.append(ClassifiedPackage(nt, bugs.get(nt.source, []), suite_packages.get(nt.source, [])))
  def classify(self):
    classes = dict(rc_bugs=[], ready_for_upload=[], other=[])
    for p in self.packages:
      if p.has_rc_bugs:
        classes['rc_bugs'].append(p)
      elif p.ready_for_upload:
        classes['ready_for_upload'].append(p)
      else:
        classes['other'].append(p)
    return classes
