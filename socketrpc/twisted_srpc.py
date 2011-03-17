# -*- coding: utf-8 -*-
# vim: set et sts=4 sw=4 encoding=utf-8:
###############################################################################
#
# This file is part of socketrpc.
#
# Copyright (C) 2011  Rene Jochum <rene@jrit.at>
#
###############################################################################

from socketrpc import set_serializer2, Fault, STRUCT_INT, struct_error
from socketrpc import STATUS_OK, NOT_WELLFORMED_ERROR, SUPPORTED_TRANSACTIONS, METHOD_NOT_FOUND, APPLICATION_ERROR, TRANSPORT_ERROR

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
    """ Incremental number "call" transactions.
    """
    id = None

    """ Dict of calls, format:
        {<id>: <Deferred>
    """
    calls = None

    """ Log a lot debugging stuff?
    """
    debug = False

    """ Should the dispatch_call method
    strip dots for security?
    """
    allow_dotted_attributes = False

    """ Tuple with Buffering data
        Contents:
            StringIO   buffer
            int        total length of the buffer
            int        where to read data next 
            int        bytes required for the next full object
    """
    _buffer = None

    """ Number bytes needed in the buffer 
    for the next object
    """
    _objNeed = 0

    def connectionMade(self):
        self._buffer = (StringIO(), 0, 0, 0,)
        self._objNeed = 0
        self.id = 0
        self.calls = {}

        # ClientCreator does not pass "factory" so check here
        if hasattr(self, 'factory') and hasattr(self.factory, 'clientConnectionMade'):
            self.factory.clientConnectionMade(self)

    def connectionLost(self, reason=protocol.connectionDone):
        for call in self.calls.itervalues():
            call.errback(Fault(TRANSPORT_ERROR, reason.getErrorMessage()))

    def dataReceived(self, data):
        buffer, blen, offset, need = self._buffer
        buffer.write(data)
        blen += len(data)

        while blen > offset:
            if need == 0:
                try:
                    buffer.seek(offset)
                    need = STRUCT_INT.unpack(buffer.read(4))[0]
                    offset += 4
                    buffer.seek(blen)
                except struct_error:
                    self.fault_received(Fault(NOT_WELLFORMED_ERROR, 'Haven\'t got a length.'))
                    self._buffer = (StringIO(), 0, 0, 0,)
                    return False

            if blen - offset >= need:
                buffer.seek(offset)
                data = buffer.read(need)
                offset += need
                need = 0

                data = decode(data)
                if isinstance(data, Fault):
                    self.fault_received(data)
                    continue

                transaction, obj = data.iteritems().next()
                if not transaction in SUPPORTED_TRANSACTIONS:
                    self.fault_received(NOT_WELLFORMED_ERROR, 'Unknown transaction: %s' % transaction)
                    continue

                if transaction == 'call':
                    d = self.dispatch_call(obj[0], obj[3], obj[1], obj[2])
                    d.addCallback(self._callCb, obj[3])
                    d.addErrback(self._callEb, obj[3])
                elif transaction == 'reply':
                    self.dispatch_reply(obj[0], obj[1], obj[2])

            else:
                break

        if need == 0:
            data = buffer.read()
            buffer.seek(0)
            buffer.truncate()
            buffer.write(data)
            blen = len(data)
            offset = 0

        self._buffer = (buffer, blen, offset, need,)


    def dispatch_call(self, method, id, args, kwargs):
        if not self.allow_dotted_attributes:
            method = method.replace('.', '')

        cmd = 'docall_%s' % method

        if self.debug:
            log.msg('exec CALL %s (%d)' % (method, id))

        try:
            func = getattr(self, cmd)
        except AttributeError, e:
            log.msg('Unknown CALL method %s (%d)' % (method, id))
            return defer.fail(Fault(METHOD_NOT_FOUND, 'Method "%s" not found (%d)' % (method, id)))

        return defer.maybeDeferred(func, *args, **kwargs)

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
        if isinstance(data, Fault):
            self.fault_received(data)
            return

        self.transport.write(STRUCT_INT.pack(len(data)) + data)

    def call(self, method, *args, **kwargs):
        self.id += 1
        data = encode({'call': [method, args, kwargs, self.id]})

        if isinstance(data, Fault):
            return defer.fail(data)

        if self.debug:
            log.msg('send CALL %d %s' % (self.id, method))

        data = STRUCT_INT.pack(len(data)) + data
        self.transport.write(data)

        finished = defer.Deferred()
        self.calls[self.id] = finished

        return finished


class SocketRPCClient(protocol.ReconnectingClientFactory):

    remote = None
    connected = False

    debug = False

    protocol = SocketRPCProtocol

    def startedConnecting(self, connector):
        self.connector = connector

    def clientConnectionLost(self, connector, reason):
        self.connected = False
        self.remote = None

    def clientConnectionMade(self, protocol):
        self.remote = protocol
        self.remote.debug = self.debug
        self.connected = True

    def call(self, method, *args, **kwargs):
        if not self.connected:
            return defer.fail(Fault(TRANSPORT_ERROR, 'Not connected.'))

        return self.remote.call(method, *args, **kwargs)
