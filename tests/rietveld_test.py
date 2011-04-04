#!/usr/bin/env python
# Copyright (c) 2011 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for rietveld.py."""

import logging
import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT_DIR, '..'))

import patch
import rietveld

# Access to a protected member XX of a client class
# pylint: disable=W0212


class RietveldTest(unittest.TestCase):
  def setUp(self):
    super(RietveldTest, self).setUp()
    self._rietveld_send = rietveld.Rietveld._send
    rietveld.Rietveld._send = None

  def tearDown(self):
    super(RietveldTest, self).setUp()
    rietveld.Rietveld._send = self._rietveld_send

  def test_get_patch_empty(self):
    rietveld.Rietveld._send = lambda x, y, payload: '{}'
    r = rietveld.Rietveld('url', 'email', 'password')
    patches = r.get_patch(123, 456)
    self.assertTrue(isinstance(patches, patch.PatchSet))
    self.assertEquals([], patches.patches)

  def test_get_patch_no_status(self):
    rietveld.Rietveld._send = lambda x, y, payload: (
        '{'
        '  "files":'
        '    {'
        '      "file_a":'
        '        {'
        '        }'
        '    }'
        '}')
    r = rietveld.Rietveld('url', 'email', 'password')
    try:
      r.get_patch(123, 456)
      self.fail()
    except patch.UnsupportedPatchFormat, e:
      self.assertEquals('file_a', e.filename)

  def test_get_patch_two_files(self):
    output = (
        '{'
        '  "files":'
        '    {'
        '      "file_a":'
        '        {'
        '          "status": "A",'
        '          "is_binary": false,'
        '          "num_chunks": 1,'
        '          "id": 789'
        '        }'
        '    }'
        '}')
    rietveld.Rietveld._send = lambda x, y, payload: output
    r = rietveld.Rietveld('url', 'email', 'password')
    patches = r.get_patch(123, 456)
    self.assertTrue(isinstance(patches, patch.PatchSet))
    self.assertEquals(1, len(patches.patches))
    obj = patches.patches[0]
    self.assertEquals(patch.FilePatchDiff, obj.__class__)
    self.assertEquals('file_a', obj.filename)
    self.assertEquals([], obj.svn_properties)
    self.assertEquals(False, obj.is_git_diff)
    self.assertEquals(0, obj.patchlevel)
    # This is because Rietveld._send() always returns the same buffer.
    self.assertEquals(output, obj.get())



if __name__ == '__main__':
  logging.basicConfig(level=logging.ERROR)
  unittest.main()
