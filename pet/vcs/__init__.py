# (C) 2011, Ansgar Burchardt <ansgar@debian.org>
from os.path import relpath
import svn.core, svn.client, svn.ra
import StringIO

class VCSException(Exception):
  pass

class FileNotFound(VCSException):
  pass

_vcs_backends = {}
def _vcs_backend(name):
  def helper(cls):
    global _vcs_backends
    _vcs_backends[name] = cls
    return cls
  return helper

def vcs_backend(repository):
  return _vcs_backends[repository.type](repository)

class VCS(object):
  pass

class _SubversionCallbacks(svn.ra.Callbacks):
  def __init__(self):
    self.auth_baton = svn.core.svn_auth_open([
      svn.client.get_simple_provider(),
      svn.client.get_username_provider(),
      ])

@_vcs_backend("svn")
class Subversion(VCS):
  def __init__(self, repository):
    self.root = repository.root
    self.web_root = repository.web_root
    self.callbacks = _SubversionCallbacks()
    self.ra = svn.ra.svn_ra_open2(self.root, self.callbacks, None)
    self.rev = svn.ra.svn_ra_get_latest_revnum(self.ra)
    self._cache = dict()
  def link(self, package, filename, directory=False, branch=None, tag=None):
    assert not (branch and tag), "cannot give both branch and tag"
    if branch:
      prefix = "branches/{0}".format(branch)
    elif tag:
      prefix = "tags/{0}".format(tag)
    else:
      prefix = "trunk"

    if directory:
      extra = ""
    else:
      extra = "?view=markup"

    return "{0}/{1}/{2}/{3}{4}".format(self.web_root, prefix, package, filename, extra)
  def file(self, package, filename, branch=None, tag=None):
    """
    returns file contents
    """
    assert not (branch and tag), "cannot give both branch and tag"
    if branch:
      path = "branches/{1}/{0}/{2}".format(package, branch, filename)
    elif tag:
      path = "tags/{0}/{1}/{2}".format(package, tag, filename)
    else:
      path = "trunk/{0}/{1}".format(package, filename)
    try:
      stream = StringIO.StringIO()
      svn.ra.svn_ra_get_file(self.ra, path, self.rev, stream)
    except svn.core.SubversionException as e:
      if e.apr_err == 160013:
        raise FileNotFound(e.message)
      raise VCSException(e)
    return stream.getvalue()
  def _list(self, path):
    """
    retrieve list of (name, commit) of subdirectories in path
    """
    if path not in self._cache:
      entries = svn.ra.svn_ra_get_dir2(self.ra, path, self.rev, svn.core.SVN_DIRENT_KIND|svn.core.SVN_DIRENT_CREATED_REV)
      cache = dict()
      for name, dirent in entries[0].items():
        if dirent.kind != svn.core.svn_node_dir: continue
        cache[name] = dirent.created_rev
      self._cache[path] = cache

    return self._cache[path]
  @property
  def packages(self):
    """
    returns a list of known packages in the repository.
    """
    return self._list("trunk").keys()
  def branches(self, package, if_changed_since=None):
    root = self._list("")
    if if_changed_since and max(root, key=lambda x: x[1]) <= if_changed_since:
      return None
    trunk = self._list("trunk")
    branches = { None: trunk[package] }
    all_branches = self._list("branches")
    for name, commit in all_branches.items():
      branch = self._list("branches/{0}".format(name))
      if package in branch:
        branches[name] = branch[package]
    return branches
  def tags(self, package, if_changed_since=None):
    if if_changed_since:
      tags = self._list("tags")
      if tags[package] == if_changed_since:
        return None
    return self._list("tags/{0}".format(package))
