# This file is part of Buildbot.  Buildbot is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright Buildbot Team Members

import UserList
import urllib

from buildbot.data import exceptions
from twisted.internet import defer


class ResourceType(object):
    name = None
    endpoints = []
    keyFields = []

    def __init__(self, master):
        self.master = master

    def getEndpoints(self):
        endpoints = self.endpoints[:]
        for i in xrange(len(endpoints)):
            ep = endpoints[i]
            if not issubclass(ep, Endpoint):
                raise TypeError("Not an Endpoint subclass")
            endpoints[i] = ep(self, self.master)
        return endpoints

    def produceEvent(self, msg, event):
        routingKey = (self.name,) \
            + tuple(str(msg[k]) for k in self.keyFields) \
            + (event,)
        self.master.mq.produce(routingKey, msg)


class Endpoint(object):
    pathPatterns = ""
    rootLinkName = None
    isCollection = False

    def __init__(self, rtype, master):
        self.rtype = rtype
        self.master = master

    def get(self, resultSpec, kwargs):
        raise NotImplementedError

    def control(self, action, args, kwargs):
        raise exceptions.InvalidControlException

    def startConsuming(self, callback, options, kwargs):
        raise NotImplementedError


class BuildNestingMixin(object):

    """
    A mixin for methods to decipher the many ways a build, step, or log can be
    specified.
    """

    @defer.inlineCallbacks
    def getBuildid(self, kwargs):
        # need to look in the context of a step, specified by build or
        # builder or whatever
        if 'buildid' in kwargs:
            defer.returnValue(kwargs['buildid'])
        else:
            build = yield self.master.db.builds.getBuildByNumber(
                builderid=kwargs['builderid'],
                number=kwargs['build_number'])
            if not build:
                return
            defer.returnValue(build['id'])

    @defer.inlineCallbacks
    def getStepid(self, kwargs):
        if 'stepid' in kwargs:
            defer.returnValue(kwargs['stepid'])
        else:
            buildid = yield self.getBuildid(kwargs)
            if buildid is None:
                return

            dbdict = yield self.master.db.steps.getStepByBuild(buildid=buildid,
                                                               number=kwargs.get('step_number'),
                                                               name=kwargs.get('step_name'))
            if not dbdict:
                return
            defer.returnValue(dbdict['id'])


class ListResult(UserList.UserList):

    __slots__ = ['offset', 'total', 'limit']

    # if set, this is the index in the overall results of the first element of
    # this list
    offset = None

    # if set, this is the total number of results
    total = None

    # if set, this is the limit, either from the user or the implementation
    limit = None

    def __init__(self, values,
                 offset=None, total=None, limit=None):
        UserList.UserList.__init__(self, values)
        self.offset = offset
        self.total = total
        self.limit = limit

    def __repr__(self):
        return "ListResult(%r, offset=%r, total=%r, limit=%r)" % \
            (self.data, self.offset, self.total, self.limit)

    def __eq__(self, other):
        if isinstance(other, ListResult):
            return self.data == other.data \
                and self.offset == other.offset \
                and self.total == other.total \
                and self.limit == other.limit
        else:
            return self.data == other \
                and self.offset == self.limit is None \
                and (self.total is None or self.total == len(other))

    def __ne__(self, other):
        return not (self == other)


class Link(object):

    "A Link points to another resource, specified by path"

    __slots__ = ['path', 'query']

    def __init__(self, path, query=None):
        assert isinstance(path, tuple)
        self.path = path
        self.query = query

    def __repr__(self):
        return "Link(%r, %r)" % (self.path, self.query or [])

    def __cmp__(self, other):
        return cmp(self.__class__, other.__class__) \
            or cmp(self.path, other.path) \
            or cmp(self.query, other.query)

    def makeUrl(self, baseUrl, apiVersion):
        querystr = ''
        if self.query:
            querystr = '?' + urllib.urlencode(self.query)
        base = '/'.join([baseUrl + 'api', 'v%d' % (apiVersion,)]
                        + list(self.path))
        return base + querystr


def updateMethod(func):
    """Decorate this resourceType instance as an update method, made available
    at master.data.updates.$funcname"""
    func.isUpdateMethod = True
    return func
