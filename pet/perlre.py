# (C) 2011, Ansgar Burchardt <ansgar@debian.org>
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

import re

_re_op = re.compile(r'^(s|tr|y)(.*)$')
_markers = { '{': '}', '(': ')', '[': ']' }
_re_backref_all = re.compile(r'\$&')
_re_backref = re.compile(r'\$(\d)')

class RegexpError(Exception):
  pass

def apply_perlre(regexp, string):
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

  if flags == '':
    py_flags = 0
  elif flags == 'i':
    py_flags = re.I
  else:
    raise RegexpError("Unknown flag '{0}' used in regular expression.".format(flags))

  replacement = re.sub(_re_backref_all, r'\\0', replacement)
  replacement = re.sub(_re_backref, r'\\\1', replacement)

  return re.sub(pattern, replacement, string)
