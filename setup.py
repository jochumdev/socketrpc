#!/usr/bin/env python

from distutils.core import setup

from socketrpc import __version__

setup(
    name = 'socketrpc',
    version = __version__,
    author = 'Rene Jochum',
    author_email = 'rene@jrit.at',
    description = 'simple socket rpc client/server for gevent and twisted',
    url = 'http://github.com/pcdummy/socketrpc',
    packages = ['socketrpc'],    
    classifiers = [
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],    
)
