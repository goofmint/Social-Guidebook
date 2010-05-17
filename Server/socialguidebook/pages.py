# -*- coding: utf-8 -*-
# vim: set ts=2 sts=2 sw=2 et:

# Python imports
import logging, re, urllib

# GAE imports
from google.appengine.api import memcache

# Wiki imports
from wiki_model import WikiContent, WikiRevision
import acl, markdown

# Regular expression for a wiki word.  Wiki words are all letters
# As well as camel case.  For example: WikiWord
_WIKI_WORD = re.compile('\[\[([^]|]+\|)?([^]]+)\]\]')

class NotFoundException(acl.HTTPException):
  def __init__(self):
    self.code = 404
    self.title = 'Not Found'
    self.message = 'There is no such page.'

def get(name, revision=None, create=False):
  page = WikiContent.gql('WHERE title = :1', name).get()
  if not page:
    if create:
      return WikiContent(title=name)
    raise NotFoundException()
  if revision:
    return WikiRevision.gql('WHERE wiki_page = :1 AND version_number = :2', page, int(revision)).get()
  return page

def put(page):
    page.put()
    cache.update(page.title)

def unquote(name):
  return urllib.unquote(name).decode('utf8').replace('_', ' ')

def quote(name, underscore=True):
  if underscore:
    name = name.replace(' ', '_')
  return urllib.quote(name.encode('utf8'))

def get_title(text):
  r = re.search("<h1>(.*)</h1>", text)
  if r:
    return r.group(1)

class wikifier:
  def __init__(self, settings):
    self.settings = settings
    self.interwiki = settings.getInterWiki()

  def wikify(self, text):
    """
    Applies wiki markup to raw markdown text.
    """
    if text is not None:
      text, count = _WIKI_WORD.subn(self.wikify_one, text)
      text = markdown.markdown.markdown(text).strip()
    return text

  def wikify_one(self, pat):
    page_title = pat.group(2)
    if pat.group(1):
      page_name = pat.group(1).rstrip('|')
    else:
      page_name = page_title

    # interwiki
    if ':' in page_name:
      parts = page_name.split(':', 2)
      if page_name == page_title:
        page_title = parts[1]
      if parts[0] in self.interwiki:
        return '<a class="iw iw-%s" href="%s" target="_blank">%s</a>' % (parts[0], self.interwiki[parts[0]].replace('%s', urllib.quote(parts[1].encode('utf8'))), page_title)
      else:
        return '<a title="Unsupported interwiki was used (%s)." class="iw-broken">%s</a>' % (urllib.quote(parts[0]), page_title)

    return '<a class="int" href="%s">%s</a>' % (quote(page_name), page_title)

class cache:
  @classmethod
  def get(cls, name, revision=None, nocache=False, create=False, settings=None):
    key = cls.get_key(name, revision)
    value = memcache.get(key)
    if nocache or value is None:
      page = get(name, revision, create=create)
      value = {
        'name': name,
        'body': wikifier(settings).wikify(page.body),
        'author': None,
        'author_email': None,
        'updated': page.updated,
        'pread': page.pread,
      }
      if page.author:
        value['author'] = page.author.wiki_user.nickname()
        value['author_email'] = page.author.wiki_user.email()
      memcache.set(key, value)
    return value

  @classmethod
  def get_key(cls, name, revision):
    key = '#1/' + name
    if revision:
      key += '?r=' + str(revision)
    return key

  @classmethod
  def update(cls, name):
    memcache.delete(cls.get_key(name, None))
    memcache.delete('/sitemap.xml')
    memcache.delete('/w/changes')
