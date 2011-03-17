# -*- coding: utf-8 -*-
# vim: set et sts=4 sw=4 encoding=utf-8:
#
###############################################################################
#
# This file is part of socketrpc, it is a compat library for shared data
# between twisted_srpc and gevent_srpc
#
# Copyright (C) 2011  Rene Jochum <rene@jrit.at>
#
###############################################################################

__version__ = '0.0.2'

import xmlrpclib
import struct

struct_error = struct.error

# -32768 - 32000 is reserved for RPC errors
# @see: http://xmlrpc-epi.sourceforge.net/specs/rfc.fault_codes.php
# Ranges of errors
PARSE_ERROR = xmlrpclib.PARSE_ERROR
SERVER_ERROR = xmlrpclib.SERVER_ERROR
APPLICATION_ERROR = xmlrpclib.APPLICATION_ERROR
#SYSTEM_ERROR = xmlrpclib.SYSTEM_ERROR
TRANSPORT_ERROR = xmlrpclib.TRANSPORT_ERROR

# Specific errors
NOT_WELLFORMED_ERROR = xmlrpclib.NOT_WELLFORMED_ERROR
UNSUPPORTED_ENCODING = xmlrpclib.UNSUPPORTED_ENCODING
#INVALID_ENCODING_CHAR = xmlrpclib.INVALID_ENCODING_CHAR
#INVALID_SRPC = xmlrpclib.INVALID_XMLRPC
METHOD_NOT_FOUND = xmlrpclib.METHOD_NOT_FOUND
#INVALID_METHOD_PARAMS = xmlrpclib.INVALID_METHOD_PARAMS
#INTERNAL_ERROR = xmlrpclib.INTERNAL_ERROR

STATUS_OK = 0

Fault = xmlrpclib.Fault
SUPPORTED_TRANSACTIONS = set(('call', 'reply'))

STRUCT_INT = struct.Struct("!I")

def set_serializer2(predefined=None, encode=None, decode=None, gls=None):
    """ Sets the serializer for the gls globals.
    
    set a serializer by:
        set_serializer2(<serializer>, gls=globals())
    or your own implementation:
        ser_serializer(encode=<your encoder>, decode=<your decoder>, gls=globals())
    
    Currently it supports 3 predefined serializers:
        <bson>      -   As fast as "cPickle/2" and secure.
        <jsonlib>   -   Same as "bson" but utilizes a higher network load.
        <pickle2>   -   The fastest but insecure, great to transfer objects internally.
        
    Own serializer notes:
        Please make sure to translate the serializers exception to Fault exceptions!
    """
    if gls is None:
        gls = globals()

    if encode and decode:
        gls['encode'] = encode
        gls['decode'] = decode

    elif predefined is not None:
        if predefined == 'bson':
            import bson
            def encode(data):
                """
                Encodes data returns a BSON object or
                a Fault
                """
                try:
                    return bson.BSON.encode(data)
                except bson.errors.InvalidBSON, e:
                    return Fault(NOT_WELLFORMED_ERROR, 'Invalid BSON Data: %s' % e)
                except bson.errors.InvalidDocument, e:
                    return Fault(NOT_WELLFORMED_ERROR, 'Invalid BSON Data: %s' % e)
                except bson.errors.InvalidStringData, e:
                    return Fault(UNSUPPORTED_ENCODING, 'Non UTF-8 BSON Data: %s' % e)

            def decode(data):
                """
                A proxy method for BSON.decode
                TODO: This will block if a lot data has been received!
                """
                try:
                    return bson.BSON(data).decode()
                except bson.errors.InvalidBSON:
                    return Fault(NOT_WELLFORMED_ERROR, 'Invalid BSON Data')
                except bson.errors.InvalidDocument:
                    return Fault(NOT_WELLFORMED_ERROR, 'Invalid BSON Data')
                except bson.errors.InvalidStringData:
                    return Fault(UNSUPPORTED_ENCODING, 'Non UTF-8 BSON Data')

            set_serializer2(encode=encode, decode=decode, gls=gls)

        elif predefined == 'jsonlib':
            import jsonlib

            def encode(data):
                """
                Encodes data returns a BSON object or
                a Fault
                """
                try:
                    return jsonlib.dumps(data)
                except Exception, e:
                    msg = 'Invalid JSON Data, got: %s:%s' % (e.__class__.__name__, e)
                    return Fault(NOT_WELLFORMED_ERROR, msg)

            def decode(data):
                """
                A proxy method for BSON.decode
                TODO: This will block if a lot data has been received!
                """
                try:
                    return jsonlib.loads(data)
                except Exception, e:
                    msg = 'Invalid JSON Data, got: %s:%s' % (e.__class__.__name__, e)
                    return Fault(NOT_WELLFORMED_ERROR, msg)

            set_serializer2(encode=encode, decode=decode, gls=gls)

        elif predefined == 'pickle2':
            try:
                import cPickle as pickle
            except ImportError:
                import pickle as pickle

            def encode(data):
                """
                Encodes data returns a BSON object or
                a Fault
                """
                try:
                    return pickle.dumps(data, 2)
                except pickle.PicklingError, e:
                    msg = 'Invalid pickle Data, got: %s:%s' % (e.__class__.__name__, e)
                    return Fault(NOT_WELLFORMED_ERROR, msg)
                except EOFError, e:
                    msg = 'Invalid pickle Data, got: %s:%s' % (e.__class__.__name__, e)
                    return Fault(NOT_WELLFORMED_ERROR, msg)

            def decode(data):
                """
                A proxy method for BSON.decode
                TODO: This will block if a lot data has been received!
                """
                try:
                    return pickle.loads(data)
                except pickle.UnpicklingError, e:
                    msg = 'Invalid pickle Data, got: %s:%s' % (e.__class__.__name__, e)
                    return Fault(NOT_WELLFORMED_ERROR, msg)
                except EOFError, e:
                    msg = 'Invalid pickle Data, got: %s:%s' % (e.__class__.__name__, e)
                    return Fault(NOT_WELLFORMED_ERROR, msg)

            set_serializer2(encode=encode, decode=decode, gls=gls)
