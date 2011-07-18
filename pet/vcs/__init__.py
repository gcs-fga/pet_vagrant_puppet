import pysvn

class VCS(object):
  pass

class Subversion(VCS):
  def __init__(self, repository_root):
    self.root = repository_root
    self.svn = pysvn.Client()
  def get_file(self, package, filename, branch=None, tag=None):
    pass
  def packages(self):
    url = "{0}/trunk".format(self.root)
    entries = self.svn.list(url, recurse=False, dirent_fields=pysvn.SVN_DIRENT_KIND|pysvn.SVN_DIRENT_CREATED_REV)
    packages = [ e[0] for e in entries if e[0].kind == pysvn.node_kind.dir ]
    return packages
