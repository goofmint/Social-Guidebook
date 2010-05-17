#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: set ts=2 sts=2 sw=2 et:
#
# Copyright 2008 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

__author__ = 'appengine-support@google.com'

"""Main application file for Wiki example.

Includes:
BaseRequestHandler - Base class to handle requests
MainHandler - Handles request to TLD
ViewHandler - Handles request to view any wiki entry
UserProfileHandler - Handles request to view any user profile
EditUserProfileHandler - Handles request to edit current user profile
GetUserPhotoHandler - Serves a users image
SendAdminEmail - Handles request to send the admins email
"""

__author__ = 'appengine-support@google.com'

# Python Imports
import datetime
import md5
import os
import sys
import urllib
import urlparse
import wsgiref.handlers
import xml.dom.minidom
import logging

# Google App Engine Imports
from google.appengine.api import images
from google.appengine.api import mail
from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.api import urlfetch
from google.appengine.api import xmpp
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template

# Wiki Imports
from markdown import markdown
from wiki_model import WikiContent
from wiki_model import WikiRevision
from wiki_model import WikiUser
from base import BaseRequestHandler
import acl, pages

# Set the debug level
_DEBUG = True
_ADMIN_EMAIL='justin.forest@gmail.com'
_SETTINGS = {
}

class ViewRevisionListHandler(BaseRequestHandler):

    def get(self, page_title):
        entry = WikiContent.gql('WHERE title = :1', page_title).get()

        if entry:
            revisions = WikiRevision.all()
            # Render the template view_revisionlist.html, which extends base.html
            self.generate('view_revisionlist.html', template_values={'page_title': page_title,
                                                        'revisions': revisions,
                                                       })


class ViewDiffHandler(BaseRequestHandler):

    def get(self, page_title, first_revision, second_revision):
        entry = WikiContent.gql('WHERE title = :1', page_title).get()

        if entry:
            first_revision = WikiRevision.gql('WHERE wiki_page =  :1 '
                                              'AND version_number = :2', entry, int(first_revision)).get()
            second_revision = WikiRevision.gql('WHERE wiki_page =  :1 '
                                              'AND version_number = :2', entry, int(second_revision)).get()

            import diff
            body = diff.textDiff(first_revision.revision_body, second_revision.revision_body)

            self.generate('view_diff.html', template_values={'page_title': page_title,
                                                             'body': body,
                                                             })


class ViewHandler(BaseRequestHandler):
  def get_page_content(self, page_title, revision_number=1):
    """When memcache lookup fails, we want to query the information from
       the datastore and return it.  If the data isn't in the data store,
       simply return empty strings
    """
    # Find the wiki entry
    entry = WikiContent.gql('WHERE title = :1', self.get_page_name(page_title)).get()

    if entry:
      # Retrieve the current version
      if revision_number is not None:
          requested_version = WikiRevision.gql('WHERE wiki_page =  :1 '
                                               'AND version_number = :2', entry, int(revision_number)).get()
      else:
          requested_version = WikiRevision.gql('WHERE wiki_page =  :1 '
                                               'ORDER BY version_number DESC', entry).get()
      # Define the body, version number, author email, author nickname
      # and revision date
      body = requested_version.revision_body
      version = requested_version.version_number
      author_email = urllib.quote(requested_version.author.wiki_user.email())
      author_nickname = requested_version.author.wiki_user.nickname()
      version_date = requested_version.created
      # Replace all wiki words with links to those wiki pages
      wiki_body = pages.wikifier(self.settings).wikify(body)
      pread = requested_version.pread
    else:
      # These things do not exist
      wiki_body = ''
      author_email = ''
      author_nickname = ''
      version = ''
      version_date = ''
      pread = False

    return [wiki_body, author_email, author_nickname, version, version_date, pread]

  def get_content(self, page_title, revision_number):
    """Checks memcache for the page.  If the page exists in memcache, it
       returns the information.  If not, it calls get_page_content, gets the
       page content from the datastore and sets the memcache with that info
    """
    page_content = memcache.get(page_title)
    if not page_content:
      page_content = self.get_page_content(page_title, revision_number)

    return page_content

  def get(self, page_name=None):
    if page_name is None or page_name == '':
      page_name = self.settings.get('start_page')
    else:
      page_name = pages.unquote(page_name)

    if self.request.get("edit"):
      return self.get_edit(page_name)
    elif self.request.get("history"):
      return self.get_history(page_name)
    else:
      return self.get_view(page_name)

  def get_view(self, page_name):
    template_values = {}

    try:
      template_values['page'] = pages.cache.get(page_name, self.request.get('r'), nocache=('nc' in self.request.arguments()), settings=self.settings)
    except acl.HTTPException, e:
      template_values['page'] = {
        'name': page_name,
        'error': {
          'code': e.code,
          'message': e.message,
        },
        'body': '<h1>%s</h1><p>%s</p>' % (page_name, e.message),
        'offer_create': True,
        'pread': self.settings.data.pread,
      }

    if self.settings.data.pread:
      template_values['page']['pread'] = True

    if 'pread' not in template_values['page'] or not template_values['page']['pread']:
      self.acl.check_read_pages()

    self.generate('view.html', template_values)

  def get_edit(self, page_name):
    self.acl.check_edit_pages()
    page = pages.get(pages.unquote(page_name), self.request.get('r'))
    self.generate('edit.html', template_values={
      'page': page,
    })

