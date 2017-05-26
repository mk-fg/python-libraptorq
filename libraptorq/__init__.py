# -*- coding: utf-8 -*-
from __future__ import print_function

import itertools as it, operator as op, functools as ft
import math

from cffi import FFI
import ctypes.util


def _add_lib_wrappers(funcs=None, props=None):
	def make_ctx_func(func_name):
		ctx_fn = 'rq_{}'.format(func_name)
		def _ctx_func(self, *args):
			return getattr(self, ctx_fn)(*args)
		return _ctx_func
	def _add_wrappers(cls_name, cls_parents, cls_attrs):
		ctx_funcs, ctx_props = funcs or list(), props or list()
		for fn in it.chain(ctx_props, ctx_funcs):
			k = fn.lower()
			if k in cls_attrs: continue
			func = make_ctx_func(fn)
			if fn in ctx_props: func = property(func)
			cls_attrs[k] = func
		return type(cls_name, cls_parents, cls_attrs)
	return _add_wrappers


class RQError(Exception): pass

class RQObject(object):

	_cdefs = '''
		typedef uint64_t RaptorQ_OTI_Common_Data;
		typedef uint32_t RaptorQ_OTI_Scheme_Specific_Data;

		typedef enum {
			NONE = 0,
			ENC_8 = 1, ENC_16 = 2, ENC_32 = 3, ENC_64 = 4,
			DEC_8 = 5, DEC_16 = 6, DEC_32 = 7, DEC_64 = 8
		} RaptorQ_type;

		struct RaptorQ_ptr;

		struct RaptorQ_ptr* RaptorQ_Enc (
			const RaptorQ_type type,
			void *data,
			const uint64_t size,
			const uint16_t min_subsymbol_size,
			const uint16_t symbol_size,
			const size_t max_memory);

		struct RaptorQ_ptr* RaptorQ_Dec (
			const RaptorQ_type type,
			const RaptorQ_OTI_Common_Data common,
			const RaptorQ_OTI_Scheme_Specific_Data scheme);

		// Encoding

		RaptorQ_OTI_Common_Data RaptorQ_OTI_Common (struct RaptorQ_ptr *enc);
		RaptorQ_OTI_Scheme_Specific_Data RaptorQ_OTI_Scheme (struct RaptorQ_ptr *enc);

		uint16_t RaptorQ_symbol_size (struct RaptorQ_ptr *ptr);
		uint8_t RaptorQ_blocks (struct RaptorQ_ptr *ptr);
		uint32_t RaptorQ_block_size (struct RaptorQ_ptr *ptr, const uint8_t sbn);
		uint16_t RaptorQ_symbols (struct RaptorQ_ptr *ptr, const uint8_t sbn);
		uint32_t RaptorQ_max_repair (struct RaptorQ_ptr *enc, const uint8_t sbn);
		size_t RaptorQ_precompute_max_memory (struct RaptorQ_ptr *enc);

		void RaptorQ_precompute (
			struct RaptorQ_ptr *enc,
			const uint8_t threads,
			const bool background);

		uint64_t RaptorQ_encode_id (
			struct RaptorQ_ptr *enc,
			void **data,
			const uint64_t size,
			const uint32_t id);
		uint64_t RaptorQ_encode (
			struct RaptorQ_ptr *enc,
			void **data,
			const uint64_t size,
			const uint32_t esi,
			const uint8_t sbn);
		uint32_t RaptorQ_id (const uint32_t esi, const uint8_t sbn);

		// Decoding

		uint64_t RaptorQ_bytes (struct RaptorQ_ptr *dec);

		uint64_t RaptorQ_decode (
			struct RaptorQ_ptr *dec,
			void **data,
			const size_t size);
		uint64_t RaptorQ_decode_block (
			struct RaptorQ_ptr *dec,
			void **data,
			const size_t size,
			const uint8_t sbn);

		bool RaptorQ_add_symbol_id (
			struct RaptorQ_ptr *dec,
			void **data,
			const uint32_t size,
			const uint32_t id);
		bool RaptorQ_add_symbol (
			struct RaptorQ_ptr *dec,
			void **data,
			const uint32_t size,
			const uint32_t esi,
			const uint8_t sbn);

		// General: free memory

		void RaptorQ_free (struct RaptorQ_ptr **ptr);
		void RaptorQ_free_block (struct RaptorQ_ptr *ptr, const uint8_t sbn);
	'''
	_ctx = None

	data_size_div, _rq_type, _rq_blk = 4, 32, 'uint32_t'

	def __init__(self):
		self._ffi = FFI()
		self._ffi.cdef(self._cdefs)
		# self.ffi.set_source('_rq', '#include <RaptorQ/cRaptorQ.h>')
		lib_name = ctypes.util.find_library('RaptorQ') # newer cffi should not do that automatically
		self._lib = self._ffi.dlopen(lib_name) # ABI mode for simplicity
		self.rq_types = ( ['NONE', None]
			+ list('ENC_{}'.format(2**n) for n in xrange(3, 7))
			+ list('DEC_{}'.format(2**n) for n in xrange(3, 7)) )
		self._rq_blk_size = self.data_size_div

	def rq_type_val(self, v, pre):
		if isinstance(v, int) or v.isdigit(): v = '{}_{}'.format(pre, v).upper()
		else: v = bytes(v).upper()
		assert v in self.rq_types, [v, self.rq_types]
		return getattr(self._lib, v)

	def __getattr__(self, k):
		if k.startswith('rq_'):
			if not self._ctx: raise RuntimeError('ContextManager not initialized or already freed')
			return ft.partial(getattr(self._lib, 'RaptorQ_{}'.format(k[3:])), self._ctx)
		return self.__getattribute__(k)

	def open(self):
		self._ctx = self._ctx_init[0](*self._ctx_init[1])
		return self._ctx

	def close(self):
		if self._ctx:
			ptr = self._ffi.new('struct RaptorQ_ptr **')
			ptr[0] = self._ctx
			self._lib.RaptorQ_free(ptr)
			self._ctx = None

	def __enter__(self):
		self.open()
		return self
	def __exit__(self, *err): self.close()
	def __del__(self): self.close()


	def sym_id(self, esi, sbn): return self._lib.RaptorQ_id(esi, sbn)

	_sym_n = None
	def _sym_buff(self, init=None):
		if not self._sym_n: self._sym_n = self.symbol_size / self._rq_blk_size
		buff = self._ffi.new('{}[]'.format(self._rq_blk), self._sym_n)
		buff_ptr = self._ffi.new('void **', buff)
		buff_raw = self._ffi.buffer(buff)
		if init: buff_raw[:] = init
		return buff_ptr, lambda: bytes(buff_raw)


