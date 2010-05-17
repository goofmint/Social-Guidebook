# -*- coding: utf-8 -*-
# vim: set ts=2 sts=2 sw=2 et:

# GAE imports
from google.appengine.api import users

# gaewiki imports
from wiki_model import WikiUser

class HTTPException(Exception):
  pass

class UnauthorizedException(HTTPException):
  def __init__(self):
    self.code = 401
    self.title = 'Unauthorized'
    self.message = 'Please log in and come back.'

class ForbiddenException(HTTPException):
  def __init__(self):
    self.code = 403
    self.title = 'Forbidden'
    self.message = 'You don\'t have access to this page.'

class acl(object):
  def __init__(self, settings):
    self.settings = settings

  def can_read_pages(self):
    """
    Returns True if the user can read pages, otherwise throws an exception.
    """
    if self.can_edit_settings():
      return True
    if self.settings.get('pread'):
      return True
    cu = users.get_current_user()
    if not cu:
      raise UnauthorizedException()
    wu = WikiUser.gql('WHERE wiki_user = :1', cu).get()
    if not wu:
      raise ForbiddenException()
    return True

  def check_read_pages(self):
    self.check_wrapper(self.can_read_pages)

  def can_edit_pages(self):
    """
    Returns True if the user can edit pages, otherwise throws an exception."
    """
    if self.can_edit_settings():
      return True
    if self.settings.get('pwrite'):
      return True
    cu = users.get_current_user()
    if not cu:
      raise UnauthorizedException()
    wu = WikiUser.gql('WHERE wiki_user = :1', cu).get()
    if not wu:
      raise ForbiddenException()
    return True

  def check_edit_pages(self):
    self.check_wrapper(self.can_edit_pages)

  def can_edit_settings(self):
    """
    Returns True if the user can edit wiki settings.
    """
    return users.is_current_user_admin()

  def check_edit_settings(self):
    self.check_wrapper(self.can_edit_settings)

  def check_wrapper(self, cb):
    """
    Raises an appropriate exception if the callback function returns Fallse.
    """
    if not cb():
      if users.get_current_user():
        raise ForbiddenException()
      else:
        raise UnauthorizedException()
