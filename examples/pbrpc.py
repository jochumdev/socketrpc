#!/usr/bin/python -OOO

from twisted.internet import defer
from twisted.spread import pb
from twisted.python import log
from twisted.python import util

class Server(pb.Root):
    def remote_addGame(self, args):
        return args
        

def callALot():
    def stop_reactor(ign):
        reactor.stop()
    
    def addGame(ign, object):
        params = {'g': 'is',
                  'e': 'very',
                  'v': 'cool',
                  'e': 'fast',
                  'n': 'and',
                  't': 'sexy!'}      
        
        return object.callRemote('addGame', params)
    
    def call(object):
        d = defer.Deferred()
        for i in xrange(100000):
            d.addBoth(addGame, object)
            
        d.addCallback(stop_reactor)
        d.callback(object)
        
        return d
    
    f = pb.PBClientFactory()
    reactor.connectTCP('localhost', 9990, f)
    d = f.getRootObject()
    d.addCallback(call)
    

if __name__ == '__main__':
    # Get the right reactor (asuming that we have a 2.6 kernel on linux)
    from platform import system as platformSystem
    if platformSystem == 'Linux':
        from twisted.internet import epollreactor
        epollreactor.install()
    from twisted.internet import reactor    
    
    from twisted.internet import protocol, reactor
    import sys
    
    log.startLogging(sys.stdout)
    
    mode = sys.argv[1]
    if mode == 'server':
        reactor.listenTCP(9990, pb.PBServerFactory(Server()))    
    else:
        callALot()
    
    reactor.run()    
