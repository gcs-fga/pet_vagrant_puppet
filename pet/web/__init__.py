from pyramid.config import Configurator
from pyramid.events import subscriber, NewRequest

from pet.models import Session
from pet.web.views import *

@subscriber(NewRequest)
def add_session_to_request(event):
  event.request.session = Session()
  def callback(request):
    request.session.rollback()
  event.request.add_finished_callback(callback)

def main(global_config=None, **settings):
  #settings.update({
  #})

  config = Configurator(settings=settings)
  config.add_static_view('static', 'pet.web:static')

  config.add_route('overview', '/{team_name}/pet.cgi')
  config.add_route('changelog', '/changelog/{named_tree_id}')
  config.scan()

  return config.make_wsgi_app()
