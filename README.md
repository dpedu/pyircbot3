pyircbot3
=========
**A modular python IRC bot**

Quick start
-----------

* Install: `python3 setup.py install`
* Configure: `cd examples ; vim config.json data/config/Services.json`
* Run: `pyircbot -c config.json`

Running in docker
-----------------

A dockerfile is included at `examples/docker/`. From the *root* of this repository, run `docker build -t pyircbot -f examples/docker/Dockerfile .` to build it. Typical use is mounting a directory from the host onto `/srv/bot`; this dir should contain config.json and any other dirs it references.

Building Docs
-------------

* Install sphinx and all modules pyircbot depends on
* `cd docs ; make html`
* Open _build/index.html

Or, use my pre-built copy [here](http://davepedu.com/files/botdocs/).

Alternatively, use the included Dockerfile to create an environment for
building the docs. Check `docs/builder/README.md`.

Developing Modules
------------------

Check *Module Developer’s Guide* in the docs

TODO
----

* Improve/complete docs
* Write config checker
