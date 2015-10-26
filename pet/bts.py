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

import debianbts
from pet.exceptions import *

class _BugReport(object):
  def update_bug(self, bug):
    from pet.models import Session, BugSource
    session = Session.object_session(bug)

    # TODO: do this in a transaction; move creating a bug here (if None is passed in)
    try:
      assert bug.bug_number == self.bug_number
      bug.severity = self.severity
      bug.tags = self.tags
      bug.subject = self.subject
      bug.submitter = self.submitter
      bug.merged_with = self.merged_with
      bug.created = self.created
      bug.last_modified = self.last_modified
      bug.done = self.done
      bug.forwarded = self.forwarded
      bug.blocks = self.blocks
      bug.blocked_by = self.blocked_by
      bug.owner = self.owner
      bug.affects = bug

      fixed = self.fixed_versions
      found = self.found_versions
      session.query(BugSource).filter_by(bug=bug).delete()
      bug_sources = list()
      for s in self.sources:
        bs = BugSource(bug=bug, source=s, fixed_versions=fixed.get(s, []), found_versions=found.get(s, []))
        bug_sources.append(bs)
      bug.bug_sources = bug_sources

    except:
      raise

class _DebianBugReport(_BugReport):
  def __init__(self, bugreport, binary_source_map, ignore_unknown_binaries=False):
    self._bugreport = bugreport
    self._binary_source_map = binary_source_map
    self._ignore_unknown_binaries = ignore_unknown_binaries

  bug_number = property(lambda self: self._bugreport.bug_num)
  severity = property(lambda self: self._bugreport.severity)
  tags = property(lambda self: self._bugreport.tags)
  subject = property(lambda self: self._bugreport.subject)
  submitter = property(lambda self: self._bugreport.originator)
  merged_with = property(lambda self: self._bugreport.mergedwith)

  @property
  def sources(self):
    return [ s.strip() for s in self._bugreport.source.split(",") ]

  created = property(lambda self: self._bugreport.date)
  last_modified = property(lambda self: self._bugreport.log_modified)
  done = property(lambda self: self._bugreport.done)

  def _split_versions(self, version_strings):
    """
    given a list of strings "binary/version" or "version", this function
    returns a dict mapping source package names to listed versions.
    For strings of the format "version", it is assumed that all source
    packages for this bug report are meant.
    """
    versions = {}
    for version in version_strings:
      parts = version.split("/")
      if len(parts) == 1:
        sources = self.sources
        v = parts[0]
      elif len(parts) == 2:
        v = parts[1]
        try:
          sources = self._binary_source_map[parts[0]]
        except KeyError:
          if parts[0] in self.sources:
            # assume binary package name == source package name
            sources = [ parts[0] ]
          elif self._ignore_unknown_binaries:
            continue
          else:
            raise BinaryNotKnown("source for binary {0} is unknown".format(parts[0]))
      else:
        raise BugTrackerException("cannot parse version '{0}'".format(version))
      for s in sources:
        sv = versions.setdefault(s, set())
        sv.add(v)
    return versions
  @property
  def fixed_versions(self):
    return self._split_versions(self._bugreport.fixed_versions)
  @property
  def found_versions(self):
    return self._split_versions(self._bugreport.found_versions)

  forwarded = property(lambda self: self._bugreport.forwarded)
  blocks = property(lambda self: self._bugreport.blocks)
  blocked_by = property(lambda self: self._bugreport.blockedby)
  owner = property(lambda self: self._bugreport.owner)
  affects = property(lambda self: self._bugreport.affects)
  summary = property(lambda self: self._bugreport.summary)

class DebianBugTracker(object):
  def __init__(self, binary_source_map, ignore_unknown_binaries=False):
    self.binary_source_map = binary_source_map
    self.ignore_unknown_binaries = ignore_unknown_binaries
  def search(self, sources, bug_numbers=None):
    if bug_numbers is None:
      bug_numbers = set()
    else:
      bug_numbers = set(bug_numbers)
    bug_numbers.update(debianbts.get_bugs('src', sources))

    # process in batches. stolen from python-debianbts.
    BATCH_SIZE = 500
    result = []
    for i in range(0, len(bug_numbers), BATCH_SIZE):
        slice = list(bug_numbers)[i:i + BATCH_SIZE]
        result += debianbts.get_status(slice)

    return [ _DebianBugReport(b, self.binary_source_map, self.ignore_unknown_binaries) for b in result ]
