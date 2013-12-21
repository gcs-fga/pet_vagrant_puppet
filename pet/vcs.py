# vim:ts=2:sw=2:et:ai:sts=2
# Copyright 2011-2012, Ansgar Burchardt <ansgar@debian.org>
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

import json
import StringIO
import subprocess
import svn.client
import svn.core
import svn.ra
import time
import urllib2
import urllib

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
  def link(self, package, filename, directory=False, branch=None, tag=None, named_tree=None):
    assert not (named_tree and (branch or tag)), "cannot give both named_tree and branch or tag"
    if named_tree is not None:
      if named_tree.type == 'branch':
        branch = named_tree.name
      elif named_tree.type == 'tag':
        tag = named_tree.name
      else:
        raise ValueError('NamedTree is neither branch nor tag')
    assert not (branch and tag), "cannot give both branch and tag"
    if branch:
      prefix = "branches/{0}/{1}".format(branch, package)
    elif tag:
      prefix = "tags/{0}/{1}".format(package, tag)
    else:
      prefix = "trunk/{0}".format(package)

    if directory:
      extra = ""
    else:
      extra = "?view=markup"

    return "{0}/{1}/{2}{3}".format(self.web_root, prefix, filename, extra)
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
  def branches(self, package):
    root = self._list("")
    trunk = self._list("trunk")
    branches = { None: trunk[package] }
    all_branches = self._list("branches")
    for name, commit in all_branches.items():
      branch = self._list("branches/{0}".format(name))
      if package in branch:
        branches[name] = branch[package]
    return branches
  def tags(self, package):
    return self._list("tags/{0}".format(package))
  def changed_named_trees(self, session, named_trees_by_package):
    # XXX: This function is ugly.
    from pet.models import NamedTree
    # We assume that all named_trees for a package were updated at the same time.
    # This means we can skip looking into a directory, if we already have a
    # named_tree with a higher commit_id.
    changed = {}
    trunk = self._list("trunk")
    tags = self._list("tags")
    branches = self._list("branches")

    for package, nts in named_trees_by_package.items():
      def add_changed(named_tree):
        changed.setdefault(package, []).append(named_tree)

      package_name = package.name
      known_tags = {}
      known_branches = {}
      known_trunk = None

      for nt in nts:
        if nt.type == 'tag':
          known_tags[nt.name] = nt
        elif nt.type == 'branch' and nt.name is not None:
          known_branches[nt.name] = nt
        elif nt.type == 'branch' and nt.name is None:
          known_trunk = nt
        else:
          raise Exception("unknown named_tree type (type={0}, name={1})".format(nt.type, nt.name))

      if package_name not in tags:
        for nt in known_tags.itervalues():
          session.delete(nt)
      else:
        if len(known_tags) > 0:
          highest_tag = int(max(known_tags.itervalues(), key=lambda nt: int(nt.commit_id)).commit_id)
        else:
          highest_tag = -1
        if tags[package_name] > highest_tag:
          existing_tags = self._list("tags/{0}".format(package_name))
          for name, nt in known_tags.iteritems():
            commit_id = existing_tags.get(name, None)
            if commit_id is None:
              session.delete(nt)
            elif commit_id > int(nt.commit_id):
              nt.commit_id = str(commit_id)
              add_changed(nt)

          for name, commit_id in existing_tags.iteritems():
            if name not in known_tags:
              nt = NamedTree(package=package, type='tag', name=name, commit_id=str(commit_id))
              add_changed(nt)
              session.add(nt)

      for branch_name in branches.iterkeys():
        branch = self._list("branches/{0}".format(branch_name))
        commit_id = branch.get(package_name, None)
        if commit_id is not None:
          nt = known_branches.get(branch_name, None)
          if nt is None:
            nt = NamedTree(package=package, type='branch', name=branch_name, commit_id=str(commit_id))
            add_changed(nt)
            session.add(nt)
          elif commit_id > int(nt.commit_id):
            nt.commit_id = str(commit_id)
            add_changed(nt)
        else:
          nt = known_branches.get(branch_name, None)
          if nt is not None:
            session.delete(nt)

      if known_trunk is None:
        if package_name in trunk:
          nt = NamedTree(package=package, type='branch', name=None, commit_id=str(trunk[package_name]))
          add_changed(nt)
          session.add(nt)
      else:
        commit_id = trunk.get(package_name, None)
        if commit_id is None:
          session.delete(known_trunk)
        elif commit_id > int(known_trunk.commit_id):
          known_trunk.commit_id = str(commit_id)
          add_changed(known_trunk)

    return changed

