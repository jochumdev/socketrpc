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
from socketrpc import STATUS_OK, NOT_WELLFORMED_ERROR, METHOD_NOT_FOUND, APPLICATION_ERROR

from gevent import spawn, spawn_later
from gevent.server import StreamServer
from gevent.event import AsyncResult, Event
from gevent.queue import Queue
from gevent.socket import create_connection
from gevent.socket import socket as gsocket

from socket import error as pysocket_error
import random

try:
    from cStringIO import StringIO
except ImportError, e:
    from StringIO import StringIO

import logging


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


def _recvsized(self):
    try:
        message_length = STRUCT_INT.unpack(self.recv(4))[0]
    except struct_error:
        return Fault(NOT_WELLFORMED_ERROR, 'Haven\'t got a length.')

    sock_buf = StringIO()
    bytes_count = 0
    while bytes_count < message_length:
        chunk = self.recv(min(message_length - bytes_count, 32768))
        part_count = len(chunk)

        if part_count < 1:
            return None

        bytes_count += part_count
        sock_buf.write(chunk)

    return sock_buf.getvalue()


def _sendsized(self, data):
    data = STRUCT_INT.pack(len(data)) + data
    self.sendall(data)

# Monkey patch the gevent socket
_socket = gsocket
_socket.recvsized = _recvsized
_socket.sendsized = _sendsized
del _socket


class SocketRPCProtocol:

    debug = False
    allow_dotted_attributes = False

    def __init__(self):
        """ Sets up instance only variables
        """
        self.id = 0
        self.calls = {}

        self.connected = Event()

        self.writeQueue = Queue()
        self.doWrite = True


    def make_connection(self, socket, address, factory):
        """ Sets up per connection vars
        """
        self.socket = socket
        self.address = address
        self.factory = factory
        self.logger = logging.getLogger("%s.%s:%s" % (self.__class__.__name__, address[0], address[1]))


    def handle_read(self):
        self.connected.set()
        self.connection_made()

        _sock = self.socket

        try:
            while True:
                data = _sock.recvsized()
                if isinstance(data, Fault):
                    return

                data = decode(data)
                if isinstance(data, Fault):
                    self.fault_received(data)
                    continue

                transaction, obj = data.iteritems().next()

                # Dispatch the transaction
                if transaction == 'call':
                    spawn(self.dispatch_call, obj[0], obj[3], obj[1], obj[2])
                elif transaction == 'reply':
                    spawn(self.dispatch_reply, obj[0], obj[1], obj[2])
                else:
                    self.fault_received(NOT_WELLFORMED_ERROR, 'Unknown transaction: %s' % transaction)

        finally:
            # TODO: Make sure that everything has been transmitted.
            self.connected.clear()
            self.connection_lost()

    def handle_write(self):
        q = self.writeQueue

        self.connected.wait()

        _sock = self.socket
        try:
            while True:
                data = q.get()

                try:
                    self.socket.sendsized(data)
                except (TypeError, pysocket_error), e:
                    # TODO: This needs to be passed
                    self.logger.exception(e)
        finally:
            pass

    def connection_made(self):
        self.logger.info('New connection from %s:%s' % self.address)

    def connection_lost(self):
        self.logger.info('Lost connection from %s:%s' % self.address)

    def dispatch_call(self, method, id, args, kwargs):
        if not self.allow_dotted_attributes:
            method = method.replace('.', '')

        cmd = 'docall_%s' % method

        if self.debug:
            self.logger.debug('exec CALL %s (%d)' % (method, id))

        try:
            func = getattr(self, cmd)
        except AttributeError, e:
            self.logger.error('Unknown CALL method %s (%d)' % (method, id))

            self.send_response(METHOD_NOT_FOUND, 'Method "%s" not found (%d)' % (method, id))
            return

        try:
            result = func(*args, **kwargs)
            self.send_response(result=result, id=id)
        except Fault, e:
            self.send_response(e.faultCode, e.faultString, id)
        except Exception, e:
            self.send_response(APPLICATION_ERROR, "%s: %s" % (e.__class__.__name__, repr(e)), id)

    def dispatch_reply(self, status, result, id):
        if self.debug:
            self.logger.debug('recv REPLY (%d)' % id)

        try:
            if status >= STATUS_OK:
                self.calls[id].set(result)
                del self.calls[id]
            else:
                self.calls[id].set_exception(Fault(status, result))
                del self.calls[id]
        except KeyError:
            self.fault_received(Fault(APPLICATION_ERROR, 'Unknown result: %d' % id))

    def fault_received(self, fault):
        """ Gets called whenever we receive a fault
        which isn't assignable.
        """
        self.logger.exception(fault)

    def send_response(self, code=STATUS_OK, result='', id=None):
        if self.debug:
            self.logger.debug('send REPLY (%d)' % id)

        data = encode({'reply': [code,
                                result,
                                id,
                      ]})

        self.writeQueue.put(data)

    def call(self, method, *args, **kwargs):
        self.connected.wait()

        self.id += 1
        data = encode({'call': [method, args, kwargs, self.id]})

        if isinstance(data, Fault):
            finished = AsyncResult()
            finished.set(data)

            return finished

        if self.debug:
            self.logger.debug('send CALL (%d) %s' % (self.id, method))

        self.writeQueue.put(data)

        finished = AsyncResult()
        self.calls[self.id] = finished

        return finished


class SocketRPCServer(StreamServer):
    def __init__(self, listener, protocol, backlog=None, spawn='default'):
        StreamServer.__init__(self, listener, backlog=backlog, spawn=spawn)
        self.protocol = protocol

    def handle(self, socket, address):
        """ Start the socket handlers
            self.protocol.handle_write and
            self.protocol.handle_read.
        """
        protocol = self.protocol()

        protocol.make_connection(socket, address, self)
        # XXX: Is this greenlet independent from handle?
        spawn(protocol.handle_write)

        protocol.handle_read()


class SocketRPCClient(object):
    """ RPClient for the above Server.
        Automaticaly reconnects to the target server (with "reconnect=True") 
        but looses any results which hasn't been transfered on reconnect.
    """

    ## START Reconnecting feature,
    # shameless borrowed from 
    # twisted.i.p.ReconnectingClientFactory (Rene)
    maxDelay = 3600
    initialDelay = 1.0
    factor = 2.7182818284590451
    jitter = 0.11962656472

    delay = initialDelay
    retries = 0
    maxRetries = None

    continueTrying = True
    isTrying = False
    ## END Reconnecting

    def __init__(self, address, protocol, timeout=None, source_address=None, reconnect=False):
        self.sock_args = [address, timeout, source_address]

        proto = self.protocol = protocol()
        if not isinstance(proto, SocketRPCProtocol):
            raise AttributeError('protocol must implement "SocketRPCProtocol"')

        self.continueTrying = reconnect

        # Do monkey patching, TODO: ugly but working.
        # methods
        proto.connection_made = self.connection_made
        proto.connection_lost = self.connection_lost
        self.call = proto.call

        # args
        self.connected = proto.connected
        self.debug = proto.debug

        # Start connecting
        self.connect()

    def connect(self):
        # Protocol specific
        try:
            self.socket = create_connection(*self.sock_args)

            self.address = self.socket.getpeername()

            self.protocol.make_connection(self.socket, self.address, self)

            spawn(self.protocol.handle_read)
            spawn(self.protocol.handle_write)
        except pysocket_error, e:
            self.connection_failed(e)

    def connection_failed(self, reason):
        logging.error('Connection to %s:%s failed: %s' % (self.sock_args[0][0], self.sock_args[0][1], reason))

        if self.continueTrying and not self.isTrying:
            self._retry()

    def connection_made(self):
        logging.info('Connected to %s:%s' % self.address)

    def connection_lost(self):
        logging.info('Lost connection to %s:%s' % self.address)

        if self.continueTrying and not self.isTrying:
            self._retry()

    def _retry(self):
        self.isTrying = True

        if self.connected.is_set():
            self.isTrying = False
            self.delay = self.initialDelay
            self.retries = 0

            if self.debug:
                logging.debug("Successfully reconnected to %s:%s" % self.sock_args[0])
            return

        if not self.continueTrying:
            if self.debug:
                logging.debug("Abandoning connecting to %s:%s on explicit request" % self.sock_args[0])
            return

        self.retries += 1
        if self.maxRetries is not None and (self.retries > self.maxRetries):
            if self.debug:
                logging.debug("Abandoning %s:%s after %d retries." % (self.sock_args[0][0], self.sock_args[0][1], self.retries))
            return

        self.delay = min(self.delay * self.factor, self.maxDelay)
        if self.jitter:
            self.delay = random.normalvariate(self.delay,
                                              self.delay * self.jitter)

        if self.debug:
            logging.debug("%s:%s will retry in %d seconds" % (self.sock_args[0][0], self.sock_args[0][1], self.delay,))

        self.connect()

        spawn_later(self.delay, self._retry)

__all__ = ['Fault', 'SocketRPCProtocol', 'SocketRPCServer', 'SocketRPCClient', 'set_serializer']