class HistoryHandler(BaseRequestHandler):
  def get(self):
    self.acl.check_read_pages()
    page_name = self.request.get('page')
    page = pages.get(page_name)
    history = WikiRevision.gql('WHERE wiki_page = :1 ORDER BY version_number DESC', page).fetch(100)
    self.generate('history.html', template_values = { 'page_name': page_name, 'page_title': page.title, 'revisions': history })

class EditHandler(BaseRequestHandler):
  def get(self):
    self.acl.check_edit_pages()
    template_values = {}

    if self.request.get('page'):
      template_values['page'] = pages.get(self.request.get('page'), self.request.get('r'), create=True)

    self.generate('edit.html', template_values)

  def post(self):
    self.acl.check_edit_pages()

    name = self.request.get('name')
    body = self.request.get('body')

    title = pages.get_title(pages.wikifier(self.settings).wikify(body))
    if not name:
      name = title

    page = pages.get(name, create=True)
    page.body = body
    page.title = title
    page.author = self.get_wiki_user(True)
    if not page.author and users.get_current_user():
      raise Exception('Could not determine who you are.')
    if self.request.get('pread'):
      page.pread = True
    else:
      page.pread = False
    pages.put(page)

    # Remove old page from cache.
    pages.cache.update(name)

    self.redirect('/' + pages.quote(page.title))


class UserProfileHandler(BaseRequestHandler):
  """Allows a user to view another user's profile.  All users are able to
     view this information by requesting http://wikiapp.appspot.com/user/*
  """

  def get(self, user):
    """When requesting the URL, we find out that user's WikiUser information.
       We also retrieve articles written by the user
    """
    # Webob over quotes the request URI, so we have to unquote twice
    unescaped_user = urllib.unquote(urllib.unquote(user))

    # Query for the user information
    wiki_user_object = users.User(unescaped_user)
    wiki_user = WikiUser.gql('WHERE wiki_user = :1', wiki_user_object).get()

    # Retrieve the unique set of articles the user has revised
    # Please note that this doesn't gaurentee that user's revision is
    # live on the wiki page
    article_list = []
    for article in wiki_user.wikirevision_set:
      article_list.append(article.wiki_page.title)
    articles = set(article_list)

    # If the user has specified a feed, fetch it
    feed_content = ''
    feed_titles = []
    if wiki_user.user_feed:
      feed = urlfetch.fetch(wiki_user.user_feed)
      # If the fetch is a success, get the blog article titles
      if feed.status_code == 200:
        feed_content = feed.content
        xml_content = xml.dom.minidom.parseString(feed_content)
        for title in xml_content.getElementsByTagName('title'):
          feed_titles.append(title.childNodes[0].nodeValue)
    # Generate the user profile
    self.generate('user.html', template_values={'queried_user': wiki_user,
                                                'articles': articles,
                                                'titles': feed_titles})

class EditUserProfileHandler(BaseRequestHandler):
  """This allows a user to edit his or her wiki profile.  The user can upload
     a picture and set a feed URL for personal data
  """
  def get(self, user):
    # Get the user information
    unescaped_user = urllib.unquote(user)
    wiki_user_object = users.User(unescaped_user)
    # Only that user can edit his or her profile
    if users.get_current_user() != wiki_user_object:
      self.redirect(self.getStartPage())

    wiki_user = WikiUser.gql('WHERE wiki_user = :1', wiki_user_object).get()
    if not wiki_user:
      wiki_user = WikiUser(wiki_user=wiki_user_object)
      wiki_user.put()

    article_list = []
    for article in wiki_user.wikirevision_set:
      article_list.append(article.wiki_page.title)
    articles = set(article_list)
    self.generate('edit_user.html', template_values={'queried_user': wiki_user,
                                                     'articles': articles})

  def post(self, user):
    # Get the user information
    unescaped_user = urllib.unquote(user)
    wiki_user_object = users.User(unescaped_user)
    # Only that user can edit his or her profile
    if users.get_current_user() != wiki_user_object:
      self.redirect(self.getStartPage())

    wiki_user = WikiUser.gql('WHERE wiki_user = :1', wiki_user_object).get()

    user_photo = self.request.get('user_picture')
    if user_photo:
      raw_photo = images.Image(user_photo)
      raw_photo.resize(width=256, height=256)
      raw_photo.im_feeling_lucky()
      wiki_user.wiki_user_picture = raw_photo.execute_transforms(output_encoding=images.PNG)
    feed_url = self.request.get('feed_url')
    if feed_url:
      wiki_user.user_feed = feed_url

    wiki_user.put()


    self.redirect('/user/%s' % user)


class GetUserPhotoHandler(BaseRequestHandler):
  """This is a class that handles serving the image for a user
     
     The template requests /getphoto/example@test.com and the handler
     retrieves the photo from the datastore, sents the content-type
     and returns the photo
  """

  def get(self, user):
    unescaped_user = urllib.unquote(user)
    wiki_user_object = users.User(unescaped_user)
    # Only that user can edit his or her profile
    if users.get_current_user() != wiki_user_object:
      self.redirect(self.getStartPage())

    wiki_user = WikiUser.gql('WHERE wiki_user = :1', wiki_user_object).get()
    
    if wiki_user.wiki_user_picture:
      self.response.headers['Content-Type'] = 'image/jpg'
      self.response.out.write(wiki_user.wiki_user_picture)


class SendAdminEmail(BaseRequestHandler):
  """Sends the admin email.

     The user must be signed in to send email to the admins
  """
  def get(self):
    # Check to see if the user is signed in
    current_user = users.get_current_user()

    if not current_user:
      self.redirect(users.create_login_url('/sendadminemail'))

    # Generate the email form
    self.generate('admin_email.html')

  def post(self):
    # Check to see if the user is signed in
    current_user = users.get_current_user()

    if not current_user:
      self.redirect(users.create_login_url('/sendadminemail'))

    # Get the email subject and body
    subject = self.request.get('subject')
    body = self.request.get('body')

    # send the email
    mail.send_mail_to_admins(sender=current_user.email(), reply_to=current_user.email(),
                             subject=subject, body=body)

    # Generate the confirmation template
    self.generate('confirm_email.html')

class UsersHandler(BaseRequestHandler):
  def get(self):
    self.acl.check_edit_settings()

    users = [{
      'name': user.wiki_user.nickname(),
      'email': user.wiki_user.email(),
      'md5': md5.new(user.wiki_user.email()).hexdigest(),
      'joined': user.joined,
      } for user in WikiUser.gql('ORDER BY wiki_user').fetch(1000)]

    self.generate('users.html', template_values = { 'users': users })

  def post(self):
    self.acl.check_edit_settings()
    email = self.request.get('email').strip()
    if email and not WikiUser.gql('WHERE wiki_user = :1', users.User(email)).get():
      user = WikiUser(wiki_user=users.User(email))
      user.put()
    self.redirect('/w/users')

class IndexHandler(BaseRequestHandler):
  def get(self):
    self.acl.check_read_pages()

    if '.rss' == self.request.path[-4:]:
      plist = {}
      for revision in WikiRevision.gql('ORDER BY created DESC').fetch(1000):
        page = revision.wiki_page.title
        if page not in plist:
          plist[page] = { 'name': page, 'title': self.get_page_name(page), 'created': revision.created, 'author': revision.author }
      self.generateRss('index-rss.html', template_values = {
        'items': [plist[page] for page in plist],
      });
    else:
      self.generate('index.html', template_values={'pages': [{
        'name': page.title,
        'uri': '/' + pages.quote(page.title),
      } for page in WikiContent.gql('ORDER BY title').fetch(1000)] })

class ChangesHandler(BaseRequestHandler):
  def get(self):
    self.acl.check_read_pages()

    if '.rss' == self.request.path[-4:]:
      self.generateRss('changes-rss.html', template_values={
        'changes': WikiContent.gql('ORDER BY updated DESC').fetch(1000),
      })
    else:
      content = memcache.get('/w/changes')
      if not content or self.request.get('nc'):
        template_values={
          'self': self.request.url,
          'changes': WikiContent.gql('ORDER BY updated DESC').fetch(1000),
        }
        content = self.generate('changes.html', template_values, ret=True)
        memcache.set('/w/changes', content)

      self.response.out.write(content)

class InterwikiHandler(BaseRequestHandler):
  def get(self):
    self.acl.check_edit_pages()
    items = self.settings.getInterWiki()
    self.generate('interwiki.html', template_values={'iwlist': [{'key': k, 'host': urlparse.urlparse(items[k])[1], 'sample': items[k].replace('%s', 'hello%2C%20world')} for k in sorted(items.keys())]})

class SettingsHandler(BaseRequestHandler):
  def get(self):
    self.acl.check_edit_settings()
    self.generate('settings.html', template_values={
      'settings': self.settings.dict(),
    })

  def post(self):
    self.settings.importFormData(self.request)
    self.response.set_status(303)
    self.redirect('/w/settings')

class RobotsHandler(BaseRequestHandler):
  def get(self):
    content = "Sitemap: http://%s/sitemap.xml\n" % (self.request.environ['HTTP_HOST'])

    content += "User-agent: *\n"
    content += "Disallow: /static/\n"
    content += "Disallow: /w/\n"

    self.response.headers['Content-Type'] = 'text/plain'
    self.response.out.write(content)

class SitemapHandler(BaseRequestHandler):
  def get(self):
    content = memcache.get('/sitemap.xml')
    if True or not content:
      content = "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n"
      content += "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n"

      settings = self.settings
      host = self.request.environ['HTTP_HOST']

      for page in WikiContent.all().fetch(1000):
        if settings.data.pread or page.pread:
          line = "<url><loc>http://%s/%s</loc>" % (host, pages.quote(page.title))
          if page.updated:
            line += "<lastmod>%s</lastmod>" % (page.updated.strftime('%Y-%m-%d'))
          line += "</url>\n"
          content += line
      content += "</urlset>\n"

      memcache.set('/sitemap.xml', content)

    self.response.headers['Content-Type'] = 'text/xml'
    self.response.out.write(content)

class UpgradeHandler(BaseRequestHandler):
  def get(self):
    self.acl.check_edit_settings()

    for page in WikiContent.all().fetch(1000):
      if page.updated is None or page.author is None or page.body is None:
        rev = WikiRevision.gql('WHERE wiki_page = :1 ORDER BY version_number DESC', page).get()
        if rev is not None:
          page.updated = rev.created
          page.author = rev.author
          page.pread = rev.pread
          page.body = rev.revision_body
          page.put()
      elif '_' in page.title:
        page.title = page.title.replace('_', ' ')
        page.put()

    self.redirect('/w/index')


_WIKI_URLS = [('/', ViewHandler),
              ('/w/changes(?:\.rss)?', ChangesHandler),
              ('/w/edit', EditHandler),
              ('/w/history', HistoryHandler),
              ('/w/index(?:\.rss)?', IndexHandler),
              ('/w/interwiki', InterwikiHandler),
              ('/w/users', UsersHandler),
              ('/w/upgrade', UpgradeHandler),
              ('/w/settings', SettingsHandler),
              ('/robots.txt', RobotsHandler),
              ('/sitemap.xml', SitemapHandler),
              ('/(.+)', ViewHandler)
              ]

def main():
  _DEBUG = ('Development/' in os.environ.get('SERVER_SOFTWARE'))
  if _DEBUG:
    logging.getLogger().setLevel(logging.DEBUG)
  application = webapp.WSGIApplication(_WIKI_URLS, debug=_DEBUG)
  wsgiref.handlers.CGIHandler().run(application)

if __name__ == '__main__':
  main()