@_vcs_backend("git")
class Git(VCS):
  def __init__(self, repository):
    self.root = repository.root
    self.web_root = repository.web_root
    self._summary_cache = None
  def link(self, package, filename=None, directory=False, branch=None, tag=None, named_tree=None):
    assert not (named_tree and (branch or tag)), "cannot give both named_tree and branch or tag"
    if named_tree is not None:
      if named_tree.type == 'branch':
        branch = named_tree.name
      elif named_tree.type == 'tag':
        tag = named_tree.name
      else:
        raise ValueError('NamedTree is neither branch nor tag')
    assert not (branch and tag), "cannot give both branch and tag"
    if filename is not None and not directory:
      url = "/{0}.git;a=blob;f={1}".format(urllib.quote(package), urllib.quote(filename))
    elif filename is not None and directory:
      url = "/{0}.git;a=tree;f={1}".format(urllib.quote(package), urllib.quote(filename))
    else:
      url = ";a=shortlog"

    if branch:
      url += ";hb=refs/heads/{0}".format(urllib.quote(branch))
    elif tag:
      url += ";hb=refs/tags/{0}".format(urllib.quote(tag))

    return self.web_root + url
  def file(self, package, filename, branch=None, tag=None):
    """
    returns file contents
    """
    assert not (branch and tag), "cannot give both branch and tag"
    if branch is not None:
      extra = ';hb=refs/heads/{0}'.format(urllib.quote(branch))
    elif tag is not None:
      extra = ';hb=refs/tags/{0}'.format(urllib.quote(tag))
    else:
      extra = ""
    url = "{0}/{1}.git;a=blob_plain;f={2}{3}".format(self.web_root, urllib.quote(package), urllib.quote(filename), extra)

    try:
      f = urllib2.urlopen(url)
      contents = f.read()
      f.close()
    except urllib2.HTTPError as e:
      if e.code == 404:
        return None
      raise
    time.sleep(3)
    return contents
  @property
  def _summary(self):
    if self._summary_cache is None:
      f = urllib2.urlopen(self.root)
      contents = f.read()
      f.close()
      self._summary_cache = json.loads(contents)
    return self._summary_cache
  @property
  def packages(self):
    return self._summary.keys()
  def branches(self, package):
    branches = self._summary[package]['branches']
    branches[None] = self._summary[package]['trunk']
    return branches
  def tags(self, package):
    return self._summary[package]['tags']
  def changed_named_trees(self, session, named_trees_by_package):
    # XXX: This function is ugly.
    from pet.models import NamedTree
    s = self._summary

    changed = {}

    for package, nts in named_trees_by_package.iteritems():
      def add_changed(named_tree):
        changed.setdefault(package, []).append(named_tree)
      ps = s.get(package.name)
      if ps is None:
        for nt in nts:
          session.delete(nt)
      else:
        nts_by_type = dict(branch={}, tag={})
        trunk = None
        for nt in nts:
          if nt.type == 'branch' and nt.name is None:
            trunk = nt
          else:
            nts_by_type[nt.type][nt.name] = nt
        # add an alias for now...
        ps['tag'] = ps['tags']
        ps['branch'] = ps['branches']
        for type in ('branch', 'tag'):
          nts = nts_by_type[type]
          known = ps[type]
          for name, commit_id in known.iteritems():
            nt = nts.get(name, None)
            if nt is None:
              nt = NamedTree(package=package, type=type, name=name, commit_id=commit_id)
              add_changed(nt)
              session.add(nt)
            elif nt.commit_id != commit_id:
              nt.commit_id = commit_id
              add_changed(nt)
          for name, nt in nts.iteritems():
            if name not in known:
              session.delete(nt)
        if trunk is None:
          trunk = NamedTree(package=package, type='branch', name=None, commit_id=ps['trunk'])
          add_changed(trunk)
          session.add(trunk)
        elif trunk.commit_id != ps['trunk']:
          trunk.commit_id = ps['trunk']
          add_changed(trunk)
    return changed

@_vcs_backend("git-local")
class GitLocal(Git):
  def __init__(self, repository):
    super(GitLocal, self).__init__(repository)
  def file(self, package, filename, branch=None, tag=None):
    assert not (branch and tag), "cannot give both branch and tag"
    tree = branch or tag or 'HEAD'
    cmd = ['git', 'cat-file', 'blob', '{0}:{1}'.format(tree, filename)]
    cwd = '{0}.d/{1}.git'.format(self.root, package)
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout, stderr) = p.communicate()
    if p.returncode != 0:
      return None
    return stdout
  @property
  def _summary(self):
    if self._summary_cache is None:
      with open(self.root, 'r') as fh:
        contents = fh.read()
        self._summary_cache = json.loads(contents)
    return self._summary_cache

@_vcs_backend("git-ssh")
class GitSsh(Git):
  def __init__(self, repository):
    super(GitSsh, self).__init__(repository)
  def file(self, package, filename, branch=None, tag=None):
    assert not (branch and tag), "cannot give both branch and tag"
    tree = branch or tag or 'HEAD'
    cwd = '{0}/{1}.git'.format(self.root, package)
    cmd = ['ssh', 'pet-cat-file', 'cd', cwd, ';', 'git', 'cat-file', 'blob', '{0}:{1}'.format(tree, filename)]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout, stderr) = p.communicate()
    if p.returncode != 0:
      return None
    return stdout
  @property
  def _summary(self):
    if self._summary_cache is None:
      cmd = ['ssh', 'pet-cat-file', 'cd', self.root, ';', 'pet-summary']
      p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      (stdout, stderr) = p.communicate()
      if p.returncode != 0:
        raise Exception("Getting summary for {0} failed: {1}".format(self.root, stderr))
      self._summary_cache = json.loads(stdout)
    return self._summary_cache
