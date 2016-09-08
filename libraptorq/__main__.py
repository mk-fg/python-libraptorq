#!/usr/bin/env python2
from __future__ import print_function

import itertools as it, operator as op, functools as ft
from os.path import dirname, basename, exists, isdir, join, abspath
import os, sys, types, math, json, base64, hashlib, logging, time


try: import libraptorq
except ImportError:
	# Make sure tool works from a checkout
	if __name__ != '__main__': raise
	pkg_root = abspath(dirname(__file__))
	for pkg_root in pkg_root, dirname(pkg_root):
		if isdir(join(pkg_root, 'libraptorq'))\
				and exists(join(pkg_root, 'setup.py')):
			sys.path.insert(0, dirname(__file__))
			try: import libraptorq
			except ImportError: pass
			else: break
	else: raise ImportError('Failed to find/import "libraptorq" module')

from libraptorq import RQEncoder, RQDecoder, RQError


sys.stdout, sys.stderr = (
	os.fdopen(s.fileno(), 'wb', 0) for s in [sys.stdout, sys.stderr] )
p = lambda fmt,*a,**k:\
	print(*( [fmt.format(*a,**k)]\
		if isinstance(fmt, types.StringTypes) and (a or k)
		else [[fmt] + list(a), k] ), file=sys.stderr)

b64_encode = base64.urlsafe_b64encode
b64_decode = lambda s:\
	base64.urlsafe_b64decode(bytes(s))\
		if '-' in s or '_' in s else bytes(s).decode('base64')

num_fmt = lambda n: '{:,}'.format(n)

def _timer_iter():
	ts0 = time.time()
	while True:
		ts = time.time()
		ts_diff, ts0 = ts - ts0, ts
		yield ts_diff

def timer_iter():
	timer = _timer_iter()
	next(timer)
	return timer


class EncDecFailure(Exception): pass

def encode(opts, data):
	data_len, data_sha256 = len(data), hashlib.sha256(data).digest()
	if data_len % 4: data += '\0' * (4 - data_len % 4)
	timer = timer_iter()
	with RQEncoder( data,
			opts.subsymbol_size, opts.symbol_size, opts.max_memory ) as enc:
		log.debug('Initialized RQEncoder (%.3fs)...', next(timer))
		oti_scheme, oti_common = enc.oti_scheme, enc.oti_common
		if not opts.no_precompute:
			enc.precompute(opts.threads, background=False)
			log.debug('Precomputed blocks (%.3fs)...', next(timer))

		symbols, enc_k, n_drop = list(), 0, 0
		for block in enc:
			enc_k += block.symbols # not including repair ones
			block_syms = list(block.encode_iter(
				repair_rate=opts.repair_symbols_rate ))
			if opts.drop_rate > 0:
				import random
				n_drop_block = int(round(len(block_syms) * opts.drop_rate, 0))
				for n in xrange(n_drop_block):
					block_syms[int(random.random() * len(block_syms))] = None
				n_drop += n_drop_block
			symbols.extend(block_syms)
		log.debug('Finished encoding symbols (%s blocks, %.3fs)...', enc.blocks, next(timer))
	log.debug('Closed RQEncoder (%.3fs)...', next(timer))

	symbols = filter(None, symbols)
	if log.isEnabledFor(logging.DEBUG):
		log.debug(
			'Encoded %s B into %s symbols (needed: >%s, repair rate:'
				' %d%%), %s dropped (%d%%), %s left in output (%s B without ids)',
			num_fmt(data_len), num_fmt(len(symbols) + n_drop),
				num_fmt(enc_k), opts.repair_symbols_rate*100,
				num_fmt(n_drop), opts.drop_rate*100, num_fmt(len(symbols)),
				num_fmt(sum(len(s[1]) for s in symbols)) )

	return dict( data_bytes=data_len,
		oti_scheme=oti_scheme, oti_common=oti_common,
		symbols=list((s[0], b64_encode(s[1])) for s in symbols),
		checksums=dict(sha256=b64_encode(data_sha256)) )


def decode(opts, data):
	data_dec = _decode(opts, data)
	if data['data_bytes'] != len(data_dec):
		raise EncDecFailure(
			'Data length mismatch - {} B encoded vs {} B decoded'
			.format(num_fmt(data['data_bytes']), num_fmt(len(data_dec))) )
	data_chk = data.get('checksums', dict())
	for k, v in data_chk.viewitems():
		v = b64_decode(v)
		if getattr(hashlib, k)(data_dec).digest() != v:
			raise EncDecFailure('Data checksum ({}) mismatch'.format(k))
	return data_dec

