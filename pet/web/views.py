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

from pet.classifier import Classifier
from pet.models import *

import debian.changelog

from pyramid.view import view_config
from pyramid.response import Response
from pyramid.httpexceptions import HTTPNotFound, HTTPBadRequest
from pyramid.url import route_url
from sqlalchemy.orm import exc

import re
import os

@view_config(route_name='overview', renderer='pet.web:templates/overview.pt')
class Overview(object):
  def __init__(self, request):
    self.request = request
    self.session = request.session
    self.team_name = request.matchdict['team_name']
  def changelog_url(self, named_tree):
    return route_url('changelog', self.request, named_tree_id=named_tree.id)
  def __call__(self):
    named_trees = self.session.query(NamedTree) \
        .join(NamedTree.package).join(Package.repository) \
        .join(Repository.team).filter(Team.name == self.team_name) \
        .filter((NamedTree.type == 'branch') & (NamedTree.name == None))
    suite_cond = "1=1"
    bt_cond = "1=1"

    classifier = Classifier(self.session, named_trees, suite_cond, bt_cond)

    return {
      "classified": classifier.classify(),
      "classes": classifier.classes()
    }

@view_config(route_name='changelog', renderer='pet.web:templates/changelog.pt')
def changelog(request):
  try:
    named_tree = request.session.query(NamedTree).filter_by(id=request.matchdict['named_tree_id']).one()
    changelog_contents = named_tree.file("debian/changelog").contents
    if changelog_contents is None:
      raise HTTPNotFound()
  except exc.NoResultFound:
    raise HTTPNotFound()

  changelog = debian.changelog.Changelog(changelog_contents, max_blocks=1, strict=False)
  return { "changelog": unicode(changelog).strip() }

@view_config(route_name='notify')#, request_method='POST')
def notify(request):
  path = request.session.query(Config.value).filter_by(key='request_directory').scalar() or '/srv/pet.debian.net/requests'
  repo_name = request.params['repository']
  repo_id = request.session.query(Repository.id).join(Repository.team) \
      .filter(Repository.name == request.params['repository']) \
      .filter(Team.name == request.matchdict['team_name']).scalar()
  with open(os.path.join(path, 'update-{0}'.format(repo_id)), 'w') as fh:
    print >>fh, 'requested-by: {0}'.format(request.remote_addr)
  return Response('Ok.')
