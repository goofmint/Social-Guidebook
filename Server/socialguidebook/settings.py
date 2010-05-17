# -*- coding: utf-8 -*-
# vim: set ts=2 sts=2 sw=2 et:

import logging, re
from google.appengine.api import memcache
from google.appengine.ext import db

class WikiSettings(db.Model):
  title = db.StringProperty()
  start_page = db.StringProperty()
  admin_email = db.StringProperty()
  # publicly readable
  pread = db.BooleanProperty(True)
  # publicly writable
  pwrite = db.BooleanProperty(False)
  # Google Site Ownership Verification,
  # http://www.google.com/support/webmasters/bin/answer.py?answer=35659
  owner_meta = db.StringProperty()
  # page footer
  footer = db.TextProperty()
  interwiki = db.TextProperty()

class Settings(object):
  def __init__(self):
    self.data = memcache.get('#settings#')
    if not self.data:
      self.data = self.read()
      if not self.data.is_saved():
        defaults = self.defaults()
        for k in defaults:
          if not getattr(self.data, k):
            setattr(self.data, k, defaults[k])
      memcache.set('#settings#', self.data)

  def defaults(self):
    return {
      'title': 'GAEWiki Demo',
      'start_page': 'welcome',
      'admin_email': 'nobody@example.com',
      'footer': None,
      'pread': True,
      'pwrite': False,
      'owner_meta': None,
      'interwiki': "google = http://www.google.ru/search?sourceid=chrome&ie=UTF-8&q=%s\nwp = http://en.wikipedia.org/wiki/Special:Search?search=%s",
    }

  def read(self):
    tmp = WikiSettings.all().fetch(1)
    if len(tmp):
      return tmp[0]
    else:
      return WikiSettings()

  def dict(self):
    d = {}
    defaults = self.defaults()
    for k in defaults:
      d[k] = getattr(self.data, k)
    return d

  def importFormData(self, r):
    for k in self.defaults():
      if k in ('pread', 'pwrite'):
        nv = bool(r.get(k))
      else:
        nv = r.get(k)
      if nv != getattr(self.data, k):
        logging.info('%s := %s' % (k, nv))
        setattr(self.data, k, nv)
    self.save()

  def save(self):
    memcache.set('#settings#', self.data)
    self.data.put()

  def get(self, k):
    return getattr(self.data, k)

  def getInterWiki(self):
    interwiki = {}
    if self.data.interwiki:
      m = re.compile('^(\w+)\s+=\s+(.*)$')
      for line in self.data.interwiki.split("\n"):
        mr = m.match(line)
        if mr:
          interwiki[mr.group(1)] = mr.group(2).strip()
    return interwiki
