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
  config.include('pyramid_chameleon')
  config.add_static_view('static', 'pet.web:static')

  config.add_route('overview', '/{team_name}/pet.cgi')
  config.add_route('changelog', '/changelog/{named_tree_id}')
  config.add_route('notify', '/{team_name}/pet-notify.cgi')
  config.scan()

  return config.make_wsgi_app()
