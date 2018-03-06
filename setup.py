#!/usr/bin/env python2
#-*- coding: utf-8 -*-

from setuptools import setup, find_packages
import os, sys

# Error-handling here is to allow package to be built w/o README included
try:
	readme = open(os.path.join(
		os.path.dirname(__file__), 'README.rst' )).read()
except IOError: readme = ''

setup(

	name = 'libraptorq',
	version = '18.3.0',
	author = 'Mike Kazantsev',
	author_email = 'mk.fraggod@gmail.com',
	license = 'WTFPL',
	keywords = [
		'fec', 'forward', 'error', 'correction', 'fountain', 'code',
		'rateless', 'erasure', 'codes', 'raptor', 'raptorq', 'libraptorq',
		'lossy', 'reliable', 'encoding', 'rate', 'parity', 'redundancy', 'reliability' ],

	url = 'http://github.com/mk-fg/python-libraptorq',

	description = 'Python CFFI bindings for libRaptorQ'
		' (RaptorQ RFC6330 FEC implementation).',
	long_description = readme,

	classifiers = [
		'Development Status :: 4 - Beta',
		'Environment :: Console',
		'Environment :: No Input/Output (Daemon)',
		'Intended Audience :: Developers',
		'Intended Audience :: End Users/Desktop',
		'Intended Audience :: Information Technology',
		'Intended Audience :: Science/Research',
		'Intended Audience :: Telecommunications Industry',
		'License :: Public Domain',
		'Operating System :: POSIX',
		'Operating System :: POSIX :: Linux',
		'Programming Language :: Python',
		'Programming Language :: Python :: 2.7',
		'Programming Language :: Python :: 2 :: Only',
		'Topic :: Communications',
		'Topic :: Internet',
		'Topic :: System :: Archiving',
		'Topic :: Utilities' ],

	install_requires = ['cffi', 'setuptools'],

	packages = find_packages(),
	include_package_data = True,

	entry_points = {
		'console_scripts': ['rq = libraptorq.__main__:main'] })
