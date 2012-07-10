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

class PetError(Exception):
  pass

# sql.py errors.
class DatabaseError(PetError):
  pass

# bts.py errors.
class BugTrackerException(PetError):
  pass

class BinaryNotKnown(BugTrackerException):
  """
  This exception is thrown when we do not know the source package
  for a given binary package.
  """
  pass

# perlre.py errors.
class RegexpError(PetError):
  pass

# vcs.py errors.
class VCSException(PetError):
  pass

class FileNotFound(VCSException):
  pass

# watch.py errors.
class WatchException(PetError):
  pass

class InvalidWatchFile(WatchException):
  pass

class NotFound(WatchException):
  pass

class DownloadError(WatchException):
  pass

class InvalidVersion(WatchException):
  pass

