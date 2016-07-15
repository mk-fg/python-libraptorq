#!/usr/bin/env python2
from __future__ import print_function

import itertools as it, operator as op, functools as ft
from os.path import dirname, basename, exists, isdir, join, abspath
import os, sys, types, math, json, base64


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

	cmd.add_argument('-j', '--threads',
		type=int, metavar='n',
		help='Number of encoder threads to use. 0 to scale to all cpus (default).')
	# cmd.add_argument('-t', '--rq-type',
	# 	default='32', metavar='{ NONE | 8 | 16 | 32 | 64 }',
	# 	help='No idea what it means, see RFC6330. Default: %(default)s')
	cmd.add_argument('-k', '--min-subsymbol-size',
		type=int, default=8, metavar='bytes',
		help='No idea what it means, see RFC6330. Default: %(default)s')
	cmd.add_argument('-s', '--symbol-size',
		type=int, default=16, metavar='bytes',
		help='Size of each indivisible (must either be present intact'
			' or lost entirely when decoding) symbol in the output. Default: %(default)s')
	cmd.add_argument('-m', '--max-memory',
		type=int, default=200, metavar='megabytes?',
		help='Uh... max memory in megs? Not sure. Default: %(default)s')

	cmd.add_argument('-n', '--repair-symbols-rate',
		default=0, type=float, metavar='float',
		help='Fraction of extra symbols to generate above what is required'
				' to reassemble to file as a fraction of that "required" count.'
			' For example, if 100 symbols are required, "-n 0.5" will generate 150 symbols.'
			' Default is to only generate required amount (i.e. "-n 0").')

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
	import logging
	logging.basicConfig(
		format='%(asctime)s :: %(levelname)s :: %(message)s',
		datefmt='%Y-%m-%d %H:%M:%S',
		level=logging.DEBUG if opts.debug else logging.WARNING )
	log = logging.getLogger()

	src = sys.stdin if not opts.path_src else open(opts.path_src, 'rb')
	try: data = src.read()
	finally: src.close()


	if opts.cmd == 'encode':
		data_len = len(data)
		if data_len % 4: data += '\0' * (4 - data_len % 4)
		with RQEncoder( data,
				opts.min_subsymbol_size, opts.symbol_size, opts.max_memory ) as enc:
			oti_scheme, oti_common = enc.oti_scheme, enc.oti_common
			enc.precompute(opts.threads, background=False)

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

		symbols = filter(None, symbols)
		if log.isEnabledFor(logging.DEBUG):
			log.debug(
				'Encoded %s B into %s symbols (needed: >%s, repair rate:'
					' %d%%), %s dropped (%d%%), %s left in output (%s B without ids)',
				num_fmt(data_len), num_fmt(len(symbols) + n_drop),
					num_fmt(enc_k), opts.repair_symbols_rate*100,
					num_fmt(n_drop), opts.drop_rate*100, num_fmt(len(symbols)),
					num_fmt(sum(len(s[1]) for s in symbols)) )
		data = json.dumps(
			dict( data_bytes=data_len,
				oti_scheme=oti_scheme, oti_common=oti_common,
				symbols=list((s[0], b64_encode(s[1])) for s in symbols) ),
			sort_keys=True, indent=2, separators=(',', ': ') )


	elif opts.cmd == 'decode':
		data = json.loads(data)
		n_syms, n_syms_total, n_sym_bytes = 0, len(data['symbols']), 0
		data_len = data['data_bytes']
		with RQDecoder(data['oti_common'], data['oti_scheme']) as dec:
			err = 'no symbols available'
			for sym_id, sym in data['symbols']:
				sym_id, sym = int(sym_id), b64_decode(sym)
				try: dec.add_symbol(sym, sym_id)
				except Exception as err: continue
				n_syms, n_sym_bytes = n_syms + 1, n_sym_bytes + len(sym)
				try: data = dec.decode()[:data_len]
				except RQError as err: pass
				else:
					if log.isEnabledFor(logging.DEBUG):
						log.debug(
							'Decoded %s B of data from %s processed'
								' symbols (%s B without ids, symbols total: %s)',
							num_fmt(len(data)), num_fmt(n_syms),
								num_fmt(n_sym_bytes), num_fmt(n_syms_total) )
					break
			else:
				log.error( 'Faled to decode data from %s'
					' total symbols (processed: %s) - %s', n_syms_total, n_syms, err )
				data = None


	else: raise NotImplementedError(opts.cmd)


	if data:
		dst = sys.stdout if not opts.path_dst else open(opts.path_dst, 'wb')
		try: dst.write(data)
		finally: dst.close()


if __name__ == '__main__': sys.exit(main())
