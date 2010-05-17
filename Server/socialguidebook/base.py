# -*- coding: utf-8 -*-
# vim: set ts=2 sts=2 sw=2 et:

# Python imports
import logging, os, re, urllib, urlparse

# GAE imports
from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template

# gaewiki imports
import acl, pages, settings
from wiki_model import WikiContent, WikiRevision, WikiUser
from markdown import markdown

class BaseRequestHandler(webapp.RequestHandler):
  """Base request handler extends webapp.Request handler

     It defines the generate method, which renders a Django template
     in response to a web request
  """

  def __init__(self):
    self.settings = settings.Settings()
    self.acl = acl.acl(self.settings)

  def handle_exception(self, e, debug_mode):
    if not issubclass(e.__class__, acl.HTTPException):
      return webapp.RequestHandler.handle_exception(self, e, debug_mode)

    if e.code == 401:
      self.redirect(users.create_login_url(self.request.url))
    else:
      self.error(e.code)
      self.generate('error.html', template_values={
        'settings': self.settings.dict(),
        'code': e.code,
        'title': e.title,
        'message': e.message,
      })

  def getStartPage(self):
    return '/' + pages.quote(self.settings.get('start_page'))

  def notifyUser(self, address, message):
    sent = False
    if xmpp.get_presence(address):
      status_code = xmpp.send_message(address, message)
      sent = (status_code != xmpp.NO_ERROR)

  def get_page_cache_key(self, page_name, revision_number=None):
    key = '/' + page_name
    if revision_number:
      key += '?r=' + str(revision_number)
    return key

  def get_page_name(self, page_title):
    if type(page_title) == type(str()):
      page_title = urllib.unquote(page_title).decode('utf8')
    return page_title.lower().replace(' ', '_')

  def get_current_user(self, back=None):
    if back is None:
      back = self.request.url
    current_user = users.get_current_user()
    if not current_user:
      raise acl.UnauthorizedException()
    return current_user

  def get_wiki_user(self, create=False, back=None):
    current_user = self.get_current_user(back)
    wiki_user = WikiUser.gql('WHERE wiki_user = :1', current_user).get()
    if not wiki_user and create:
      wiki_user = WikiUser(wiki_user=current_user)
      wiki_user.put()
    return wiki_user

  def generateRss(self, template_name, template_values={}):
    template_values['self'] = self.request.url
    url = urlparse.urlparse(self.request.url)
    template_values['base'] = url[0] + '://' + url[1]
    self.response.headers['Content-Type'] = 'text/xml'
    return self.generate(template_name, template_values)

  def generate(self, template_name, template_values={}, ret=False):
    """Generate takes renders and HTML template along with values
       passed to that template

       Args:
         template_name: A string that represents the name of the HTML template
         template_values: A dictionary that associates objects with a string
           assigned to that object to call in the HTML template.  The defualt
           is an empty dictionary.
    """
    # We check if there is a current user and generate a login or logout URL
    user = users.get_current_user()

    if user:
      log_in_out_url = users.create_logout_url(self.getStartPage())
    else:
      log_in_out_url = users.create_login_url(self.request.path)

    template_values['settings'] = self.settings.dict()

    # We'll display the user name if available and the URL on all pages
    values = {'user': user, 'log_in_out_url': log_in_out_url, 'editing': self.request.get('edit'), 'is_admin': users.is_current_user_admin() }
    values['sidebar'] = pages.cache.get('sidebar', create=True, settings=self.settings)
    url = urlparse.urlparse(self.request.url)
    values['base'] = url[0] + '://' + url[1]
    values.update(template_values)

    # Construct the path to the template
    directory = os.path.dirname(__file__)
    path = os.path.join(directory, 'templates', template_name)

    result = template.render(path, values)
    if ret:
      return result

    # Respond to the request by rendering the template
    self.response.out.write(result)
