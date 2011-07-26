# (C) 2011, Ansgar Burchardt <ansgar@debian.org>

from pet.perlre import RegexpError, apply_perlre
import re
import urllib2
from StringIO import StringIO
import gzip
from urlparse import urljoin
from debian.debian_support import Version

class WatchException(Exception):
  pass

class InvalidWatchFile(WatchException):
  pass

class NotFound(WatchException):
  pass

_re_upstream_version = re.compile(r'^(?:\d+:)?(.*?)(?:-[a-zA-Z0-9+.~]*)?$')

_re_version = re.compile(r'^version=(\d+)')
_re_cont    = re.compile(r'^(.+)\\$')

_re_comment = re.compile(r'^\s*#')
_re_options = re.compile(r'^opt(?:ion)?s=(?:"([^"]*)"|(\S*))\s+(.+)')
_re_mangle  = re.compile(r'mangle$')
_re_paren   = re.compile(r'(.+)/([^/]*\([^/]+\)[^/]*)$')

class WatchRule(object):
  def __init__(self, rule=None):
    if rule is not None:
      self.parse(rule)
  def parse(self, rule):
    options = dict()
    match = _re_options.match(rule)
    if match:
      rule = match.group(3)
      opts = match.group(1) or match.group(2)
      for kv in opts.split(","):
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

    pattern = r'\A{0}\Z'.format(pattern)
    self.options = options
    self.homepage = homepage
    self.pattern = re.compile(pattern)
    self.version = version
    self.action = action
  def _mangle(self, regexpes, string):
    for regexp in regexpes:
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
    if watch is not None:
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
      line = line.strip()
      if _re_comment.match(line):
        continue
      if self.version is None:
        # check version
        match = _re_version.match(line)
        if match:
          self.version = int(match.group(1))
          if self.version not in (2, 3):
            raise InvalidWatchFile('Only watch files using version 2 or 3 are supported.')
      elif line:
        # collect watch rules
        self.rules.append(WatchRule(line))

_re_cpan_url = re.compile('^http://search.cpan.org/')
_re_http = re.compile('^https?://')
_re_href = re.compile("""href=(?:"([^"]+)"|'([^']+)'|([^'">]+))""")
_re_sf = re.compile(r'^http://sf\.net/')

class Watcher(object):
  def __init__(self):
    self._cpan = CPAN()
  def check(self, watch_file):
    watch = WatchFile(watch_file)
    results = []
    errors = []
    for rule in watch.rules:
      try:
        result = self.check_rule(rule)
        if result is not None:
          results.append(result)
      except WatchException as e:
        errors.append(e)
    results.sort(key=lambda x: x[1], reverse=True)
    if len(errors) == 0:
      errors = None
    if len(results) == 0:
      if errors is None:
        errors = ["NotFound"]
      if len(watch.rules):
        homepage = watch.rules[0].homepage
      else:
        homepage = None
      return dict(errors=errors, homepage=homepage)
    return dict(version=results[0][1], dversionmangle=results[0][2], homepage=results[0][3], url=results[0][0], errors=errors)
  def check_rule(self, rule):
    try:
      results = None
      if _re_cpan_url.match(rule.homepage):
        results = self._cpan.check(rule.homepage, rule.pattern, rule.uversionmangle, rule.dversionmangle)
      # try by hand if url is unknown to cpan
      if results is None:
        results = []
        homepage = _re_sf.sub('http://qa.debian.org/watch/sf.php/', rule.homepage)
        fh = urllib2.urlopen(homepage)
        contents = fh.read()
        fh.close()
        if _re_http.match(homepage):
          # join all groups, only one in non-empty and contains the link
          links = [ "".join(l) for l in _re_href.findall(contents) ]
        else:
          links = contents.split()

        for link in links:
          match = rule.pattern.search(link)
          if match:
            url = urljoin(homepage, link)
            version = rule.uversionmangle(".".join(match.groups()))
            results.append((url, Version(version), rule.dversionmangle, rule.homepage))
        results.sort(key=lambda x: x[1], reverse=True)
    except urllib2.HTTPError as e:
      if e.code == 404:
        raise NotFound()

    if len(results) > 0:
      return results[0]
    return None

_re_cpan_dist = re.compile(r'/dist/')
_re_cpan_files = re.compile(r'/authors/id/|/modules/by-module/')

class CPAN(object):
  def __init__(self, mirror='ftp://ftp.cs.uu.nl/pub/CPAN/'):
    self.mirror = mirror
    self._dists = None
    self._files = None

  def _get_and_uncompress(self, url):
    response = urllib2.urlopen(url)
    buf = StringIO(response.read())
    response.close()
    return gzip.GzipFile(fileobj=buf, mode='rb')

  def check(self, homepage, pattern, uversionmangle=lambda x: x, dversionmangle=lambda x: x):
    if _re_cpan_dist.search(homepage):
      target = self.dists
    elif _re_cpan_files.search(homepage):
      target = self.files
    else:
      return None

    results = []
    for candidate in target:
      match = pattern.match(candidate)
      if match:
        url = urljoin(self.mirror, candidate)
        version = uversionmangle(".".join(match.groups()))
        results.append((url, Version(version), dversionmangle, homepage))
    results.sort(key=lambda x: x[1], reverse=True)
    return results

  @property
  def dists(self):
    if self._dists is None:
      dists = []
      contents = self._get_and_uncompress(urljoin(self.mirror, 'modules/02packages.details.txt.gz'))
      for line in contents:
        fields = line.strip().split(None, 3)
        if len(fields) >= 3:
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
      contents = self._get_and_uncompress(urljoin(self.mirror, 'indices/ls-lR.gz'))
      for line in contents:
        line = line.strip()
        if line == '':
          current = ''
          interesting = False

        match = re_dir.match(line)
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
