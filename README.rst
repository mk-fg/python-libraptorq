python-libraptorq
=================

Python 2.X CFFI_ bindings for libRaptorQ_ v0.1.x - C++11 implementation of
RaptorQ Forward Error Correction codes, as described in RFC6330_.

**Warning**: Using libRaptorQ RFC6330 API (which this module wraps around)
properly requires knowledge of some concepts and parameters described in that
RFC, and not using correct ones may result in undecodable data!
See "Usage" section below for more details.

**Warning**: As far as I know (not a lawyer), there are lots of patents around
the use of this technology, which might be important for any high-profile and
commercial projects, especially in US and Canada.

|

.. contents::
  :backlinks: none

.. _CFFI: http://cffi.readthedocs.org/
.. _libRaptorQ: https://www.fenrirproject.org/Luker/libRaptorQ/wikis/home
.. _RFC6330: https://tools.ietf.org/html/rfc6330



General info
------------

Quoting `wikipedia on Raptor code`_:

  Raptor codes, as with fountain codes in general, encode a given message
  consisting of a number of symbols, k, into a potentially limitless sequence of
  encoding symbols such that knowledge of any k or more encoding symbols allows
  the message to be recovered with some non-zero probability.

  Raptor ("RAPid TORnado") codes are the first known class of fountain codes
  with linear time encoding and decoding.

And RFC6330_:

  RaptorQ codes are a new family of codes that provide superior flexibility,
  support for larger source block sizes, and better coding efficiency than
  Raptor codes in RFC 5053.

  ... in most cases, a set of cardinality equal to the number of source symbols
  is sufficient; in rare cases, a set of cardinality slightly more than the
  number of source symbols is required.

In practice this means that source data block of size 1 MiB (for example) can
(with very high probability) be recovered from any 1.002 MiB of the received
symbols for it (from `"Application Layer Forward Error Correction for Mobile
Multimedia Broadcasting Case Study" paper`_).

Note that being a probablilistic algorithm, RaptorQ can have highly-improbable
pathological cases and be exploited through these e.g. by dropping specific data
blocks (see `"Stopping a Rapid Tornado with a Puff" paper`_ for more details).

Encoded data will be roughly same size as original plus the "repair symbols",
i.e. almost no size overhead, except for what is intentionally generated.

.. _wikipedia on Raptor code: https://en.wikipedia.org/wiki/Raptor_code
.. _"Application Layer Forward Error Correction for Mobile Multimedia Broadcasting Case Study" paper:
   https://www.qualcomm.com/media/documents/files/raptor-codes-for-mobile-multimedia-broadcasting-case-study.pdf
.. _"Stopping a Rapid Tornado with a Puff" paper: http://jmsalopes.com/pubs/sp.pdf



Usage
-----

Module includes command-line script ("rq", when installed or as symlink in the
repo), which has example code for both encoding and decoding, and can be used as
a standalone tool, or for basic algorithm testing/showcase.

Can also be used from command-line via ``python2 -m libraptorq ...`` invocation
(when installed as module), e.g. ``python2 -m libraptorq --help``.

**Important**: With current 0.1.x libRaptorQ API, specifying unsuitable
parameters for encoding, such as having symbol_size=16 and max_memory=200 for
encoding 200K+ of data WILL result in **silently** producing encoded data that
**cannot be decoded**.


Command-line script
'''''''''''''''''''

Note: it's just an example/testing script to run and check if module works with
specific parameters or see how to use it, don't rely on it as a production tool
or anything like that.

To encode file, with 50% extra symbols (resulting indivisible data chunks to be
stored/transmitted intact or lost entirely) and 30% of total from these (K
required symbols + X repair symbols) dropped (for testing purposes) before
saving them to "setup.py.enc"::

  % ./rq --debug encode -s16 -m200 --repair-symbols-rate 0.5 --drop-rate 0.3 setup.py setup.py.enc
  Initialized RQEncoder (0.063s)...
  Precomputed blocks (0.002s)...
  Finished encoding symbols (9 blocks, 0.008s)...
  Closed RQEncoder (0.002s)...
  Encoded 1,721 B into 167 symbols (needed: >108, repair rate: 50%),
    45 dropped (30%), 122 left in output (1,952 B without ids)

