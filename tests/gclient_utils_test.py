#!/usr/bin/python
# Copyright (c) 2010 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import StringIO

# Fixes include path.
from super_mox import SuperMoxTestBase

import gclient_utils


class GclientUtilBase(SuperMoxTestBase):
  def setUp(self):
    super(GclientUtilBase, self).setUp()
    gclient_utils.sys.stdout.flush = lambda: None
    self.mox.StubOutWithMock(gclient_utils, 'Popen')


class GclientUtilsUnittest(GclientUtilBase):
  """General gclient_utils.py tests."""
  def testMembersChanged(self):
    members = [
        'CheckCall', 'CheckCallError', 'CheckCallAndFilter',
        'CheckCallAndFilterAndHeader', 'Error', 'ExecutionQueue', 'FileRead',
        'FileWrite', 'FindFileUpwards', 'FindGclientRoot',
        'GetGClientRootAndEntries', 'GetNamedNodeText',
        'GetNodeNamedAttributeText', 'PathDifference', 'ParseXML', 'Popen',
        'PrintableObject', 'RemoveDirectory', 'SplitUrlRevision',
        'SyntaxErrorToError', 'WorkItem',
        'errno', 'logging', 'os', 're', 'stat', 'subprocess', 'sys',
        'threading', 'time', 'xml',
    ]
    # If this test fails, you should add the relevant test.
    self.compareMembers(gclient_utils, members)


class CheckCallTestCase(GclientUtilBase):
  def testCheckCallSuccess(self):
    args = ['boo', 'foo', 'bar']
    process = self.mox.CreateMockAnything()
    process.returncode = 0
    gclient_utils.Popen(
        args, cwd=None,
        stderr=None,
        stdout=gclient_utils.subprocess.PIPE).AndReturn(process)
    process.communicate().AndReturn(['bleh', 'foo'])
    self.mox.ReplayAll()
    gclient_utils.CheckCall(args)

  def testCheckCallFailure(self):
    args = ['boo', 'foo', 'bar']
    process = self.mox.CreateMockAnything()
    process.returncode = 42
    gclient_utils.Popen(
        args, cwd=None,
        stderr=None,
        stdout=gclient_utils.subprocess.PIPE).AndReturn(process)
    process.communicate().AndReturn(['bleh', 'foo'])
    self.mox.ReplayAll()
    try:
      gclient_utils.CheckCall(args)
      self.fail()
    except gclient_utils.CheckCallError, e:
      self.assertEqual(e.command, args)
      self.assertEqual(e.cwd, None)
      self.assertEqual(e.retcode, 42)
      self.assertEqual(e.stdout, 'bleh')
      self.assertEqual(e.stderr, 'foo')


class CheckCallAndFilterTestCase(GclientUtilBase):
  class ProcessIdMock(object):
    def __init__(self, test_string):
      self.stdout = StringIO.StringIO(test_string)
    def wait(self):
        pass

  def _inner(self, args, test_string):
    cwd = 'bleh'
    gclient_utils.sys.stdout.write(
        '\n________ running \'boo foo bar\' in \'bleh\'\n')
    for i in test_string:
      gclient_utils.sys.stdout.write(i)
    gclient_utils.Popen(
        args,
        cwd=cwd,
        stdout=gclient_utils.subprocess.PIPE,
        stderr=gclient_utils.subprocess.STDOUT,
        bufsize=0).AndReturn(self.ProcessIdMock(test_string))

    self.mox.ReplayAll()
    compiled_pattern = gclient_utils.re.compile(r'a(.*)b')
    line_list = []
    capture_list = []
    def FilterLines(line):
      line_list.append(line)
      assert isinstance(line, str), type(line)
      match = compiled_pattern.search(line)
      if match:
        capture_list.append(match.group(1))
    gclient_utils.CheckCallAndFilterAndHeader(
        args, cwd=cwd, always=True, filter_fn=FilterLines)
    self.assertEquals(line_list, ['ahah', 'accb', 'allo', 'addb'])
    self.assertEquals(capture_list, ['cc', 'dd'])

  def testCheckCallAndFilter(self):
    args = ['boo', 'foo', 'bar']
    test_string = 'ahah\naccb\nallo\naddb\n'
    self._inner(args, test_string)

  def testNoLF(self):
    # Exactly as testCheckCallAndFilterAndHeader without trailing \n
    args = ['boo', 'foo', 'bar']
    test_string = 'ahah\naccb\nallo\naddb'
    self._inner(args, test_string)


class SplitUrlRevisionTestCase(GclientUtilBase):
  def testSSHUrl(self):
    url = "ssh://test@example.com/test.git"
    rev = "ac345e52dc"
    out_url, out_rev = gclient_utils.SplitUrlRevision(url)
    self.assertEquals(out_rev, None)
    self.assertEquals(out_url, url)
    out_url, out_rev = gclient_utils.SplitUrlRevision("%s@%s" % (url, rev))
    self.assertEquals(out_rev, rev)
    self.assertEquals(out_url, url)
    url = "ssh://example.com/test.git"
    out_url, out_rev = gclient_utils.SplitUrlRevision(url)
    self.assertEquals(out_rev, None)
    self.assertEquals(out_url, url)
    out_url, out_rev = gclient_utils.SplitUrlRevision("%s@%s" % (url, rev))
    self.assertEquals(out_rev, rev)
    self.assertEquals(out_url, url)
    url = "ssh://example.com/git/test.git"
    out_url, out_rev = gclient_utils.SplitUrlRevision(url)
    self.assertEquals(out_rev, None)
    self.assertEquals(out_url, url)
    out_url, out_rev = gclient_utils.SplitUrlRevision("%s@%s" % (url, rev))
    self.assertEquals(out_rev, rev)
    self.assertEquals(out_url, url)
    rev = "test-stable"
    out_url, out_rev = gclient_utils.SplitUrlRevision("%s@%s" % (url, rev))
    self.assertEquals(out_rev, rev)
    self.assertEquals(out_url, url)

  def testSVNUrl(self):
    url = "svn://example.com/test"
    rev = "ac345e52dc"
    out_url, out_rev = gclient_utils.SplitUrlRevision(url)
    self.assertEquals(out_rev, None)
    self.assertEquals(out_url, url)
    out_url, out_rev = gclient_utils.SplitUrlRevision("%s@%s" % (url, rev))
    self.assertEquals(out_rev, rev)
    self.assertEquals(out_url, url)


if __name__ == '__main__':
  import unittest
  unittest.main()

# vim: ts=2:sw=2:tw=80:et:
