from pet.classifier import Classifier
from pet.models import *

import debian.changelog

from pyramid.view import view_config
from pyramid.response import Response
from pyramid.httpexceptions import HTTPNotFound
from pyramid.url import route_url
from sqlalchemy.orm import exc

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
  return { "changelog": str(changelog).strip() }