Decode original file back from these::

  % ./rq --debug decode setup.py.enc setup.py.dec
  Initialized RQDecoder (0.064s)...
  Decoded enough symbols to recover data (0.010s)...
  Closed RQDecoder (0.002s)...
  Decoded 1,721 B of data from 108 processed symbols (1,728 B without ids, symbols total: 122)

  % sha256sum -b setup.py{,.dec}
  36c50348459b51821a2715b0f5c4ef08647d66f77a29913121af4f0f4dfef454 *setup.py
  36c50348459b51821a2715b0f5c4ef08647d66f77a29913121af4f0f4dfef454 *setup.py.dec

No matter which chunks are dropped (get picked by ``random.choice``), file
should be recoverable from output as long as number of chunks left (in each
"block") is slightly (by ~0.02%) above K.

Output data ("setup.py.enc" in the example) for the script is JSON-encoded list
of base64-encoded symbols, as well as some parameters for lib init
(``oti_scheme``, ``oti_common``).

Input data length and sha256 hash of source data are only there to make sure
that decoded data is same as original (or exit with error otherwise).

See output with --help option for all the other script parameters.


Python module
'''''''''''''

To use as a python2 module::

  from libraptorq import RQEncoder

  data = 'some input string' * 500

  # Data size must be divisible by RQEncoder.data_size_div
  data_len, n = len(data), RQEncoder.data_size_div
  if data_len % n: data += '\0' * (n - data_len % n)

  with RQEncoder(data, min_subsymbol_size=4, symbol_size=16, max_memory=200) as enc:

    symbols = dict()
    oti_scheme, oti_common = enc.oti_scheme, enc.oti_common

    for block in enc:
      symbols.update(block.encode_iter(repair_rate=0))

  data_encoded = data_len, oti_scheme, oti_common, symbols

``oti_scheme`` and ``oti_common`` are two integers specifying encoder options,
needed to initialize decoder, which can be hard-coded (if constant) on both ends.

``block.encode_iter()`` can be used without options to produce max possible
amount of symbols, up to ``block.symbols + block.max_repair``.
Above example only produces K symbols - min amount required.

For decoding (reverse operation)::

  from libraptorq import RQDecoder

  data_len, oti_scheme, oti_common, symbols = data_encoded

  with RQDecoder(oti_common, oti_scheme) as dec:
    for sym_id, sym in symbols.viewitems(): dec.add_symbol(sym, sym_id)

    data = dec.decode()[:data_len]

Note that in practice, e.g. when transmitting each symbol in a udp packet, one'd
want to send something like ``sym_id || sym_data || checksum``, and keep sending
these from ``block.encode_iter()`` until other side acknowledges that it can
decode a block (i.e. enough symbols received, see ``RQDecoder.decode_block()``),
then start streaming the next block in similar fashion.

See `__main__.py
<https://github.com/mk-fg/python-libraptorq/blob/master/libraptorq/__main__.py>`_
file (cli script) for an extended example, and libRaptorQ_ docs for info on its
C API, which this module wraps around.



Installation
------------

It's a regular package for Python 2.7 (not 3.X).

It uses and needs CFFI_ (can/should be installed by pip_) and libRaptorQ_ v0.1.x
installed (as libRaptorQ.so) on the system.

libRaptorQ v1.x (as opposed to current stable version 0.1.9) has different API
and **will not** work with this module.

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

* See `github-issue-1`_ for more info on what happens when encoding parameters
  (such as symbol_size and max_memory) are specified carelessly, and why
  command-line interface of this module does not have defaults for these.

* libRaptorQ is currently used via CFFI in "ABI Mode" to avoid any extra hassle
  with compilation and the need for compiler, see `CFFI docs on the subject`_
  for more info on what it means.

* When decoding, libRaptorQ can raise errors for ``add_symbol()`` calls, when
  source block is already decoded and that extra symbol is not needed.

* libRaptorQ allows to specify "rq_type" parameter for internal data alignment
  size (C++ iterator element), which is hard-coded to RQ_ENC_32/RQ_DEC_32
  in the module, for simplicity.

* Lack of Python 3.X compatibility is due to me not using it at all (yet?), so
  don't need it, have nothing against it in principle.

.. _github-issue-1: https://github.com/mk-fg/python-libraptorq/issues/1
.. _CFFI docs on the subject: https://cffi.readthedocs.org/en/latest/cdef.html
