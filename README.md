Socketrpc client/server
============

Introduction
---------
This is a simple socket rpc client/server for gevent and twisted

I use this a replacement for "Perspective Broker" of Twisted
as i'm switching from Twisted to gevent.

It uses a very simple dataformat to transfer calls:

    Client: --> {call: [method, params, call_id]}
    Server: <-- {reply: [status, result, call_id]}

On the network level it uses a sized format:

    [(uint16_t)serialized size][serialized data]

Example:

    Client: --> {"call": ["echo", "hello world", 1]}
    Server: --> {"reply": [0, "hello world", 1]}

Its also possible for the server to call on the client:

    Server: --> {"call": ["echo", "hello world", 1]}
    Client: --> {"reply": [0, "hello world", 1]}

Features
---------
* Two-way calls over a single socket
* Supports different serializers
* Native implementions for both Twisted and gevent

Requirements
---------
* gevent >= 0.13.0 for the gevent variant
* Twisted >= 10.1 for the twisted variant

* bson for the bson serializer
* jsonlib for the jsonlib serializer

Roadmap
---------
- 0.0.2 - Docs bugfixes
- 0.0.3 - Unittests
- 0.0.4 - ?
- 1.0.0 - Stable API, following http://semver.org/ from this point on

Howto
---------
For now see examples/twisted_srpc.py and examples/gevent_srpc.py

- Start a gevent server with the bson serializer

    $ ./examples/gevent_srpc.py -d -s bson server

- Run 100 calls on the server

    ./examples/gevent_srpc.py -d -s bson -r 100 clientserial

- Run a bounced call (Client calls server to call the client)

    $ ./examples/gevent_srpc.py -d -s bson clientsingle

Copyright
---------
Copyright (c) 2011 Rene Jochum, See LICENSE for details. (NEW-BSD)
