# -*- coding: utf-8 -*-
# vim: set et sts=4 sw=4 encoding=utf-8:
#
###############################################################################
#
# This file is part of socketrpc.
#
# Copyright (C) 2011  Rene Jochum <rene@jrit.at>
#
###############################################################################

from socketrpc import set_serializer2, Fault, STRUCT_INT, struct_error
from socketrpc import STATUS_OK, NOT_WELLFORMED_ERROR, SUPPORTED_TRANSACTIONS, METHOD_NOT_FOUND, APPLICATION_ERROR

from twisted.internet import protocol, defer
from twisted.python import log

try:
    from cStringIO import StringIO
except ImportError, e:
    from StringIO import StringIO

# For pylint
def decode(data):
    pass
def encode(obj):
    pass

def set_serializer(predefined=None, encode=None, decode=None):
    """ Sets the serializer for this class.
    @see: socketrpc.set_serializer2
    """
    set_serializer2(predefined, encode, decode, globals())

class SocketRPCProtocol(protocol.Protocol):
    id = None
    calls = None

    _objNeed = None
    _buffer = None

    debug = False

    def connectionMade(self):
        self._buffer = StringIO()
        self._objNeed = None
        self.id = 0
        self.calls = {}

    def dataReceived(self, data):
        buffer = self._buffer
        need = self._objNeed

        buffer.write(data)
        blen = buffer.tell()
        buffer.seek(0)
        offset = 0

        while blen > offset:
            if need is None:
                try:
                    need = STRUCT_INT.unpack(buffer.read(4))[0]
                    offset += 4
                except struct_error:
                    self.bsonReceived(Fault(NOT_WELLFORMED_ERROR, 'Haven\'t got a length.'))
                    return False

                data = buffer.read(need)
                if len(data) == need:
                    offset += need
                    need = None

                    data = decode(data)
                    if isinstance(data, Fault):
                        self.fault_received(data)
                        continue

                    transaction, obj = data.iteritems().next()
                    if not transaction in SUPPORTED_TRANSACTIONS:
                        self.fault_received(NOT_WELLFORMED_ERROR, 'Unknown transaction: %s' % transaction)
                        continue

                    if transaction == 'call':
                        d = self.dispatch_call(obj[0], obj[1], obj[2])
                        d.addCallback(self._callCb, obj[2])
                        d.addErrback(self._callEb, obj[2])
                    elif transaction == 'reply':
                        self.dispatch_reply(obj[0], obj[1], obj[2])

            else:
                buffer.seek(offset)
                break

        if offset != 0:
            data = buffer.read()
            buffer.seek(0)
            buffer.truncate()
            buffer.write(data)
            self._objNeed = need


    def dispatch_call(self, method, params, id):
        cmd = 'docall_%s' % method

        if self.debug:
            log.msg('exec CALL %s (%d)' % (method, id))

        try:
            func = getattr(self, cmd)
        except AttributeError, e:
            log.msg('Unknown CALL method %s (%d)' % (method, id))
            return defer.fail(Fault(METHOD_NOT_FOUND, 'Method "%s" not found (%d)' % (method, id)))

        return defer.maybeDeferred(func, params)

    def _callEb(self, failure, id):
        obj = failure.value
        if isinstance(obj, Fault):
            self.send_response(obj.faultCode, obj.faultString, id)
        elif isinstance(obj, Exception):
            self.send_response(APPLICATION_ERROR, "%s: %s" % (obj.__class__.__name__, repr(obj)), id)
        else:
            self.send_response(APPLICATION_ERROR, repr(obj), id)

    def _callCb(self, result, id):
        if isinstance(result, Fault):
            self.send_response(result.faultCode, result.faultString, id)
        else:
            self.send_response(STATUS_OK, result, id)

    def dispatch_reply(self, status, result, id):
        if self.debug:
            log.msg('recv REPLY %d' % id)

        try:
            if status >= STATUS_OK:
                self.calls[id].callback(result)
                del self.calls[id]
            else:
                self.calls[id].errback(Fault(status, result))
                del self.calls[id]
        except KeyError:
            self.fault_received(Fault(APPLICATION_ERROR, 'Unknown result: %d' % id))

    def fault_received(self, fault):
        """ Gets called whenever we receive a fault
        which isn't assignable.
        """
        log.err(fault)

    def send_response(self, code=STATUS_OK, result='', id=None):
        data = {'reply': [code, result, id]}

        if self.debug:
            log.msg('send REPLY %d' % id)

        data = encode(data)
        self.transport.write(STRUCT_INT.pack(len(data)) + data)

    def call(self, method, params=''):
        self.id += 1
        data = encode({'call': [method, params, self.id]})

        if self.debug:
            log.msg('send CALL %d' % self.id)

        data = STRUCT_INT.pack(len(data)) + data
        self.transport.write(data)

        finished = defer.Deferred()
        self.calls[self.id] = finished

        return finished


__all__ = ['Fault', 'Protocol']
