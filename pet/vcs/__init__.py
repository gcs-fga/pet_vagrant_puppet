# (C) 2011, Ansgar Burchardt <ansgar@debian.org>
import pysvn
from os.path import relpath

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

@_vcs_backend("svn")
class Subversion(VCS):
  def __init__(self, repository):
    self.root = repository.root
    self.web_root = repository.web_root
    self.svn = pysvn.Client()
    self.svn.exception_style = 1
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
      url = "{3}/branches/{1}/{0}/{2}".format(package, branch, filename, self.root)
    elif tag:
      url = "{3}/tags/{0}/{1}/{2}".format(package, tag, filename, self.root)
    else:
      url = "{2}/trunk/{0}/{1}".format(package, filename, self.root)
    try:
      return self.svn.cat(url)
    except pysvn.ClientError as e:
      if e[1][0][1] == 160013:
        raise FileNotFound(e[0])
      else:
        raise VCSException(e[0])
  def _list(self, path):
    """
    retrieve list of (name, commit) of subdirectories in path
    """
    url = self.root + path

    if url not in self._cache:
      entries = [ e[0] for e in self.svn.list(url, recurse=False, dirent_fields=pysvn.SVN_DIRENT_KIND|pysvn.SVN_DIRENT_CREATED_REV) ]
      cache = dict()
      for e in entries:
        if e.kind != pysvn.node_kind.dir or e.repos_path == path: continue
        name = relpath(e.repos_path, path)
        cache[name] = e.created_rev.number
      self._cache[url] = cache

    return self._cache[url]
  @property
  def packages(self):
    """
    returns a list of known packages in the repository.
    """
    return self._list("/trunk").keys()
  def branches(self, package, if_changed_since=None):
    root = self._list("/")
    if if_changed_since and max(root, key=lambda x: x[1]) <= if_changed_since:
      return None
    trunk = self._list("/trunk")
    branches = { None: trunk[package] }
    all_branches = self._list("/branches")
    for name, commit in all_branches.items():
      branch = self._list("/branches/{0}".format(name))
      if package in branch:
        branches[name] = branch[package]
    return branches
  def tags(self, package, if_changed_since=None):
    if if_changed_since:
      tags = self._list("/tags")
      if tags[package] == if_changed_since:
        return None
    return self._list("/tags/{0}".format(package))