class RQEncoder(RQObject):

	__metaclass__ = _add_lib_wrappers(
		props=[ 'symbol_size', 'blocks', 'bytes',
			'precompute_max_memory', 'OTI_Common', 'OTI_Scheme' ],
		funcs=['block_size', 'symbols', 'free_block', 'max_repair'] )

	def __init__(self, data, min_subsymbol_size, symbol_size, max_memory, init_check=True):
		super(RQEncoder, self).__init__()
		self._sym_n = symbol_size / self._rq_blk_size
		assert len(data) % self._rq_blk_size == 0, len(data)
		rq_len = len(data) // self._rq_blk_size
		self._ctx_init_check = init_check
		self._ctx_init = self._lib.RaptorQ_Enc,\
			[ self.rq_type_val(self._rq_type, 'enc'), data, rq_len,
				min_subsymbol_size, symbol_size, max_memory ]

	def open(self):
		super(RQEncoder, self).open()
		if self._ctx_init_check and self.oti_scheme == self.oti_common == 0:
			raise RQError('Failed to initialize'
				' encoder for specified data and encoding parameters')
		return self._ctx

	def precompute(self, n_threads=None, background=False):
		return self.rq_precompute(n_threads or 0, background)

	def encode(self, sym_id=None, esi=None, sbn=None):
		buff_ptr, buff_get = self._sym_buff()
		if sym_id is not None:
			n = self.rq_encode_id(buff_ptr, self._sym_n, sym_id)
		elif esi is not None and sbn is not None:
			n = self.rq_encode(buff_ptr, self._sym_n, esi, sbn)
		else: raise ValueError(sym_id, esi, sbn)
		if n != self._sym_n: raise RQError('Failure when creating the symbol')
		return buff_get()

	def encode_block_iter(self):
		for sbn in xrange(self.blocks):
			yield RQEncoderBlock(self, sbn)

	def __iter__(self): return self.encode_block_iter()