def _decode(opts, data):
	n_syms, n_syms_total, n_sym_bytes = 0, len(data['symbols']), 0
	if ( not data['symbols'] # zero-input/zero-output case
		and data['oti_common'] == data['oti_scheme'] == 0 ): return ''
	timer = timer_iter()
	with RQDecoder(data['oti_common'], data['oti_scheme']) as dec:
		log.debug('Initialized RQDecoder (%.3fs)...', next(timer))
		err = 'no symbols available'
		for sym_id, sym in data['symbols']:
			sym_id, sym = int(sym_id), b64_decode(sym)
			try: dec.add_symbol(sym, sym_id)
			except RQError as err: continue
			n_syms, n_sym_bytes = n_syms + 1, n_sym_bytes + len(sym)
			try: data = dec.decode()[:data['data_bytes']] # strips \0 padding to rq block size
			except RQError as err: pass
			else:
				log.debug('Decoded enough symbols to recover data (%.3fs)...', next(timer))
				break
		else:
			raise EncDecFailure(( 'Faled to decode data from {}'
				' total symbols (processed: {}) - {}' ).format(n_syms_total, n_syms, err))
	log.debug('Closed RQDecoder (%.3fs)...', next(timer))
	if log.isEnabledFor(logging.DEBUG):
		log.debug(
			'Decoded %s B of data from %s processed'
				' symbols (%s B without ids, symbols total: %s)',
			num_fmt(len(data)), num_fmt(n_syms),
				num_fmt(n_sym_bytes), num_fmt(n_syms_total) )
	return data


def main(args=None, error_func=None):
	import argparse
	parser = argparse.ArgumentParser(
		description='Encode/decode data using RaptorQ rateless'
			' erasure encoding ("fountain code") algorithm, using libRaptorQ through CFFI.')
	parser.add_argument('--debug', action='store_true', help='Verbose operation mode.')
	cmds = parser.add_subparsers( dest='cmd',
		title='Supported operations (have their own suboptions as well)' )


	cmd = cmds.add_parser('encode',
		help='Encode file into chunks and dump these along with OTI parameters as a JSON structure.')
	cmd.add_argument('path_src', nargs='?',
		help='Path to a file which contents should be encoded. Stdin will be used, if not specified.')
	cmd.add_argument('path_dst', nargs='?',
		help='Path to write resulting JSON to. Will be dumped to stdout, if not specified.')

	cmd.add_argument('--no-precompute', action='store_true',
		help='Do not run precompute() synchronously before encoding symbols.'
			' Should be much slower, so probably only useful for benchmarking or debugging.')
	cmd.add_argument('-j', '--threads',
		type=int, metavar='n',
		help='Number of encoder threads to use. 0 to scale to all cpus (default).')
	cmd.add_argument('-k', '--subsymbol-size',
		type=int, metavar='bytes',
		help='Should almost always be equal to symbol size.'
			' See RFC6330 for details. Set to value of symbols size if not specified.')
	cmd.add_argument('-s', '--symbol-size',
		required=True, type=int, metavar='bytes',
		help='Size of each indivisible (must either be'
				' present intact or lost entirely when decoding) symbol in the output.'
			' Using wrong value here (for data size) can result in undecodable output.'
			' See RFC6330 or libRaptorQ code/docs for more information.'
			' Must be specified manually.')
	cmd.add_argument('-m', '--max-memory',
		required=True, type=int, metavar='int',
		help='Value for working memory of the decoder,'
			' see RFC6330 or libRaptorQ code/docs for more information.'
			' Raise it if encoding fails to produce valid (decodable) data.'
			' Must be specified manually.')

	cmd.add_argument('-n', '--repair-symbols-rate',
		required=True, type=float, metavar='float',
		help='Fraction of extra symbols to generate above what is required'
				' to reassemble to file as a fraction of that "required" count.'
			' For example, if 100 symbols are required, "-n 0.5" will generate 150 symbols.'
			' Must be specified manually.')

	cmd.add_argument('-d', '--drop-rate',
		default=0, type=float, metavar='0-1.0',
		help='Drop specified randomly-picked fraction'
				' of symbols encoded for each block (incl. ones for repair).'
			' I.e. just discard these right after encoding. Mainly useful for testing.')


	cmd = cmds.add_parser('decode', help='Decode lines of base64 into a file.')
	cmd.add_argument('path_src', nargs='?',
		help='Path to a file with JSON structure, such as produced by "encode" operation.'
			' Stdin will be used, if not specified.')
	cmd.add_argument('path_dst', nargs='?',
		help='Path to write assembled file to. Will be dumped to stdout, if not specified.')


	opts = parser.parse_args(sys.argv[1:] if args is None else args)

	global log
	logging.basicConfig(
		format='%(asctime)s :: %(levelname)s :: %(message)s',
		datefmt='%Y-%m-%d %H:%M:%S',
		level=logging.DEBUG if opts.debug else logging.WARNING )
	log = logging.getLogger()

	src = sys.stdin if not opts.path_src else open(opts.path_src, 'rb')
	try: data = src.read()
	finally: src.close()

	try:
		if opts.cmd == 'encode':
			if not opts.subsymbol_size: opts.subsymbol_size = opts.symbol_size
			try: data = encode(opts, data)
			except RQError as err: raise EncDecFailure(str(err))
			data = json.dumps(data, sort_keys=True, indent=2, separators=(',', ': '))
		elif opts.cmd == 'decode':
			data = decode(opts, json.loads(data))
		else: raise NotImplementedError(opts.cmd)
	except EncDecFailure as err:
		log.error('Operation failed - %s', err)
		return 1

	if data is not None:
		dst = sys.stdout if not opts.path_dst else open(opts.path_dst, 'wb')
		try: dst.write(data)
		finally: dst.close()


if __name__ == '__main__': sys.exit(main())
