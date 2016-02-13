# vim:ts=2:sw=2:et:ai:sts=2
# Copyright 2011, Ansgar Burchardt <ansgar@debian.org>
#
# Released under the same terms as the original software, see below.
#
# Based on quoted_regex_parse from uscan which has the following copyright
# notice:
#
# Originally written by Christoph Lameter <clameter@debian.org> (I believe)
#
# Modified by Julian Gilbey <jdg@debian.org>
#
# HTTP support added by Piotr Roszatycki <dexter@debian.org>
#
# Rewritten in Perl, Copyright 2002-2006, Julian Gilbey
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

from pet.exceptions import *

import re

_re_op = re.compile(r'^(s|tr|y)(.*)$')
_markers = { '{': '}', '(': ')', '[': ']' }

_pattern_rules = [
  # POSIX character classes
  (re.compile(r'\[:alpha:\]'), r'A-Za-z'),
  (re.compile(r'\[:alnum:\]'), r'A-Za-z0-9'),
    # missing: [:ascii:]
  (re.compile(r'\[:blank:\]'), r' \t'),
    # missing: [:cntrl:]
  (re.compile(r'\[:digit:\]'), r'\d'),
    # missing: [:graph:]
  (re.compile(r'\[:lower:\]'), r'a-z'),
    # missing: [:print:], [:punct:]
  (re.compile(r'\[:space:\]'), r'\s'), # missing: + vertical tab
  (re.compile(r'\[:upper:\]'), r'A-Z'),
  (re.compile(r'\[:word:\]'), r'\w'),
  (re.compile(r'\[:xdigit:\]'), r'0-9a-fA-F'),
]

_replacement_rules = [
  # backrefs
  (re.compile(r'\$&'), r'\\g<0>'),
  (re.compile(r'\$\{?(\d)\}?'), r'\\g<\1>'),
]

def compile(pattern):
  for regex, sub in _pattern_rules:
    pattern = regex.sub(sub, pattern)
  return re.compile(pattern)

def apply_perlre(regexp, string):
  regexp = regexp.strip()
  if regexp == "":
    return string

  match_op = _re_op.match(regexp)
  if not match_op:
    raise RegexpError("Unknown operator in regular expression '{0}'.".format(regexp))
  op = match_op.group(1)

  if op != 's':
    raise NotImplemented("Operator '{0}' not implemented.".format(op))

  arguments = match_op.group(2)
  marker = arguments[0]
  end_marker = _markers.get(marker, marker)
  last_was_escape = False

  stage = 0 # 0=pattern, (1=replacement-marker), 2=replacement, 3=flags
  pattern = replacement = flags = ""
  for char in arguments[1:]:
    if stage == 1:
      end_marker = _markers.get(char, char)
      stage = 2
      continue
    if last_was_escape:
      last_was_escape = False
      if stage == 0:
        pattern += char
      elif stage == 1:
        raise RegexpError("Invalid regular expression.")
      elif stage == 2:
        replacement += char
      else:
        flags += char
    elif char == end_marker:
      if stage == 0:
        if marker != end_marker:
          stage = 1
        else:
          stage = 2
      else:
        stage = 3
    else:
      if char == "\\":
        last_was_escape = True
      if stage == 0:
        pattern += char
      elif stage == 2:
        replacement += char
      else:
        flags += char

  if stage != 3:
    raise RegexpError("Invalid regular expression.")

  count = 1
  py_flags = 0
  for flag in flags:
    if flag == 'i':
      py_flags |= re.I
    elif flag == 'g':
      count = 0
    else:
      raise RegexpError("Unknown flag '{0}' used in regular expression.".format(flags))

  for regex, sub in _pattern_rules:
    pattern = regex.sub(sub, pattern)
  for regex, sub in _replacement_rules:
    replacement = regex.sub(sub, replacement)

  # TODO: flags is only in Python 2.7
  try:
    return re.sub(pattern, replacement, string, count=count)
  except:
    return string
  #return re.sub(pattern, replacement, string, count=count, flags=py_flags)