class RQEncoderBlock(object):

	symbol_size = property(lambda s: s.encoder.symbol_size)
	symbols = property(lambda s: s.encoder.symbols(s.sbn))
	max_repair = property(lambda s: s.encoder.max_repair(s.sbn))

	def __init__(self, encoder, sbn):
		self.encoder, self.sbn = encoder, sbn

	def encode(self, esi):
		sym_id = self.encoder.sym_id(esi, self.sbn)
		return sym_id, self.encoder.encode(sym_id)

	def encode_iter(self, repair_rate=None, repair_count_max=None):
		n = self.symbols
		nr = int(math.ceil(n * repair_rate) if repair_rate is not None else 0)
		nr = min(nr, self.max_repair)
		if repair_count_max is not None: nr = min(nr, repair_count_max)
		for esi in xrange(n + nr): yield self.encode(esi)

	def __iter__(self): return self.encode_iter()


class RQDecoder(RQObject):

	__metaclass__ = _add_lib_wrappers(
		props=['symbol_size', 'blocks', 'bytes'],
		funcs=['block_size', 'symbols', 'max_repair'] )

	def __init__(self, oti_common, oti_scheme):
		super(RQDecoder, self).__init__()
		self._ctx_init = self._lib.RaptorQ_Dec,\
			[self.rq_type_val(self._rq_type, 'dec'), oti_common, oti_scheme]

	def __enter__(self):
		super(RQDecoder, self).__enter__()
		self._sym_n = self.symbol_size / self._rq_blk_size
		return self

	def add_symbol(self, sym, sym_id=None, esi=None, sbn=None):
		buff_ptr, buff_get = self._sym_buff(sym)
		assert len(sym) == self._sym_n * self._rq_blk_size
		if sym_id is not None:
			chk = self.rq_add_symbol_id(buff_ptr, self._sym_n, sym_id)
		elif esi is not None and sbn is not None:
			chk = self.rq_add_symbol(buff_ptr, self._sym_n, esi, sbn)
		else: raise ValueError(sym_id, esi, sbn)
		if not chk:
			raise RQError( 'Failed to decode symbol'
				' (id: {}/{}/{}, data: {!r})'.format(sym_id, esi, sbn, sym) )

	def _block_buff(self, bs):
		buff_n = int(math.ceil(bs / float(self._rq_blk_size)))
		buff = self._ffi.new('{}[]'.format(self._rq_blk), buff_n)
		buff_ptr = self._ffi.new('void **', buff)
		return buff_n, buff_ptr, lambda n: bytes(self._ffi.buffer(buff, n))

	def decode(self, partial=False):
		buff_n, buff_ptr, buff_get = self._block_buff(self.bytes)
		n = self.rq_decode(buff_ptr, buff_n)
		if not partial and n != buff_n:
			raise RQError('Failed to decode data - not enough symbols received')
		return buff_get(n * self._rq_blk_size)

	def decode_block(self, sbn, partial=False):
		buff_n, buff_ptr, buff_get = self._block_buff(self.block_size(sbn))
		n = self.rq_decode_block(buff_ptr, buff_n, sbn)
		if not partial and n != buff_n:
			raise RQError('Failed to decode data - not enough symbols received')
		return buff_get(n * self._rq_blk_size)
