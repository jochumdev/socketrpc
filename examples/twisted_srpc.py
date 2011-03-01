#!/usr/bin/python -OO
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

### START Library location
# Set import Library to ../socketrpc in dev mode
import sys
import os
if os.path.exists(os.path.join(os.path.dirname(sys.argv[0]), os.pardir, 'socketrpc')):
    sys.path.insert(0, os.path.join(os.path.dirname(sys.argv[0]), os.pardir))
### END library location

# Get the right reactor (asuming that we have a 2.6 kernel on linux)
from platform import system as platformSystem
if platformSystem == 'Linux':
    from twisted.internet import epollreactor
    epollreactor.install()
from twisted.internet import reactor

from twisted.internet import protocol, reactor, defer
from twisted.python import log

from socketrpc import __version__
from socketrpc.twisted_srpc import SocketRPCProtocol, set_serializer

from optparse import OptionParser


def parse_commandline(parser=None):
    if parser is None:
        parser = OptionParser(usage="""%prog [-v] [-s <serializer>] [-H <host>] [-p <port>] [-r <# of requests>] MODE

Use this to test/benchmark socketrpc on gevent or to learn using it.
  
Available MODEs:
    server:         Run a single thread server,
                    you need to start this before you can do client* calls.
    clientsingle:   Run a single request on the server.
    clientparallel: Run parallel requests (specify with -r)
    clientserial:   Run serial requests (specify with -r)""")

    parser.add_option("-v", "--version", dest="print_version",
                        help="print current Version", action="store_true")
    parser.add_option("-H", "--host", dest="host", default='127.0.0.1',
                      help="HOST to connect/listen. Default: 127.0.0.1", metavar="HOST")
    parser.add_option("-p", "--port", dest="port", default='9990',
                      help="PORT to connect/listen. Default: 9990", metavar="PORT")
    parser.add_option("-s", "--serializer", dest="serializer", default='pickle2',
                      help="Use serializer SERIALIZER, available are: bson, json and pickle2. Default: pickle2", metavar="SERIALIZER")
    parser.add_option("-r", "--requests", dest="requests", default=100000,
                  help="NUMBER of parallel/serial requests. Default: 100000", metavar="NUMBER")
    parser.add_option("-d", "--debug", dest="debug", default=False,
                        help="Debug print lots of data? Default: False", action="store_true")

    # Parse the commandline
    parser.set_defaults(verbose=True)
    (options, args) = parser.parse_args()
    # Print Version and exit if requested
    if options.print_version:
        print "%s: %s" % ('socketrpc', __version__)
        sys.exit(0)

    if len(args) < 1:
        print 'Please give a MODE'
        sys.exit(1)

    result = {
      'serializer': options.serializer,
      'requests': int(options.requests),
      'mode': args[0],
      'host': options.host,
      'port': int(options.port),
      'debug': options.debug,
    }

    return result

def start(options):
    log.startLogging(sys.stdout)

    SocketRPCProtocol.debug = options['debug']
    set_serializer(options['serializer'])

    mode = options['mode']
    if mode == 'server':
        class ServerProtocol(SocketRPCProtocol):
            def docall_echo(self, args):
                return defer.succeed(args)

            def docall_bounce(self, args):
                """ This is just here to show that server is able to do
                    a "call" on the client
                """
                return self.call(args[0], args[1])

        f = protocol.ServerFactory()
        f.protocol = ServerProtocol
        reactor.listenTCP(options['port'], f)

    elif mode.startswith('client'):
        params = {'g': 'is',
                  'e': 'very',
                  'v': 'cool',
                  'e': 'fast',
                  'n': 'and',
                  't': 'sexy!'}

        class ClientProtocol(SocketRPCProtocol):
            def docall_log(self, args):
                log.msg('"%s" logged from the server' % args[1])
                return '%s: logged on the client, facility: %d' % (args[1], args[0])

        def gotProtocol(client, mode):
            if mode == 'clientsingle':
                client.call('bounce', ['log', (60, 'test')])

            elif mode == 'clientparallel':
                # TODO: This doesn't work the deferredList gets never all result.

                def run100(ign):
                    dl = []
                    ds = []

                    for i in xrange(100):
                        d = defer.Deferred()
                        dl.append(d)
                        ds.append(d)

                    dl = defer.DeferredList(dl)

                    for i in xrange(100):
                        ds[i].chainDeferred(client.call('echo', params))

                    dl.addCallback(lambda ign: log.msg('100 done'))
                    return dl

                d = defer.Deferred()
                for i in xrange(options['requests'] / 100):
                    d.addCallback(run100)

                d.addCallback(lambda ign: reactor.stop())
                d.callback(None)

            elif mode == 'clientserial':
                d = defer.Deferred()

                for i in xrange(int(options['requests'])):
                    d.addCallback(lambda ign: client.call('echo', params))

                d.addCallback(lambda ign: reactor.stop())
                d.callback(None)

        client = protocol.ClientCreator(reactor, ClientProtocol)
        client.connectTCP(options['host'], options['port']).addCallback(gotProtocol, mode)

    reactor.run()

if __name__ == '__main__':
    options = parse_commandline()
    start(options)
