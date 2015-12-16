python-libraptorq
=================

Python 2.X CFFI_ bindings for libRaptorQ_ - C++11 implementation of RaptorQ
Forward Error Correction codes, as described in RFC6330_.

**Warning**: as far as I know (not a lawyer), there are lots of patents around
the use of this technology, which might be important for any high-profile and
commercial projects, especially in US and Canada.

Quoting `wikipedia on Raptor code`_:

  Raptor codes, as with fountain codes in general, encode a given message
  consisting of a number of symbols, k, into a potentially limitless sequence of
  encoding symbols such that knowledge of any k or more encoding symbols allows
  the message to be recovered with some non-zero probability.

  Raptor ("RApid TORnado") codes are the first known class of fountain codes
  with linear time encoding and decoding.

And RFC6330_:

  RaptorQ codes are a new family of codes that provide superior flexibility,
  support for larger source block sizes, and better coding efficiency than
  Raptor codes in RFC 5053.

  ... in most cases, a set of cardinality equal to the number of source symbols
  is sufficient; in rare cases, a set of cardinality slightly more than the
  number of source symbols is required.

In practice this means that source data block of size 1 MiB (for example) can be
recovered from any 1.002 MiB of the received symbols for it (from `"Application
Layer Forward Error Correction for Mobile Multimedia Broadcasting Case Study"
paper`_).

| Whole input can have up to 256 "source blocks" (encoded independently).
| Each block can have up to 56.403 symbols.
| Each symbol can be up to 65.535 (2**16 - 1) bytes long.
| Which sums up to ~881 GiB max for one input.

.. _CFFI: http://cffi.readthedocs.org/
.. _libRaptorQ: https://github.com/LucaFulchir/libRaptorQ/
.. _RFC6330: https://tools.ietf.org/html/rfc6330
.. _wikipedia on Raptor code: https://en.wikipedia.org/wiki/Raptor_code
.. _"Application Layer Forward Error Correction for Mobile Multimedia Broadcasting Case Study" paper:
   https://www.qualcomm.com/media/documents/files/raptor-codes-for-mobile-multimedia-broadcasting-case-study.pdf


------

.. contents::
  :backlinks: none

------



Usage
-----

Module includes command-line script ("rq", when installed or as symlink in the
repo), which has example code for both encoding and decoding, and can be used as
a standalone tool, or for basic algorithm testing/showcase.

Can also be used from command-line via ``python2 -m libraptorq ...`` invocation
(when installed as module), e.g. ``python2 -m libraptorq --help``.

Command-line script
'''''''''''''''''''

To encode file, with 50% extra symbols (resulting indivisible data chunks to be
stored/transmitted intact or lost entirely) and 30% of total from these (K
required symbols + X repair symbols) dropped (just for testing purposes) before
saving them to "setup.py.enc"::

  % ./rq --debug encode --repair-symbols-rate 0.5 --drop-rate 0.3 setup.py setup.py.enc
  2015-12-16 15:59:00 :: DEBUG :: Encoded 629 symbols\
    (needed: >419, repair rate: 50%), 189 dropped (30%), 440 left in output

Decode original file back from these::

  % ./rq --debug decode setup.py.enc setup.py.dec
  2015-12-16 15:57:09 :: DEBUG :: Decoded 1673B of data from 440 symbols (total, discarded: 0)

  % sha256sum -b setup.py{,.dec}
  0a19b84ca98562476f79d55f19ac853ea49e567205dcc9139ba986e8572f9681 *setup.py
  0a19b84ca98562476f79d55f19ac853ea49e567205dcc9139ba986e8572f9681 *setup.py.dec

No matter which chunks are dropped (get picked by ``random.choice``), file
should be recoverable from output as long as number of chunks left (in each
"block") is slightly (by ~0.02%) above K.

Output data ("setup.py.enc" in the example) for the script is JSON-encoded list
of base64-encoded symbols, as well as some parameters for lib init
("oti_scheme", "oti_common").

