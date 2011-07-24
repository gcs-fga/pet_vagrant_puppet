# (C) 2011, Ansgar Burchardt <ansgar@debian.org>

from pet.perlre import RegexpError, apply_perlre
import re
import urllib2
from StringIO import StringIO
import gzip

class WatchException(Exception):
  pass

class InvalidWatchFile(WatchException):
  pass

_re_upstream_version = re.compile(r'^(?:\d+:)?(.*?)(?:-[a-zA-Z0-9+.~]*)?$')

_re_version = re.compile(r'^version=(\d+)')
_re_cont    = re.compile(r'^(.+)\\$')

_re_comment = re.compile(r'^\s*#')
_re_options = re.compile(r'^opt(?:ion)?s=("[^"]*"|.*)\s+(.+)')
_re_mangle  = re.compile(r'mangle$')
_re_paren   = re.compile(r'(.+)/([^/]*\([^/]+\)[^/]*)$')

class WatchRule(object):
  def __init__(self, rule=None):
    if rule:
      self.parse(rule)
  def parse(self, rule):
    options = dict()
    match = _re_options.match(rule)
    if match:
      rule = match.group(2)
      for kv in match.group(1).split(","):
        key, value = kv.split("=", 2)
        match = _re_mangle.search(key)
        if match:
          options[key] = value.split(';')
        else:
          options[key] = value

    fields = rule.split(None, 4)

    # When the homepage contains parentheses in the last component use that as pattern.
    # In that case the line has only three (not four) fields so we have to split again.
    try:
      match = _re_paren.search(fields[0])
      if match:
        homepage = match.group(1)
        pattern = match.group(2)
        fields = rule.split(None, 3)
        try:
          version = fields[1]
        except IndexError:
          version = None
        try:
          action = fields[2]
        except IndexError:
          action = None
      else:
        homepage = fields[0]
        pattern = fields[1]
        try:
          version = fields[2]
        except IndexError:
          version = None
        try:
          action = fields[3]
        except IndexError:
          action = None
    except IndexError:
      raise InvalidWatchFile("Rule '{0}' is invalid.".format(rule))

    self.options = options
    self.homepage = homepage
    self.pattern = re.compile(pattern)
    self.version = version
    self.action = action
  def _mangle(self, regexpes, string):
    for regexp in regexpes.split(';'):
      string = apply_perlre(regexp, string)
    return string
  def uversionmangle(self, uversion):
    """returns mangled upstream version"""
    regexpes = self.options.get('uversionmangle', self.options.get('versionmangle', None))
    if regexpes is not None:
      uversion = self._mangle(regexpes, uversion)
    return uversion
  def dversionmangle(self, dversion):
    dversion = _re_upstream_version.sub(r'\1', dversion)
    regexpes = self.options.get('dversionmangle', self.options.get('versionmangle', None))
    if regexpes is not None:
      dversion = self._mangle(regexpes, dversion)
    return dversion

class WatchFile(object):
  def __init__(self, watch=None):
    if watch:
      self.parse(watch)
  def parse(self, watch):
    lines = watch.splitlines()
    def next_line():
      logical_line = ""
      for line in lines:
        match = _re_cont.match(line)
        if match:
          logical_line += match.group(1)
          continue
        else:
          logical_line += line
        yield logical_line
        logical_line = ""

    self.version = None
    self.rules = []
    for line in next_line():
      if _re_comment.match(line):
        continue
      if self.version is None:
        # check version
        match = _re_version.match(line)
        if match:
          self.version = int(match.group(1))
          if self.version not in (2, 3):
            raise InvalidWatchFile('Only watch files using version 2 or 3 are supported.')
      else:
        # collect watch rules
        self.rules.append(WatchRule(line))

_re_cpan_url = re.compile('^http://search.cpan.org/')

class Watcher(object):
  def __init__(self):
    self._cpan = CPAN()
  def check(self, watch_file):
    watch = WatchFile(watch_file)
    for rule in watch.rules:
      self.check_rule(rule)
  def check_rule(self, rule):
    if _re_cpan_url.match(rule.homepage):
      self._cpan.check(rule.homepage, rule.pattern)

_re_cpan_dist = re.compile(r'/dist/')
_re_cpan_files = re.compile(r'/authors/id/|/modules/by-module/')

class CPAN(object):
  def __init__(self, mirror='ftp://ftp.cs.uu.nl/pub/CPAN'):
    self.mirror = mirror
    self._dists = None
    self._files = None

  def _get_and_uncompress(self, url):
    response = urllib2.openurl(url)
    buf = StringIO(response.read())
    response.close()
    return gzip.GzipFile(fileobj=buf, mode='rb')

  def check(self, homepage, pattern):
    if _re_cpan_dist.search(homepage):
      target = self.dists
    elif _re_cpan_files.search(homepage):
      target = self.files
    else:
      return None

    results = []
    for candidate in target:
      match = rule.pattern.match(candidate):
      if match:
        url = "{0}/{1}".format(homepage, candidate)
        version = ".".join(match.groups)
        results.append((url, version))
    return results

  @property
  def dists(self):
    if self._dists is None:
      dists = []
      contents = self._get_and_uncompress(self.mirror + '/02packages.details.txt.gz')
      for line in contents:
        fields = line.split(None, 3)
        dists.append(fields[2])
      contents.close()
      self._dists = dists
    return self._dists

  @property
  def files(self):
    if self._files is None:
      files = []

      re_dir = re.compile('^(.*):$')
      re_interesting = re.compile('authors/id|modules/by-module')
      re_file = re.compile(r'\.tar\.(?:gz|bz2|xz)')

      current = '' # current directory
      interesting = False # are we interested in files in the current directory?
      contents = self._get_and_uncompress(self.mirror + '/ls-lR.gz')
      for line in contents:
        line = line.strip()
        if line == '':
          current = ''
          interesting = False

        match = re_dir.match(line):
        if match:
          current = match.group(1)
          interesting = re_interesting.search(current)
        if not interesting or not current:
          continue

        # -rw-rw-r--   1 jhi      cpan-adm    1129 Aug 10  1998 README
        # lrwxrwxrwx   1 root     csc           24 Feb 25 03:20 CA-97.17.sperl -> ../../5.0/CA-97.17.sperl
        fields = line.split()
        if len(fields) < 9:
          continue

        if not re_file.search(fields[8]):
          continue

        files.append("{0}/{1}".format(current, fields[8]))
      contents.close()
      self._files = files
    return self._files
