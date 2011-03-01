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

from gevent import monkey; monkey.patch_all()
from gevent import joinall
from gevent.pool import Pool

from socketrpc import __version__
from socketrpc.gevent_srpc import SocketRPCProtocol, SocketRPCServer, SocketRPCClient, set_serializer

import logging
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
    logging.basicConfig(level=logging.NOTSET, format='%(asctime)s\t%(name)-35s\t%(levelname)s\t%(message)s')
    SocketRPCProtocol.debug = options['debug']

    set_serializer(options['serializer'])

    mode = options['mode']
    if mode == 'server':
        class ServerProtocol(SocketRPCProtocol):
            def docall_echo(self, args):
                """ RPC Call, the result will be passed
                to the client.
                """
                return args

            def docall_bounce(self, args):
                """ This is just here to show that server is able to do
                    a "call" on the client
                """
                return self.call(args[0], args[1]).get()

        SocketRPCServer((options['host'], options['port']), ServerProtocol, backlog=2048).serve_forever()

    elif mode.startswith('client'):
        # The test data to transfer
        params = {'g': 'is',
                  'e': 'very',
                  'v': 'cool',
                  'e': 'fast',
                  'n': 'and',
                  't': 'sexy!'}


        class ClientProtocol(SocketRPCProtocol):
            def docall_log(self, args):
                self.logger.log(args[0], '"%s" logged from the server' % args[1])
                return '%s: logged on the client, facility: %d' % (args[1], args[0])


        if mode == 'clientsingle':
            # Single call, .get() is blocking until the result arrives.
            client = SocketRPCClient((options['host'], options['port']), ClientProtocol)

            echoed = client.call('bounce', ['log', (logging.WARN, 'test')]).get()

        elif mode == 'clientparallel':
            # Parallel execution, sliced
            client = SocketRPCClient((options['host'], options['port']), ClientProtocol)

            def run100():
                # I'm not using gevent.pool.Pool for memory efficience
                pool = Pool()
                for b in xrange(1000):
                    pool.add(client.call('echo', params))

                # Blocks until all results arrived
                pool.join()

            for i in xrange(options['requests'] / 1000):
                run100()


        elif mode == 'clientserial':
            # One after another 
            client = SocketRPCClient((options['host'], options['port']), ClientProtocol)

            for i in xrange(options['requests']):
                # The ".get" blocks until the result arrives
                client.call('echo', params).get()

if __name__ == '__main__':
    options = parse_commandline()
    start(options)



