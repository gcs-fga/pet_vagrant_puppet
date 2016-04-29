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
import pet.perlre

import debian.debian_support
import gzip
import httplib
import re
import ssl
import StringIO
import urllib2
import urlparse

_re_upstream_version = re.compile(r'^(?:\d+:)?(.*?)(?:-[a-zA-Z0-9+.~]*)?$')

_re_version = re.compile(r'^version=(\d+)')
_re_cont    = re.compile(r'^(.+)\\$')

_re_comment = re.compile(r'^\s*#')
_re_options = re.compile(r'^opt(?:ion)?s=(?:"([^"]*)"|(\S*))\s+(.+)')
_re_mangle  = re.compile(r'mangle$')
_re_paren   = re.compile(r'(.+)/([^/]*\([^/]+\)[^/]*)$')

def TIMEOUT(): return 180

def urlopen(*args, **kwargs):
  if 'context' not in kwargs:
    kwargs['context'] = ssl._create_unverified_context()
  return urllib2.urlopen(*args, **kwargs)

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
        if kv == 'pasv' or kv == 'passive':
          options['passive'] = True
        elif kv == 'active':
          options['active'] = True
        elif kv == 'repack':
          options['repack'] = True
        elif kv == 'decompress':
          options['decompress'] = True
        elif kv == 'bare':
          options['bare'] = True
        elif len(kv) == 0:
          pass
        else:
          key, value = kv.split("=", 1)
          match = _re_mangle.search(key)
          if match:
            options[key] = value.split(';')
          else:
            options[key] = value

    fields = rule.split(None, 3)

    # When the homepage contains parentheses in the last component use that as pattern.
    # In that case the line has only three (not four) fields so we have to split again.
    try:
      match = _re_paren.search(fields[0])
      if match:
        homepage = match.group(1)
        pattern = match.group(2)
        fields = rule.split(None, 2)
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
    try:
      self.pattern = pet.perlre.compile(pattern)
    except Exception as e:
      raise InvalidWatchFile("Could not parse regular expression '{0}': {1}.".format(pattern, e))
    self.version = version
    self.action = action
  def _mangle(self, regexpes, string):
    for regexp in regexpes:
      string = pet.perlre.apply_perlre(regexp, string)
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

_re_cpan_url = re.compile('^https?://search.cpan.org/|https?://www.cpan.org/|https?://metacpan.org/|https?://cpan.metacpan.org/')
_re_http = re.compile('^https?://')
_re_href = re.compile("""href=(?:"([^"]+)"|'([^']+)'|([^'">]+))""")
_re_sf = re.compile(r'^http://sf\.net/')

class Watcher(object):
  def __init__(self):
    self._cpan = CPAN()
  def check(self, watch_file):
    try:
      watch = WatchFile(watch_file)
    except InvalidWatchFile as e:
      return dict(errors=[e])
    except RegexpError:
      return dict(errors=["RegexpError"])
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
        errors = [NotFound("NotFound")]
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
        fh = urlopen(homepage, timeout=TIMEOUT())
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
            url = urlparse.urljoin(homepage, link)
            try:
              v = rule.uversionmangle(".".join(match.groups()))
            except TypeError:
              raise InvalidVersion("InvalidVersion")
            try:
              version = debian.debian_support.Version(v)
            except ValueError:
              raise InvalidVersion("InvalidVersion")
            results.append((url, version, rule.dversionmangle, rule.homepage))
        try:
          results.sort(key=lambda x: x[1], reverse=True)
        except ValueError:
          raise InvalidVersion("InvalidVersion")
    except urllib2.HTTPError as e:
      if e.code == 404:
        raise NotFound("HomepageNotFound")
      raise DownloadError("DownloadError")
    except (urllib2.URLError, httplib.HTTPException, IOError):
      raise DownloadError("DownloadError")
    except RegexpError:
      raise InvalidWatchFile("RegexpError")

    if len(results) > 0:
      return results[0]
    return None

_re_cpan_dist = re.compile(r'/dist/|/release/')
_re_cpan_files = re.compile(r'/authors/id/|/modules/by-module/')

class CPAN(object):
  def __init__(self, mirror='ftp://ftp.cs.uu.nl/pub/CPAN/'):
    self.mirror = mirror
    self._dists = None
    self._files = None

  def _get_and_uncompress(self, url):
    response = urlopen(url, timeout=TIMEOUT())
    buf = StringIO.StringIO(response.read())
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
        url = urlparse.urljoin(self.mirror, candidate)
        v = uversionmangle(".".join(match.groups()))
        try:
          version = debian.debian_support.Version(v)
        except ValueError:
          raise InvalidVersion("InvalidVersion")
        results.append((url, version, dversionmangle, homepage))
    results.sort(key=lambda x: x[1], reverse=True)
    return results

  @property
  def dists(self):
    if self._dists is None:
      dists = []
      contents = self._get_and_uncompress(urlparse.urljoin(self.mirror,
	      'modules/02packages.details.txt.gz'))
      for line in contents:
        fields = line.strip().split(None, 2)
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
      contents = self._get_and_uncompress(urlparse.urljoin(self.mirror,
	      'indices/ls-lR.gz'))
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