See output with --help option for all the other script parameters.

Python module
'''''''''''''

To use as a python2 module::

  from libraptorq import RQEncoder

  data = sys.stdin.read()

  with RQEncoder(data, min_subsymbol_size=4, symbol_size=16, max_memory=200) as enc:

    symbols = dict()
    oti_scheme, oti_common = enc.oti_scheme, enc.oti_common

    for block in enc:
      symbols.update(block.encode_iter(repair_rate=0))

  data_encoded = oti_scheme, oti_common, symbols

"oti_scheme" and "oti_common" are two integers specifying encoder options,
needed to initialize decoder, which can be hard-coded (if constant) on both ends.

``block.encode_iter()`` can be used without options to produce max possible
amount of symbols, up to ``block.symbols + block.max_repair``.
Above example only produces K symbols - min amount required.

For decoding (reverse operation)::

  from libraptorq import RQDecoder

  oti_scheme, oti_common, symbols = data_encoded

  with RQDecoder(oti_scheme, oti_common) as dec:
    for sym_id, sym in symbols.viewitems(): dec.add_symbol(sym, sym_id)

    data = dec.decode()

Note that in practice, e.g. when transmitting each symbol in a udp packet, one'd
want to send something like ``sym_id || sym_data || checksum``, and keep sending
these from ``block.encode_iter()`` until other side acknowledges that it can
decode a block (i.e. enough symbols received, see ``RQDecoder.decode_block()``),
then start streaming the next block in similar fashion.

See `__main__.py
<https://github.com/mk-fg/python-libraptorq/blob/master/libraptorq/__main__.py>`_
file (cli script) for an extended example, and libRaptorQ_ docs for info on its
API, which this module wraps around.



Installation
------------

It's a regular package for Python 2.7 (not 3.X).

It uses and needs CFFI_ (can/should be installed by pip_) and libRaptorQ_
installed on the system.

Using pip_ is the best way::

  % pip install libraptorq

If you don't have it, use::

  % easy_install pip
  % pip install libraptorq

Alternatively (see also `pip2014.com`_ and `pip install guide`_)::

  % curl https://raw.github.com/pypa/pip/master/contrib/get-pip.py | python2
  % pip install libraptorq

Or, if you absolutely must::

  % easy_install libraptorq

But, you really shouldn't do that.

Current-git version can be installed like this::

  % pip install 'git+https://github.com/mk-fg/python-libraptorq.git#egg=libraptorq'

Note that to install stuff in system-wide PATH and site-packages, elevated
privileges are often required.
Use "install --user", `~/.pydistutils.cfg`_ or virtualenv_ to do unprivileged
installs into custom paths.

Alternatively, ``./rq`` tool can be run right from the checkout tree without any
installation, if that's the only thing you need there.

.. _pip: http://pip-installer.org/
.. _pip2014.com: http://pip2014.com/
.. _pip install guide: http://www.pip-installer.org/en/latest/installing.html
.. _~/.pydistutils.cfg: http://docs.python.org/install/index.html#distutils-configuration-files
.. _virtualenv: http://pypi.python.org/pypi/virtualenv



Random Notes
------------

* libRaptorQ is currently used via CFFI in "ABI Mode" to avoid any extra hassle
  with compilation and the need for compiler, see `CFFI docs on the subject`_
  for more info on what it means.

* When testing decoding of some encoded data, noticed that libRaptorQ
  *sometimes* returns errors for ``add_symbol()`` calls, essentially discarding
  some valid symbols.

  Not sure if that's supposed to happen (again, lack of familiarity with the
  algo), but stuff usually can be decoded already when this starts to happen.

* libRaptorQ allows to specify "rq_type" parameter, which is hard-coded to
  ENC_32/DEC_32 in the module for now, for simplicity.

* Lack of Python 3.X compatibility is due to me not using it at all (yet?), so
  don't need it, have nothing against it in principle.

.. _CFFI docs on the subject: https://cffi.readthedocs.org/en/latest/cdef.html
