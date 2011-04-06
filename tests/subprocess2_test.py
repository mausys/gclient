#!/usr/bin/env python
# Copyright (c) 2011 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for subprocess2.py."""

import optparse
import os
import sys
import time
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

import subprocess2

# Method could be a function
# pylint: disable=R0201

class Subprocess2Test(unittest.TestCase):
  # Can be mocked in a test.
  TO_SAVE = {
      subprocess2: ['Popen', 'call', 'check_call', 'capture', 'check_output'],
      subprocess2.subprocess: ['Popen'],
  }

  def setUp(self):
    self.exe_path = __file__
    self.exe = [self.exe_path, '--child']
    self.saved = {}
    for module, names in self.TO_SAVE.iteritems():
      self.saved[module] = dict(
          (name, getattr(module, name)) for name in names)

  def tearDown(self):
    for module, saved in self.saved.iteritems():
      for name, value in saved.iteritems():
        setattr(module, name, value)

  @staticmethod
  def _fake_call():
    results = {}
    def fake_call(args, **kwargs):
      assert not results
      results.update(kwargs)
      results['args'] = args
      return ['stdout', 'stderr'], 0
    subprocess2.call = fake_call
    return results

  @staticmethod
  def _fake_Popen():
    results = {}
    class fake_Popen(object):
      returncode = -8
      def __init__(self, args, **kwargs):
        assert not results
        results.update(kwargs)
        results['args'] = args
      def communicate(self):
        return None, None
    subprocess2.Popen = fake_Popen
    return results

  @staticmethod
  def _fake_subprocess_Popen():
    results = {}
    class fake_Popen(object):
      returncode = -8
      def __init__(self, args, **kwargs):
        assert not results
        results.update(kwargs)
        results['args'] = args
      def communicate(self):
        return None, None
    subprocess2.subprocess.Popen = fake_Popen
    return results

  def test_check_call_defaults(self):
    results = self._fake_call()
    self.assertEquals(
        ['stdout', 'stderr'], subprocess2.check_call(['foo'], a=True))
    expected = {
        'args': ['foo'],
        'a':True,
    }
    self.assertEquals(expected, results)

  def test_call_defaults(self):
    results = self._fake_Popen()
    self.assertEquals(((None, None), -8), subprocess2.call(['foo'], a=True))
    expected = {
        'args': ['foo'],
        'a': True,
    }
    self.assertEquals(expected, results)

  def test_Popen_defaults(self):
    results = self._fake_subprocess_Popen()
    proc = subprocess2.Popen(['foo'], a=True)
    self.assertEquals(-8, proc.returncode)
    env = os.environ.copy()
    env['LANG'] = 'en_US.UTF-8'
    expected = {
        'args': ['foo'],
        'a': True,
        'shell': bool(sys.platform=='win32'),
        'env': env,
    }
    self.assertEquals(expected, results)

  def test_check_output_defaults(self):
    results = self._fake_call()
    # It's discarding 'stderr' because it assumes stderr=subprocess2.STDOUT but
    # fake_call() doesn't 'implement' that.
    self.assertEquals('stdout', subprocess2.check_output(['foo'], a=True))
    expected = {
        'args': ['foo'],
        'a':True,
        'stdout': subprocess2.PIPE,
        'stderr': subprocess2.STDOUT,
    }
    self.assertEquals(expected, results)

  def test_timeout(self):
    # It'd be better to not discard stdout.
    out, returncode = subprocess2.call(
        self.exe + ['--sleep', '--stdout'],
        timeout=0.01,
        stdout=subprocess2.PIPE)
    self.assertEquals(-9, returncode)
    self.assertEquals(['', None], out)

  def test_void(self):
    out = subprocess2.check_output(
         self.exe + ['--stdout', '--stderr'],
         stdout=subprocess2.VOID)
    self.assertEquals(None, out)
    out = subprocess2.check_output(
         self.exe + ['--stdout', '--stderr'],
         stderr=subprocess2.VOID)
    self.assertEquals('A\nBB\nCCC\n', out)

  def test_check_output_throw(self):
    try:
      subprocess2.check_output(self.exe + ['--fail', '--stderr'])
      self.fail()
    except subprocess2.CalledProcessError, e:
      self.assertEquals('a\nbb\nccc\n', e.stdout)
      self.assertEquals(None, e.stderr)
      self.assertEquals(64, e.returncode)

  def test_check_call_throw(self):
    try:
      subprocess2.check_call(self.exe + ['--fail', '--stderr'])
      self.fail()
    except subprocess2.CalledProcessError, e:
      self.assertEquals(None, e.stdout)
      self.assertEquals(None, e.stderr)
      self.assertEquals(64, e.returncode)


def child_main(args):
  parser = optparse.OptionParser()
  parser.add_option(
      '--fail',
      dest='return_value',
      action='store_const',
      default=0,
      const=64)
  parser.add_option('--stdout', action='store_true')
  parser.add_option('--stderr', action='store_true')
  parser.add_option('--sleep', action='store_true')
  options, args = parser.parse_args(args)
  if args:
    parser.error('Internal error')

  def do(string):
    if options.stdout:
      print >> sys.stdout, string.upper()
    if options.stderr:
      print >> sys.stderr, string.lower()

  do('A')
  do('BB')
  do('CCC')
  if options.sleep:
    time.sleep(10)
  return options.return_value


if __name__ == '__main__':
  if len(sys.argv) > 1 and sys.argv[1] == '--child':
    sys.exit(child_main(sys.argv[2:]))
  unittest.main()
