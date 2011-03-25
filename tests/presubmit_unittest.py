#!/usr/bin/python
# Copyright (c) 2010 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for presubmit_support.py and presubmit_canned_checks.py."""

# pylint is too confused.
# pylint: disable=E1101,E1103,W0212,W0403

import StringIO

# Fixes include path.
from super_mox import mox, SuperMoxTestBase

import owners
import presubmit_support as presubmit
# Shortcut.
presubmit_canned_checks = presubmit.presubmit_canned_checks


class PresubmitTestsBase(SuperMoxTestBase):
  """Setups and tear downs the mocks but doesn't test anything as-is."""
  presubmit_text = """
def CheckChangeOnUpload(input_api, output_api):
  if not input_api.change.NOSUCHKEY:
    return [output_api.PresubmitError("!!")]
  elif not input_api.change.REALLYNOSUCHKEY:
    return [output_api.PresubmitPromptWarning("??")]
  elif not input_api.change.REALLYABSOLUTELYNOSUCHKEY:
    return [output_api.PresubmitPromptWarning("??"),
            output_api.PresubmitError("XX!!XX")]
  else:
    return ()
"""
  presubmit_tryslave = """
def GetPreferredTrySlaves():
  return %s
"""

  presubmit_diffs = """
--- file1       2011-02-09 10:38:16.517224845 -0800
+++ file2       2011-02-09 10:38:53.177226516 -0800
@@ -1,6 +1,5 @@
 this is line number 0
 this is line number 1
-this is line number 2 to be deleted
 this is line number 3
 this is line number 4
 this is line number 5
@@ -8,7 +7,7 @@
 this is line number 7
 this is line number 8
 this is line number 9
-this is line number 10 to be modified
+this is line number 10
 this is line number 11
 this is line number 12
 this is line number 13
@@ -21,9 +20,8 @@
 this is line number 20
 this is line number 21
 this is line number 22
-this is line number 23
-this is line number 24
-this is line number 25
+this is line number 23.1
+this is line number 25.1
 this is line number 26
 this is line number 27
 this is line number 28
@@ -31,6 +29,7 @@
 this is line number 30
 this is line number 31
 this is line number 32
+this is line number 32.1
 this is line number 33
 this is line number 34
 this is line number 35
@@ -38,14 +37,14 @@
 this is line number 37
 this is line number 38
 this is line number 39
-
 this is line number 40
-this is line number 41
+this is line number 41.1
 this is line number 42
 this is line number 43
 this is line number 44
 this is line number 45
+
 this is line number 46
 this is line number 47
-this is line number 48
+this is line number 48.1
 this is line number 49
"""

  def setUp(self):
    class FakeChange(object):
      root = '/'

      def RepositoryRoot(self):
        return self.root

    SuperMoxTestBase.setUp(self)
    self.fake_change = FakeChange()
    self.mox.StubOutWithMock(presubmit, 'random')
    self.mox.StubOutWithMock(presubmit, 'warn')
    presubmit._ASKED_FOR_FEEDBACK = False
    self.fake_root_dir = self.RootDir()
    # Special mocks.
    def MockAbsPath(f):
      return f
    def MockChdir(f):
      return None
    # SuperMoxTestBase already mock these but simplify our life.
    presubmit.os.path.abspath = MockAbsPath
    presubmit.os.getcwd = self.RootDir
    presubmit.os.chdir = MockChdir
    self.mox.StubOutWithMock(presubmit.scm, 'determine_scm')
    self.mox.StubOutWithMock(presubmit.scm.SVN, 'CaptureInfo')
    self.mox.StubOutWithMock(presubmit.scm.SVN, 'GetFileProperty')
    self.mox.StubOutWithMock(presubmit.gclient_utils, 'FileRead')
    self.mox.StubOutWithMock(presubmit.gclient_utils, 'FileWrite')
    self.mox.StubOutWithMock(presubmit.scm.SVN, 'GenerateDiff')


class PresubmitUnittest(PresubmitTestsBase):
  """General presubmit_support.py tests (excluding InputApi and OutputApi)."""

  _INHERIT_SETTINGS = 'inherit-review-settings-ok'

  def testMembersChanged(self):
    self.mox.ReplayAll()
    members = [
      'AffectedFile', 'Change', 'DoGetTrySlaves', 'DoPresubmitChecks',
      'GetTrySlavesExecuter', 'GitAffectedFile',
      'GitChange', 'InputApi', 'ListRelevantPresubmitFiles', 'Main',
      'NotImplementedException', 'OutputApi', 'ParseFiles',
      'PresubmitExecuter', 'PresubmitOutput', 'ScanSubDirs',
      'SvnAffectedFile', 'SvnChange', 'cPickle', 'cStringIO',
      'exceptions', 'fix_encoding', 'fnmatch', 'gclient_utils', 'glob', 'json',
      'load_files',
      'logging', 'marshal', 'normpath', 'optparse', 'os', 'owners', 'pickle',
      'presubmit_canned_checks', 'random', 're', 'scm', 'subprocess',
      'sys', 'tempfile', 'time', 'traceback', 'types', 'unittest', 'urllib2',
      'warn',
    ]
    # If this test fails, you should add the relevant test.
    self.compareMembers(presubmit, members)

  def testListRelevantPresubmitFiles(self):
    join = presubmit.os.path.join
    files = [
      'blat.cc',
      join('foo', 'haspresubmit', 'yodle', 'smart.h'),
      join('moo', 'mat', 'gat', 'yo.h'),
      join('foo', 'luck.h'),
    ]
    inherit_path = presubmit.os.path.join(self.fake_root_dir,
                                          self._INHERIT_SETTINGS)
    presubmit.os.path.isfile(inherit_path).AndReturn(False)
    presubmit.os.path.isfile(join(self.fake_root_dir,
                                  'PRESUBMIT.py')).AndReturn(True)
    presubmit.os.path.isfile(join(self.fake_root_dir, 'foo',
                                  'PRESUBMIT.py')).AndReturn(False)
    presubmit.os.path.isfile(join(self.fake_root_dir, 'foo', 'haspresubmit',
                                  'PRESUBMIT.py')).AndReturn(True)
    presubmit.os.path.isfile(join(self.fake_root_dir, 'foo', 'haspresubmit',
                                  'yodle', 'PRESUBMIT.py')).AndReturn(True)
    presubmit.os.path.isfile(join(self.fake_root_dir, 'moo',
                                  'PRESUBMIT.py')).AndReturn(False)
    presubmit.os.path.isfile(join(self.fake_root_dir, 'moo', 'mat',
                                  'PRESUBMIT.py')).AndReturn(False)
    presubmit.os.path.isfile(join(self.fake_root_dir, 'moo', 'mat', 'gat',
                                  'PRESUBMIT.py')).AndReturn(False)
    self.mox.ReplayAll()

    presubmit_files = presubmit.ListRelevantPresubmitFiles(files,
                                                           self.fake_root_dir)
    self.assertEqual(presubmit_files,
        [
          join(self.fake_root_dir, 'PRESUBMIT.py'),
          join(self.fake_root_dir, 'foo', 'haspresubmit', 'PRESUBMIT.py'),
          join(self.fake_root_dir, 'foo', 'haspresubmit', 'yodle',
               'PRESUBMIT.py')
        ])

  def testListRelevantPresubmitFilesInheritSettings(self):
    join = presubmit.os.path.join
    sys_root_dir = self._OS_SEP
    root_dir = join(sys_root_dir, 'foo', 'bar')
    files = [
      'test.cc',
      join('moo', 'test2.cc'),
      join('zoo', 'test3.cc')
    ]
    inherit_path = presubmit.os.path.join(root_dir, self._INHERIT_SETTINGS)
    presubmit.os.path.isfile(inherit_path).AndReturn(True)
    presubmit.os.path.isfile(join(sys_root_dir,
                                  'PRESUBMIT.py')).AndReturn(False)
    presubmit.os.path.isfile(join(sys_root_dir, 'foo',
                                  'PRESUBMIT.py')).AndReturn(True)
    presubmit.os.path.isfile(join(sys_root_dir, 'foo', 'bar',
                                  'PRESUBMIT.py')).AndReturn(False)
    presubmit.os.path.isfile(join(sys_root_dir, 'foo', 'bar', 'moo',
                                  'PRESUBMIT.py')).AndReturn(True)
    presubmit.os.path.isfile(join(sys_root_dir, 'foo', 'bar', 'zoo',
                                  'PRESUBMIT.py')).AndReturn(False)
    self.mox.ReplayAll()

    presubmit_files = presubmit.ListRelevantPresubmitFiles(files, root_dir)
    self.assertEqual(presubmit_files,
        [
          join(sys_root_dir, 'foo', 'PRESUBMIT.py'),
          join(sys_root_dir, 'foo', 'bar', 'moo', 'PRESUBMIT.py')
        ])

  def testTagLineRe(self):
    self.mox.ReplayAll()
    m = presubmit.Change._TAG_LINE_RE.match(' BUG =1223, 1445  \t')
    self.failUnless(m)
    self.failUnlessEqual(m.group('key'), 'BUG')
    self.failUnlessEqual(m.group('value'), '1223, 1445')

  def testGclChange(self):
    description_lines = ('Hello there',
                         'this is a change',
                         'BUG=123',
                         ' STORY =http://foo/  \t',
                         'and some more regular text  \t')
    files = [
      ['A', 'foo/blat.cc'],
      ['M', 'binary.dll'],  # a binary file
      ['A', 'isdir'],  # a directory
      ['?', 'flop/notfound.txt'],  # not found in SVN, still exists locally
      ['D', 'boo/flap.h'],
    ]
    blat = presubmit.os.path.join(self.fake_root_dir, 'foo', 'blat.cc')
    notfound = presubmit.os.path.join(
        self.fake_root_dir, 'flop', 'notfound.txt')
    flap = presubmit.os.path.join(self.fake_root_dir, 'boo', 'flap.h')
    binary = presubmit.os.path.join(self.fake_root_dir, 'binary.dll')
    isdir = presubmit.os.path.join(self.fake_root_dir, 'isdir')
    presubmit.os.path.exists(blat).AndReturn(True)
    presubmit.os.path.isdir(blat).AndReturn(False)
    presubmit.os.path.exists(binary).AndReturn(True)
    presubmit.os.path.isdir(binary).AndReturn(False)
    presubmit.os.path.exists(isdir).AndReturn(True)
    presubmit.os.path.isdir(isdir).AndReturn(True)
    presubmit.os.path.exists(notfound).AndReturn(True)
    presubmit.os.path.isdir(notfound).AndReturn(False)
    presubmit.os.path.exists(flap).AndReturn(False)
    presubmit.scm.SVN.CaptureInfo(flap
        ).AndReturn({'Node Kind': 'file'})
    presubmit.scm.SVN.GetFileProperty(blat, 'svn:mime-type').AndReturn(None)
    presubmit.scm.SVN.GetFileProperty(
        binary, 'svn:mime-type').AndReturn('application/octet-stream')
    presubmit.scm.SVN.GetFileProperty(
        notfound, 'svn:mime-type').AndReturn('')
    presubmit.scm.SVN.CaptureInfo(blat).AndReturn(
            {'URL': 'svn:/foo/foo/blat.cc'})
    presubmit.scm.SVN.CaptureInfo(binary).AndReturn(
        {'URL': 'svn:/foo/binary.dll'})
    presubmit.scm.SVN.CaptureInfo(notfound).AndReturn({})
    presubmit.scm.SVN.CaptureInfo(flap).AndReturn(
            {'URL': 'svn:/foo/boo/flap.h'})
    presubmit.scm.SVN.GenerateDiff([blat]).AndReturn(self.presubmit_diffs)
    presubmit.scm.SVN.GenerateDiff([notfound]).AndReturn(self.presubmit_diffs)

    self.mox.ReplayAll()

    change = presubmit.SvnChange('mychange', '\n'.join(description_lines),
                                 self.fake_root_dir, files, 0, 0)
    self.failUnless(change.Name() == 'mychange')
    self.failUnless(change.DescriptionText() ==
                    'Hello there\nthis is a change\nand some more regular text')
    self.failUnless(change.FullDescriptionText() ==
                    '\n'.join(description_lines))

    self.failUnless(change.BUG == '123')
    self.failUnless(change.STORY == 'http://foo/')
    self.failUnless(change.BLEH == None)

    self.failUnless(len(change.AffectedFiles()) == 4)
    self.failUnless(len(change.AffectedFiles(include_dirs=True)) == 5)
    self.failUnless(len(change.AffectedFiles(include_deletes=False)) == 3)
    self.failUnless(len(change.AffectedFiles(include_dirs=True,
                                             include_deletes=False)) == 4)

    affected_text_files = change.AffectedTextFiles()
    self.failUnless(len(affected_text_files) == 2)
    self.failIf(filter(lambda x: x.LocalPath() == 'binary.dll',
                       affected_text_files))

    local_paths = change.LocalPaths()
    expected_paths = [presubmit.normpath(f[1]) for f in files]
    self.failUnless(
        len(filter(lambda x: x in expected_paths, local_paths)) == 4)

    server_paths = change.ServerPaths()
    expected_paths = ['svn:/foo/%s' % f[1] for f in files if
                      f[1] != 'flop/notfound.txt']
    expected_paths.append('')  # one unknown file
    self.assertEqual(
      len(filter(lambda x: x in expected_paths, server_paths)), 4)

    files = [[x[0], presubmit.normpath(x[1])] for x in files]

    rhs_lines = []
    for line in change.RightHandSideLines():
      rhs_lines.append(line)
    self.assertEquals(rhs_lines[0][0].LocalPath(), files[0][1])
    self.assertEquals(rhs_lines[0][1], 10)
    self.assertEquals(rhs_lines[0][2],'this is line number 10')

    self.assertEquals(rhs_lines[3][0].LocalPath(), files[0][1])
    self.assertEquals(rhs_lines[3][1], 32)
    self.assertEquals(rhs_lines[3][2], 'this is line number 32.1')

    self.assertEquals(rhs_lines[8][0].LocalPath(), files[3][1])
    self.assertEquals(rhs_lines[8][1], 23)
    self.assertEquals(rhs_lines[8][2], 'this is line number 23.1')

    self.assertEquals(rhs_lines[12][0].LocalPath(), files[3][1])
    self.assertEquals(rhs_lines[12][1], 46)
    self.assertEquals(rhs_lines[12][2], '')

    self.assertEquals(rhs_lines[13][0].LocalPath(), files[3][1])
    self.assertEquals(rhs_lines[13][1], 49)
    self.assertEquals(rhs_lines[13][2], 'this is line number 48.1')

  def testExecPresubmitScript(self):
    description_lines = ('Hello there',
                         'this is a change',
                         'STORY=http://tracker/123')
    files = [
      ['A', 'foo\\blat.cc'],
    ]
    fake_presubmit = presubmit.os.path.join(self.fake_root_dir, 'PRESUBMIT.py')
    self.mox.ReplayAll()

    change = presubmit.Change('mychange', '\n'.join(description_lines),
                              self.fake_root_dir, files, 0, 0)
    executer = presubmit.PresubmitExecuter(change, False, False, None)
    self.failIf(executer.ExecPresubmitScript('', fake_presubmit))
    # No error if no on-upload entry point
    self.failIf(executer.ExecPresubmitScript(
      ('def CheckChangeOnCommit(input_api, output_api):\n'
       '  return (output_api.PresubmitError("!!"))\n'),
      fake_presubmit
    ))

    executer = presubmit.PresubmitExecuter(change, True, False, None)
    # No error if no on-commit entry point
    self.failIf(executer.ExecPresubmitScript(
      ('def CheckChangeOnUpload(input_api, output_api):\n'
       '  return (output_api.PresubmitError("!!"))\n'),
      fake_presubmit
    ))

    self.failIf(executer.ExecPresubmitScript(
      ('def CheckChangeOnUpload(input_api, output_api):\n'
       '  if not input_api.change.STORY:\n'
       '    return (output_api.PresubmitError("!!"))\n'
       '  else:\n'
       '    return ()'),
      fake_presubmit
    ))

    self.failUnless(executer.ExecPresubmitScript(
      ('def CheckChangeOnCommit(input_api, output_api):\n'
       '  if not input_api.change.NOSUCHKEY:\n'
       '    return [output_api.PresubmitError("!!")]\n'
       '  else:\n'
       '    return ()'),
      fake_presubmit
    ))

    self.assertRaises(presubmit.exceptions.RuntimeError,
      executer.ExecPresubmitScript,
      'def CheckChangeOnCommit(input_api, output_api):\n'
      '  return "foo"',
      fake_presubmit)

    self.assertRaises(presubmit.exceptions.RuntimeError,
      executer.ExecPresubmitScript,
      'def CheckChangeOnCommit(input_api, output_api):\n'
      '  return ["foo"]',
      fake_presubmit)

  def testDoPresubmitChecks(self):
    join = presubmit.os.path.join
    description_lines = ('Hello there',
                         'this is a change',
                         'STORY=http://tracker/123')
    files = [
      ['A', join('haspresubmit', 'blat.cc')],
    ]
    haspresubmit_path = join(self.fake_root_dir, 'haspresubmit', 'PRESUBMIT.py')
    root_path = join(self.fake_root_dir, 'PRESUBMIT.py')
    inherit_path = presubmit.os.path.join(self.fake_root_dir,
                                          self._INHERIT_SETTINGS)
    presubmit.os.path.isfile(inherit_path).AndReturn(False)
    presubmit.os.path.isfile(root_path).AndReturn(True)
    presubmit.os.path.isfile(haspresubmit_path).AndReturn(True)
    presubmit.gclient_utils.FileRead(root_path,
                                     'rU').AndReturn(self.presubmit_text)
    presubmit.gclient_utils.FileRead(haspresubmit_path,
                                     'rU').AndReturn(self.presubmit_text)
    presubmit.random.randint(0, 4).AndReturn(1)
    self.mox.ReplayAll()

    input_buf = StringIO.StringIO('y\n')
    change = presubmit.Change('mychange', '\n'.join(description_lines),
                              self.fake_root_dir, files, 0, 0)
    output = presubmit.DoPresubmitChecks(
        change, False, True, None, input_buf, None, False)
    self.failIf(output.should_continue())
    self.assertEqual(output.getvalue().count('!!'), 2)
    self.assertEqual(output.getvalue().count(
        'Running presubmit upload checks ...\n'), 1)

  def testDoPresubmitChecksPromptsAfterWarnings(self):
    join = presubmit.os.path.join
    description_lines = ('Hello there',
                         'this is a change',
                         'NOSUCHKEY=http://tracker/123')
    files = [
      ['A', join('haspresubmit', 'blat.cc')],
    ]
    presubmit_path = join(self.fake_root_dir, 'PRESUBMIT.py')
    haspresubmit_path = join(self.fake_root_dir, 'haspresubmit', 'PRESUBMIT.py')
    inherit_path = presubmit.os.path.join(self.fake_root_dir,
                                          self._INHERIT_SETTINGS)
    for _ in range(2):
      presubmit.os.path.isfile(inherit_path).AndReturn(False)
      presubmit.os.path.isfile(presubmit_path).AndReturn(True)
      presubmit.os.path.isfile(haspresubmit_path).AndReturn(True)
      presubmit.gclient_utils.FileRead(presubmit_path, 'rU'
          ).AndReturn(self.presubmit_text)
      presubmit.gclient_utils.FileRead(haspresubmit_path, 'rU'
          ).AndReturn(self.presubmit_text)
    presubmit.random.randint(0, 4).AndReturn(1)
    presubmit.random.randint(0, 4).AndReturn(1)
    self.mox.ReplayAll()

    input_buf = StringIO.StringIO('n\n')  # say no to the warning
    change = presubmit.Change('mychange', '\n'.join(description_lines),
                              self.fake_root_dir, files, 0, 0)
    output = presubmit.DoPresubmitChecks(
        change, False, True, None, input_buf, None, True)
    self.failIf(output.should_continue())
    self.assertEqual(output.getvalue().count('??'), 2)

    input_buf = StringIO.StringIO('y\n')  # say yes to the warning
    output = presubmit.DoPresubmitChecks(
        change, False, True, None, input_buf, None, True)
    self.failUnless(output.should_continue())
    self.assertEquals(output.getvalue().count('??'), 2)
    self.assertEqual(output.getvalue().count(
        'Running presubmit upload checks ...\n'), 1)

  def testDoPresubmitChecksNoWarningPromptIfErrors(self):
    join = presubmit.os.path.join
    description_lines = ('Hello there',
                         'this is a change',
                         'NOSUCHKEY=http://tracker/123',
                         'REALLYNOSUCHKEY=http://tracker/123')
    files = [
      ['A', join('haspresubmit', 'blat.cc')],
    ]
    presubmit_path = join(self.fake_root_dir, 'PRESUBMIT.py')
    haspresubmit_path = join(self.fake_root_dir, 'haspresubmit',
                             'PRESUBMIT.py')
    inherit_path = presubmit.os.path.join(self.fake_root_dir,
                                          self._INHERIT_SETTINGS)
    presubmit.os.path.isfile(inherit_path).AndReturn(False)
    presubmit.os.path.isfile(presubmit_path).AndReturn(True)
    presubmit.os.path.isfile(haspresubmit_path).AndReturn(True)
    presubmit.gclient_utils.FileRead(presubmit_path, 'rU'
                                     ).AndReturn(self.presubmit_text)
    presubmit.gclient_utils.FileRead(haspresubmit_path, 'rU').AndReturn(
        self.presubmit_text)
    presubmit.random.randint(0, 4).AndReturn(1)
    self.mox.ReplayAll()

    change = presubmit.Change('mychange', '\n'.join(description_lines),
                              self.fake_root_dir, files, 0, 0)
    output = presubmit.DoPresubmitChecks(change, False, True, None, None,
        None, False)
    self.assertEqual(output.getvalue().count('??'), 2)
    self.assertEqual(output.getvalue().count('XX!!XX'), 2)
    self.assertEqual(output.getvalue().count('(y/N)'), 0)
    self.assertEqual(output.getvalue().count(
        'Running presubmit upload checks ...\n'), 1)

  def testDoDefaultPresubmitChecksAndFeedback(self):
    join = presubmit.os.path.join
    description_lines = ('Hello there',
                         'this is a change',
                         'STORY=http://tracker/123')
    files = [
      ['A', join('haspresubmit', 'blat.cc')],
    ]
    DEFAULT_SCRIPT = """
def CheckChangeOnUpload(input_api, output_api):
  return [output_api.PresubmitError("!!")]
def CheckChangeOnCommit(input_api, output_api):
  raise Exception("Test error")
"""
    inherit_path = presubmit.os.path.join(self.fake_root_dir,
                                          self._INHERIT_SETTINGS)
    presubmit.os.path.isfile(inherit_path).AndReturn(False)
    presubmit.os.path.isfile(join(self.fake_root_dir, 'PRESUBMIT.py')
        ).AndReturn(False)
    presubmit.os.path.isfile(join(self.fake_root_dir,
                                  'haspresubmit',
                                  'PRESUBMIT.py')).AndReturn(False)
    presubmit.random.randint(0, 4).AndReturn(0)
    self.mox.ReplayAll()

    input_buf = StringIO.StringIO('y\n')
    # Always fail.
    change = presubmit.Change('mychange', '\n'.join(description_lines),
                              self.fake_root_dir, files, 0, 0)
    output = presubmit.DoPresubmitChecks(
        change, False, True, None, input_buf, DEFAULT_SCRIPT, False)
    self.failIf(output.should_continue())
    text = ('Running presubmit upload checks ...\n'
            'Warning, no presubmit.py found.\n'
            'Running default presubmit script.\n'
            '\n'
            '** Presubmit ERRORS **\n!!\n\n'
            'Was the presubmit check useful? Please send feedback & hate mail '
            'to maruel@chromium.org!\n')
    self.assertEquals(output.getvalue(), text)

  def testDirectoryHandling(self):
    files = [
      ['A', 'isdir'],
      ['A', presubmit.os.path.join('isdir', 'blat.cc')],
    ]
    isdir = presubmit.os.path.join(self.fake_root_dir, 'isdir')
    blat = presubmit.os.path.join(isdir, 'blat.cc')
    presubmit.os.path.exists(isdir).AndReturn(True)
    presubmit.os.path.isdir(isdir).AndReturn(True)
    presubmit.os.path.exists(blat).AndReturn(True)
    presubmit.os.path.isdir(blat).AndReturn(False)
    self.mox.ReplayAll()

    change = presubmit.Change('mychange', 'foo', self.fake_root_dir, files,
                              0, 0)
    affected_files = change.AffectedFiles(include_dirs=False)
    self.failUnless(len(affected_files) == 1)
    self.failUnless(affected_files[0].LocalPath().endswith('blat.cc'))
    affected_files_and_dirs = change.AffectedFiles(include_dirs=True)
    self.failUnless(len(affected_files_and_dirs) == 2)

  def testTags(self):
    DEFAULT_SCRIPT = """
def CheckChangeOnUpload(input_api, output_api):
  if input_api.change.tags['BUG'] != 'boo':
    return [output_api.PresubmitError('Tag parsing failed. 1')]
  if input_api.change.tags['STORY'] != 'http://tracker.com/42':
    return [output_api.PresubmitError('Tag parsing failed. 2')]
  if input_api.change.BUG != 'boo':
    return [output_api.PresubmitError('Tag parsing failed. 6')]
  if input_api.change.STORY != 'http://tracker.com/42':
    return [output_api.PresubmitError('Tag parsing failed. 7')]
  try:
    y = False
    x = input_api.change.invalid
  except AttributeError:
    y = True
  if not y:
    return [output_api.PresubmitError('Tag parsing failed. 8')]
  if 'TEST' in input_api.change.tags:
    return [output_api.PresubmitError('Tag parsing failed. 3')]
  if input_api.change.DescriptionText() != 'Blah Blah':
    return [output_api.PresubmitError('Tag parsing failed. 4 ' +
                                      input_api.change.DescriptionText())]
  if (input_api.change.FullDescriptionText() !=
      'Blah Blah\\n\\nSTORY=http://tracker.com/42\\nBUG=boo\\n'):
    return [output_api.PresubmitError('Tag parsing failed. 5 ' +
                                      input_api.change.FullDescriptionText())]
  return [output_api.PresubmitNotifyResult(input_api.change.tags['STORY'])]
def CheckChangeOnCommit(input_api, output_api):
  raise Exception("Test error")
"""
    presubmit.random.randint(0, 4).AndReturn(1)
    inherit_path = presubmit.os.path.join(self.fake_root_dir,
                                          self._INHERIT_SETTINGS)
    presubmit.os.path.isfile(inherit_path).AndReturn(False)
    self.mox.ReplayAll()

    output = StringIO.StringIO()
    input_buf = StringIO.StringIO('y\n')
    change = presubmit.Change(
        'foo', "Blah Blah\n\nSTORY=http://tracker.com/42\nBUG=boo\n",
        self.fake_root_dir, None, 0, 0)
    self.failUnless(presubmit.DoPresubmitChecks(
        change, False, True, output, input_buf, DEFAULT_SCRIPT, False))
    self.assertEquals(output.getvalue(),
                      ('Running presubmit upload checks ...\n'
                       'Warning, no presubmit.py found.\n'
                       'Running default presubmit script.\n'
                       '\n'
                       '** Presubmit Messages **\n'
                       'http://tracker.com/42\n'
                       '\n'
                       'Presubmit checks passed.\n'))

  def testGetTrySlavesExecuter(self):
    self.mox.ReplayAll()

    executer = presubmit.GetTrySlavesExecuter()
    self.assertEqual([], executer.ExecPresubmitScript(''))
    self.assertEqual([], executer.ExecPresubmitScript('def foo():\n  return\n'))

    # bad results
    starts_with_space_result = ['  starts_with_space']
    not_list_result1 = "'foo'"
    not_list_result2 = "('a', 'tuple')"
    for result in starts_with_space_result, not_list_result1, not_list_result2:
      self.assertRaises(presubmit.exceptions.RuntimeError,
                        executer.ExecPresubmitScript,
                        self.presubmit_tryslave % result)

    # good results
    expected_result = ['1', '2', '3']
    empty_result = []
    space_in_name_result = ['foo bar', '1\t2 3']
    for result in expected_result, empty_result, space_in_name_result:
      self.assertEqual(result,
                       executer.ExecPresubmitScript(self.presubmit_tryslave %
                                                    str(result)))

  def testDoGetTrySlaves(self):
    join = presubmit.os.path.join
    filename = 'foo.cc'
    filename_linux = join('linux_only', 'penguin.cc')
    root_presubmit = join(self.fake_root_dir, 'PRESUBMIT.py')
    linux_presubmit = join(self.fake_root_dir, 'linux_only', 'PRESUBMIT.py')
    inherit_path = presubmit.os.path.join(self.fake_root_dir,
                                          self._INHERIT_SETTINGS)

    presubmit.os.path.isfile(inherit_path).AndReturn(False)
    presubmit.os.path.isfile(root_presubmit).AndReturn(True)
    presubmit.gclient_utils.FileRead(root_presubmit, 'rU').AndReturn(
        self.presubmit_tryslave % '["win"]')

    presubmit.os.path.isfile(inherit_path).AndReturn(False)
    presubmit.os.path.isfile(root_presubmit).AndReturn(True)
    presubmit.os.path.isfile(linux_presubmit).AndReturn(True)
    presubmit.gclient_utils.FileRead(root_presubmit, 'rU').AndReturn(
        self.presubmit_tryslave % '["win"]')
    presubmit.gclient_utils.FileRead(linux_presubmit, 'rU').AndReturn(
        self.presubmit_tryslave % '["linux"]')
    self.mox.ReplayAll()

    output = StringIO.StringIO()
    self.assertEqual(['win'],
                     presubmit.DoGetTrySlaves([filename], self.fake_root_dir,
                                              None, False, output))
    output = StringIO.StringIO()
    self.assertEqual(['win', 'linux'],
                     presubmit.DoGetTrySlaves([filename, filename_linux],
                                              self.fake_root_dir, None, False,
                                              output))

  def testMainUnversioned(self):
    # OptParser calls presubmit.os.path.exists and is a pain when mocked.
    self.UnMock(presubmit.os.path, 'exists')
    self.mox.StubOutWithMock(presubmit, 'DoPresubmitChecks')
    self.mox.StubOutWithMock(presubmit, 'ParseFiles')
    presubmit.scm.determine_scm(self.fake_root_dir).AndReturn(None)
    presubmit.ParseFiles(['random_file.txt'], None
        ).AndReturn(['random_file.txt'])
    output = self.mox.CreateMock(presubmit.PresubmitOutput)
    output.should_continue().AndReturn(False)

    presubmit.DoPresubmitChecks(mox.IgnoreArg(), False, False,
                                mox.IgnoreArg(),
                                mox.IgnoreArg(),
                                None, False).AndReturn(output)
    self.mox.ReplayAll()

    self.assertEquals(
        True,
        presubmit.Main(['--root', self.fake_root_dir, 'random_file.txt']))

  def testMainUnversionedFail(self):
    # OptParser calls presubmit.os.path.exists and is a pain when mocked.
    self.UnMock(presubmit.os.path, 'exists')
    self.mox.StubOutWithMock(presubmit, 'DoPresubmitChecks')
    self.mox.StubOutWithMock(presubmit, 'ParseFiles')
    presubmit.scm.determine_scm(self.fake_root_dir).AndReturn(None)
    self.mox.StubOutWithMock(presubmit.sys, 'stderr')
    presubmit.sys.stderr.write(
        'Usage: presubmit_unittest.py [options] <files...>\n')
    presubmit.sys.stderr.write('\n')
    presubmit.sys.stderr.write(
        'presubmit_unittest.py: error: For unversioned directory, <files> is '
        'not optional.\n')
    self.mox.ReplayAll()

    try:
      presubmit.Main(['--root', self.fake_root_dir])
      self.fail()
    except SystemExit, e:
      self.assertEquals(2, e.code)


class InputApiUnittest(PresubmitTestsBase):
  """Tests presubmit.InputApi."""
  def testMembersChanged(self):
    self.mox.ReplayAll()
    members = [
      'AbsoluteLocalPaths', 'AffectedFiles', 'AffectedSourceFiles',
      'AffectedTextFiles',
      'DEFAULT_BLACK_LIST', 'DEFAULT_WHITE_LIST',
      'DepotToLocalPath', 'FilterSourceFile', 'LocalPaths',
      'LocalToDepotPath',
      'PresubmitLocalPath', 'ReadFile', 'RightHandSideLines', 'ServerPaths',
      'basename', 'cPickle', 'cStringIO', 'canned_checks', 'change', 'environ',
      'host_url', 'is_committing', 'json', 'marshal', 'os_path',
      'owners_db', 'pickle', 'platform', 'python_executable', 're',
      'subprocess', 'tbr', 'tempfile', 'time', 'traceback', 'unittest',
      'urllib2', 'version',
    ]
    # If this test fails, you should add the relevant test.
    self.compareMembers(presubmit.InputApi(self.fake_change, './.', False,
                                           False, None),
                        members)

  def testDepotToLocalPath(self):
    presubmit.scm.SVN.CaptureInfo('svn://foo/smurf').AndReturn(
        {'Path': 'prout'})
    presubmit.scm.SVN.CaptureInfo('svn:/foo/notfound/burp').AndReturn({})
    self.mox.ReplayAll()

    path = presubmit.InputApi(self.fake_change, './p', False, False,
        None).DepotToLocalPath('svn://foo/smurf')
    self.failUnless(path == 'prout')
    path = presubmit.InputApi(self.fake_change, './p', False, False,
        None).DepotToLocalPath('svn:/foo/notfound/burp')
    self.failUnless(path == None)

  def testLocalToDepotPath(self):
    presubmit.scm.SVN.CaptureInfo('smurf').AndReturn({'URL': 'svn://foo'})
    presubmit.scm.SVN.CaptureInfo('notfound-food').AndReturn({})
    self.mox.ReplayAll()
    path = presubmit.InputApi(self.fake_change, './p', False, False,
        None).LocalToDepotPath('smurf')
    self.assertEqual(path, 'svn://foo')
    path = presubmit.InputApi(self.fake_change, './p', False, False,
        None).LocalToDepotPath('notfound-food')
    self.failUnless(path == None)

  def testInputApiConstruction(self):
    self.mox.ReplayAll()
    api = presubmit.InputApi(self.fake_change,
                             presubmit_path='foo/path/PRESUBMIT.py',
                             is_committing=False, tbr=False, host_url=None)
    self.assertEquals(api.PresubmitLocalPath(), 'foo/path')
    self.assertEquals(api.change, self.fake_change)
    self.assertEquals(api.host_url, 'http://codereview.chromium.org')

  def testInputApiPresubmitScriptFiltering(self):
    join = presubmit.os.path.join
    description_lines = ('Hello there',
                         'this is a change',
                         'BUG=123',
                         ' STORY =http://foo/  \t',
                         'and some more regular text')
    files = [
      ['A', join('foo', 'blat.cc')],
      ['M', join('foo', 'blat', 'READ_ME2')],
      ['M', join('foo', 'blat', 'binary.dll')],
      ['M', join('foo', 'blat', 'weird.xyz')],
      ['M', join('foo', 'blat', 'another.h')],
      ['M', join('foo', 'third_party', 'third.cc')],
      ['D', 'foo/mat/beingdeleted.txt'],
      ['M', 'flop/notfound.txt'],
      ['A', 'boo/flap.h'],
    ]
    blat = presubmit.normpath(join(self.fake_root_dir, files[0][1]))
    readme = presubmit.normpath(join(self.fake_root_dir, files[1][1]))
    binary = presubmit.normpath(join(self.fake_root_dir, files[2][1]))
    weird = presubmit.normpath(join(self.fake_root_dir, files[3][1]))
    another = presubmit.normpath(join(self.fake_root_dir, files[4][1]))
    third_party = presubmit.normpath(join(self.fake_root_dir, files[5][1]))
    beingdeleted = presubmit.normpath(join(self.fake_root_dir, files[6][1]))
    notfound = presubmit.normpath(join(self.fake_root_dir, files[7][1]))
    flap = presubmit.normpath(join(self.fake_root_dir, files[8][1]))
    for i in (blat, readme, binary, weird, another, third_party):
      presubmit.os.path.exists(i).AndReturn(True)
      presubmit.os.path.isdir(i).AndReturn(False)
    presubmit.os.path.exists(beingdeleted).AndReturn(False)
    presubmit.os.path.exists(notfound).AndReturn(False)
    presubmit.os.path.exists(flap).AndReturn(True)
    presubmit.os.path.isdir(flap).AndReturn(False)
    presubmit.scm.SVN.CaptureInfo(beingdeleted).AndReturn({})
    presubmit.scm.SVN.CaptureInfo(notfound).AndReturn({})
    presubmit.scm.SVN.GetFileProperty(blat, 'svn:mime-type').AndReturn(None)
    presubmit.scm.SVN.GetFileProperty(readme, 'svn:mime-type').AndReturn(None)
    presubmit.scm.SVN.GetFileProperty(binary, 'svn:mime-type').AndReturn(
        'application/octet-stream')
    presubmit.scm.SVN.GetFileProperty(weird, 'svn:mime-type').AndReturn(None)
    presubmit.scm.SVN.GetFileProperty(another, 'svn:mime-type').AndReturn(None)
    presubmit.scm.SVN.GetFileProperty(third_party, 'svn:mime-type'
        ).AndReturn(None)
    presubmit.scm.SVN.GenerateDiff([blat]).AndReturn(self.presubmit_diffs)
    presubmit.scm.SVN.GenerateDiff([another]).AndReturn(self.presubmit_diffs)

    self.mox.ReplayAll()

    change = presubmit.SvnChange('mychange', '\n'.join(description_lines),
                                 self.fake_root_dir, files, 0, 0)
    input_api = presubmit.InputApi(change,
                                   join(self.fake_root_dir, 'foo',
                                        'PRESUBMIT.py'),
                                   False, False, None)
    # Doesn't filter much
    got_files = input_api.AffectedFiles()
    self.assertEquals(len(got_files), 7)
    self.assertEquals(got_files[0].LocalPath(), presubmit.normpath(files[0][1]))
    self.assertEquals(got_files[1].LocalPath(), presubmit.normpath(files[1][1]))
    self.assertEquals(got_files[2].LocalPath(), presubmit.normpath(files[2][1]))
    self.assertEquals(got_files[3].LocalPath(), presubmit.normpath(files[3][1]))
    self.assertEquals(got_files[4].LocalPath(), presubmit.normpath(files[4][1]))
    self.assertEquals(got_files[5].LocalPath(), presubmit.normpath(files[5][1]))
    self.assertEquals(got_files[6].LocalPath(), presubmit.normpath(files[6][1]))
    # Ignores weird because of whitelist, third_party because of blacklist,
    # binary isn't a text file and beingdeleted doesn't exist. The rest is
    # outside foo/.
    rhs_lines = [x for x in input_api.RightHandSideLines(None)]
    self.assertEquals(len(rhs_lines), 14)
    self.assertEqual(rhs_lines[0][0].LocalPath(),
                     presubmit.normpath(files[0][1]))
    self.assertEqual(rhs_lines[3][0].LocalPath(),
                     presubmit.normpath(files[0][1]))
    self.assertEqual(rhs_lines[7][0].LocalPath(),
                     presubmit.normpath(files[4][1]))
    self.assertEqual(rhs_lines[13][0].LocalPath(),
                     presubmit.normpath(files[4][1]))

  def testDefaultWhiteListBlackListFilters(self):
    def f(x):
      return presubmit.AffectedFile(x, 'M')
    files = [
      (
        [
          # To be tested.
          f('a/experimental/b'),
          f('experimental/b'),
          f('a/experimental'),
          f('a/experimental.cc'),
          f('a/experimental.S'),
        ],
        [
          # Expected.
          'a/experimental',
          'a/experimental.cc',
          'a/experimental.S',
        ],
      ),
      (
        [
          # To be tested.
          f('a/third_party/b'),
          f('third_party/b'),
          f('a/third_party'),
          f('a/third_party.cc'),
        ],
        [
          # Expected.
          'a/third_party',
          'a/third_party.cc',
        ],
      ),
      (
        [
          # To be tested.
          f('a/LOL_FILE/b'),
          f('b.c/LOL_FILE'),
          f('a/PRESUBMIT.py'),
        ],
        [
          # Expected.
          'a/LOL_FILE/b',
          'a/PRESUBMIT.py',
        ],
      ),
      (
        [
          # To be tested.
          f('a/.git'),
          f('b.c/.git'),
          f('a/.git/bleh.py'),
          f('.git/bleh.py'),
        ],
        [
          # Expected.
        ],
      ),
    ]
    input_api = presubmit.InputApi(self.fake_change, './PRESUBMIT.py', False,
        False, None)
    self.mox.ReplayAll()

    self.assertEqual(len(input_api.DEFAULT_WHITE_LIST), 22)
    self.assertEqual(len(input_api.DEFAULT_BLACK_LIST), 9)
    for item in files:
      results = filter(input_api.FilterSourceFile, item[0])
      for i in range(len(results)):
        self.assertEquals(results[i].LocalPath(),
                          presubmit.normpath(item[1][i]))
      # Same number of expected results.
      self.assertEquals(sorted([f.LocalPath().replace(presubmit.os.sep, '/')
                                for f in results]),
                        sorted(item[1]))

  def testCustomFilter(self):
    def FilterSourceFile(affected_file):
      return 'a' in affected_file.LocalPath()
    files = [('A', 'eeaee'), ('M', 'eeabee'), ('M', 'eebcee')]
    for _, item in files:
      item = presubmit.os.path.join(self.fake_root_dir, item)
      presubmit.os.path.exists(item).AndReturn(True)
      presubmit.os.path.isdir(item).AndReturn(False)
      presubmit.scm.SVN.GetFileProperty(item, 'svn:mime-type').AndReturn(None)
    self.mox.ReplayAll()

    change = presubmit.SvnChange('mychange', '', self.fake_root_dir, files, 0,
                                 0)
    input_api = presubmit.InputApi(change,
                                   presubmit.os.path.join(self.fake_root_dir,
                                                          'PRESUBMIT.py'),
                                   False, False, None)
    got_files = input_api.AffectedSourceFiles(FilterSourceFile)
    self.assertEquals(len(got_files), 2)
    self.assertEquals(got_files[0].LocalPath(), 'eeaee')
    self.assertEquals(got_files[1].LocalPath(), 'eeabee')

  def testLambdaFilter(self):
    white_list = presubmit.InputApi.DEFAULT_BLACK_LIST + (r".*?a.*?",)
    black_list = [r".*?b.*?"]
    files = [('A', 'eeaee'), ('M', 'eeabee'), ('M', 'eebcee'), ('M', 'eecaee')]
    for _, item in files:
      item = presubmit.os.path.join(self.fake_root_dir, item)
      presubmit.os.path.exists(item).AndReturn(True)
      presubmit.os.path.isdir(item).AndReturn(False)
      presubmit.scm.SVN.GetFileProperty(item, 'svn:mime-type').AndReturn(None)
    self.mox.ReplayAll()

    change = presubmit.SvnChange('mychange', '', self.fake_root_dir, files, 0,
                                 0)
    input_api = presubmit.InputApi(change, './PRESUBMIT.py', False,
                                   False, None)
    # Sample usage of overiding the default white and black lists.
    got_files = input_api.AffectedSourceFiles(
        lambda x: input_api.FilterSourceFile(x, white_list, black_list))
    self.assertEquals(len(got_files), 2)
    self.assertEquals(got_files[0].LocalPath(), 'eeaee')
    self.assertEquals(got_files[1].LocalPath(), 'eecaee')

  def testGetAbsoluteLocalPath(self):
    join = presubmit.os.path.join
    normpath = presubmit.normpath
    # Regression test for bug of presubmit stuff that relies on invoking
    # SVN (e.g. to get mime type of file) not working unless gcl invoked
    # from the client root (e.g. if you were at 'src' and did 'cd base' before
    # invoking 'gcl upload' it would fail because svn wouldn't find the files
    # the presubmit script was asking about).
    files = [
      ['A', 'isdir'],
      ['A', join('isdir', 'blat.cc')],
      ['M', join('elsewhere', 'ouf.cc')],
    ]
    self.mox.ReplayAll()

    change = presubmit.Change('mychange', '', self.fake_root_dir, files, 0, 0)
    affected_files = change.AffectedFiles(include_dirs=True)
    # Local paths should remain the same
    self.assertEquals(affected_files[0].LocalPath(), normpath('isdir'))
    self.assertEquals(affected_files[1].LocalPath(), normpath('isdir/blat.cc'))
    # Absolute paths should be prefixed
    self.assertEquals(affected_files[0].AbsoluteLocalPath(),
                      normpath(join(self.fake_root_dir, 'isdir')))
    self.assertEquals(affected_files[1].AbsoluteLocalPath(),
                      normpath(join(self.fake_root_dir, 'isdir/blat.cc')))

    # New helper functions need to work
    paths_from_change = change.AbsoluteLocalPaths(include_dirs=True)
    self.assertEqual(len(paths_from_change), 3)
    presubmit_path = join(self.fake_root_dir, 'isdir', 'PRESUBMIT.py')
    api = presubmit.InputApi(change=change,
                             presubmit_path=presubmit_path,
                             is_committing=True, tbr=False, host_url=None)
    paths_from_api = api.AbsoluteLocalPaths(include_dirs=True)
    self.assertEqual(len(paths_from_api), 2)
    for absolute_paths in [paths_from_change, paths_from_api]:
      self.assertEqual(absolute_paths[0],
                       normpath(join(self.fake_root_dir, 'isdir')))
      self.assertEqual(absolute_paths[1],
                       normpath(join(self.fake_root_dir, 'isdir', 'blat.cc')))

  def testDeprecated(self):
    presubmit.warn(mox.IgnoreArg(), category=mox.IgnoreArg(), stacklevel=2)
    self.mox.ReplayAll()

    change = presubmit.Change('mychange', '', self.fake_root_dir, [], 0, 0)
    api = presubmit.InputApi(
        change,
        presubmit.os.path.join(self.fake_root_dir, 'foo', 'PRESUBMIT.py'), True,
        False, None)
    api.AffectedTextFiles(include_deletes=False)

  def testReadFileStringDenied(self):
    self.mox.ReplayAll()

    change = presubmit.Change('foo', 'foo', self.fake_root_dir, [('M', 'AA')],
                              0, 0)
    input_api = presubmit.InputApi(
        change, presubmit.os.path.join(self.fake_root_dir, '/p'), False,
        False, None)
    self.assertRaises(IOError, input_api.ReadFile, 'boo', 'x')

  def testReadFileStringAccepted(self):
    path = presubmit.os.path.join(self.fake_root_dir, 'AA/boo')
    presubmit.gclient_utils.FileRead(path, 'x').AndReturn(None)
    self.mox.ReplayAll()

    change = presubmit.Change('foo', 'foo', self.fake_root_dir, [('M', 'AA')],
                              0, 0)
    input_api = presubmit.InputApi(
        change, presubmit.os.path.join(self.fake_root_dir, '/p'), False,
        False, None)
    input_api.ReadFile(path, 'x')

  def testReadFileAffectedFileDenied(self):
    fileobj = presubmit.AffectedFile('boo', 'M', 'Unrelated')
    self.mox.ReplayAll()

    change = presubmit.Change('foo', 'foo', self.fake_root_dir, [('M', 'AA')],
                              0, 0)
    input_api = presubmit.InputApi(
        change, presubmit.os.path.join(self.fake_root_dir, '/p'), False,
        False, None)
    self.assertRaises(IOError, input_api.ReadFile, fileobj, 'x')

  def testReadFileAffectedFileAccepted(self):
    fileobj = presubmit.AffectedFile('AA/boo', 'M', self.fake_root_dir)
    presubmit.gclient_utils.FileRead(fileobj.AbsoluteLocalPath(), 'x'
                                     ).AndReturn(None)
    self.mox.ReplayAll()

    change = presubmit.Change('foo', 'foo', self.fake_root_dir, [('M', 'AA')],
                              0, 0)
    input_api = presubmit.InputApi(
        change, presubmit.os.path.join(self.fake_root_dir, '/p'), False,
        False, None)
    input_api.ReadFile(fileobj, 'x')


class OuputApiUnittest(PresubmitTestsBase):
  """Tests presubmit.OutputApi."""
  def testMembersChanged(self):
    self.mox.ReplayAll()
    members = [
      'MailTextResult', 'PresubmitAddReviewers', 'PresubmitError',
      'PresubmitNotifyResult', 'PresubmitPromptWarning', 'PresubmitResult',
    ]
    # If this test fails, you should add the relevant test.
    self.compareMembers(presubmit.OutputApi(), members)

  def testOutputApiBasics(self):
    self.mox.ReplayAll()
    self.failUnless(presubmit.OutputApi.PresubmitError('').fatal)
    self.failIf(presubmit.OutputApi.PresubmitError('').should_prompt)

    self.failIf(presubmit.OutputApi.PresubmitPromptWarning('').fatal)
    self.failUnless(
        presubmit.OutputApi.PresubmitPromptWarning('').should_prompt)

    self.failIf(presubmit.OutputApi.PresubmitNotifyResult('').fatal)
    self.failIf(presubmit.OutputApi.PresubmitNotifyResult('').should_prompt)

    self.failIf(presubmit.OutputApi.PresubmitAddReviewers(
        ['foo']).fatal)
    self.failIf(presubmit.OutputApi.PresubmitAddReviewers(
        ['foo']).should_prompt)

    # TODO(joi) Test MailTextResult once implemented.

  def testOutputApiHandling(self):
    self.mox.ReplayAll()

    output = presubmit.PresubmitOutput()
    presubmit.OutputApi.PresubmitAddReviewers(
        ['ben@example.com']).handle(output)
    self.failUnless(output.should_continue())
    self.failUnlessEqual(output.reviewers, ['ben@example.com'])

    output = presubmit.PresubmitOutput()
    presubmit.OutputApi.PresubmitError('!!!').handle(output)
    self.failIf(output.should_continue())
    self.failUnless(output.getvalue().count('!!!'))

    output = presubmit.PresubmitOutput()
    presubmit.OutputApi.PresubmitNotifyResult('?see?').handle(output)
    self.failUnless(output.should_continue())
    self.failUnless(output.getvalue().count('?see?'))

    output = presubmit.PresubmitOutput(input_stream=StringIO.StringIO('y'))
    presubmit.OutputApi.PresubmitPromptWarning('???').handle(output)
    output.prompt_yes_no('prompt: ')
    self.failUnless(output.should_continue())
    self.failUnless(output.getvalue().count('???'))

    output = presubmit.PresubmitOutput(input_stream=StringIO.StringIO('y'))
    presubmit.OutputApi.PresubmitPromptWarning('???').handle(output)
    output.prompt_yes_no('prompt: ')
    self.failUnless(output.should_continue())
    self.failUnless(output.getvalue().count('???'))

    output = presubmit.PresubmitOutput(input_stream=StringIO.StringIO('\n'))
    presubmit.OutputApi.PresubmitPromptWarning('???').handle(output)
    output.prompt_yes_no('prompt: ')
    self.failIf(output.should_continue())
    self.failUnless(output.getvalue().count('???'))


class AffectedFileUnittest(PresubmitTestsBase):
  def testMembersChanged(self):
    self.mox.ReplayAll()
    members = [
      'AbsoluteLocalPath', 'Action', 'ChangedContents', 'GenerateScmDiff',
      'IsDirectory', 'IsTextFile', 'LocalPath', 'NewContents', 'OldContents',
      'OldFileTempPath', 'Property', 'ServerPath',
    ]
    # If this test fails, you should add the relevant test.
    self.compareMembers(presubmit.AffectedFile('a', 'b'), members)
    self.compareMembers(presubmit.SvnAffectedFile('a', 'b'), members)

  def testAffectedFile(self):
    path = presubmit.os.path.join('foo', 'blat.cc')
    presubmit.os.path.exists(path).AndReturn(True)
    presubmit.os.path.isdir(path).AndReturn(False)
    presubmit.gclient_utils.FileRead(path, 'rU').AndReturn('whatever\ncookie')
    presubmit.scm.SVN.CaptureInfo(path).AndReturn(
        {'URL': 'svn:/foo/foo/blat.cc'})
    self.mox.ReplayAll()
    af = presubmit.SvnAffectedFile('foo/blat.cc', 'M')
    self.failUnless(af.ServerPath() == 'svn:/foo/foo/blat.cc')
    self.failUnless(af.LocalPath() == presubmit.normpath('foo/blat.cc'))
    self.failUnless(af.Action() == 'M')
    self.assertEquals(af.NewContents(), ['whatever', 'cookie'])
    af = presubmit.AffectedFile('notfound.cc', 'A')
    self.failUnless(af.ServerPath() == '')

  def testProperty(self):
    presubmit.scm.SVN.GetFileProperty('foo.cc', 'svn:secret-property'
        ).AndReturn('secret-property-value')
    self.mox.ReplayAll()
    affected_file = presubmit.SvnAffectedFile('foo.cc', 'A')
    # Verify cache coherency.
    self.failUnless(affected_file.Property('svn:secret-property') ==
                    'secret-property-value')
    self.failUnless(affected_file.Property('svn:secret-property') ==
                    'secret-property-value')

  def testIsDirectoryNotExists(self):
    presubmit.os.path.exists('foo.cc').AndReturn(False)
    presubmit.scm.SVN.CaptureInfo('foo.cc').AndReturn({})
    self.mox.ReplayAll()
    affected_file = presubmit.SvnAffectedFile('foo.cc', 'A')
    # Verify cache coherency.
    self.failIf(affected_file.IsDirectory())
    self.failIf(affected_file.IsDirectory())

  def testIsDirectory(self):
    presubmit.os.path.exists('foo.cc').AndReturn(True)
    presubmit.os.path.isdir('foo.cc').AndReturn(True)
    self.mox.ReplayAll()
    affected_file = presubmit.SvnAffectedFile('foo.cc', 'A')
    # Verify cache coherency.
    self.failUnless(affected_file.IsDirectory())
    self.failUnless(affected_file.IsDirectory())

  def testIsTextFile(self):
    files = [presubmit.SvnAffectedFile('foo/blat.txt', 'M'),
            presubmit.SvnAffectedFile('foo/binary.blob', 'M'),
            presubmit.SvnAffectedFile('blat/flop.txt', 'D')]
    blat = presubmit.os.path.join('foo', 'blat.txt')
    blob = presubmit.os.path.join('foo', 'binary.blob')
    presubmit.os.path.exists(blat).AndReturn(True)
    presubmit.os.path.isdir(blat).AndReturn(False)
    presubmit.os.path.exists(blob).AndReturn(True)
    presubmit.os.path.isdir(blob).AndReturn(False)
    presubmit.scm.SVN.GetFileProperty(blat, 'svn:mime-type').AndReturn(None)
    presubmit.scm.SVN.GetFileProperty(blob, 'svn:mime-type'
        ).AndReturn('application/octet-stream')
    self.mox.ReplayAll()

    output = filter(lambda x: x.IsTextFile(), files)
    self.failUnless(len(output) == 1)
    self.failUnless(files[0] == output[0])


class GclChangeUnittest(PresubmitTestsBase):
  def testMembersChanged(self):
    members = [
        'AbsoluteLocalPaths', 'AffectedFiles', 'AffectedTextFiles',
        'DescriptionText', 'FullDescriptionText', 'LocalPaths', 'Name',
        'RepositoryRoot', 'RightHandSideLines', 'ServerPaths',
        'issue', 'patchset', 'scm', 'tags',
    ]
    # If this test fails, you should add the relevant test.
    self.mox.ReplayAll()

    change = presubmit.Change('foo', 'foo', self.fake_root_dir, [('M', 'AA')],
                              0, 0)
    self.compareMembers(change, members)


class CannedChecksUnittest(PresubmitTestsBase):
  """Tests presubmit_canned_checks.py."""

  def setUp(self):
    PresubmitTestsBase.setUp(self)

  def MockInputApi(self, change, committing):
    input_api = self.mox.CreateMock(presubmit.InputApi)
    input_api.cStringIO = presubmit.cStringIO
    input_api.os_path = presubmit.os.path
    input_api.re = presubmit.re
    input_api.traceback = presubmit.traceback
    input_api.urllib2 = self.mox.CreateMock(presubmit.urllib2)
    input_api.unittest = unittest
    input_api.subprocess = self.mox.CreateMock(presubmit.subprocess)

    input_api.change = change
    input_api.host_url = 'http://localhost'
    input_api.is_committing = committing
    input_api.tbr = False
    input_api.python_executable = 'pyyyyython'
    return input_api

  def testMembersChanged(self):
    self.mox.ReplayAll()
    members = [
      'CheckBuildbotPendingBuilds',
      'CheckChangeHasBugField', 'CheckChangeHasDescription',
      'CheckChangeHasNoStrayWhitespace',
      'CheckChangeHasOnlyOneEol', 'CheckChangeHasNoCR',
      'CheckChangeHasNoCrAndHasOnlyOneEol', 'CheckChangeHasNoTabs',
      'CheckChangeTodoHasOwner',
      'CheckChangeHasQaField', 'CheckChangeHasTestedField',
      'CheckChangeHasTestField',
      'CheckChangeLintsClean',
      'CheckChangeSvnEolStyle',
      'CheckDoNotSubmit',
      'CheckDoNotSubmitInDescription', 'CheckDoNotSubmitInFiles',
      'CheckLongLines', 'CheckTreeIsOpen', 'PanProjectChecks',
      'CheckLicense',
      'CheckOwners',
      'CheckRietveldTryJobExecution',
      'CheckSvnModifiedDirectories',
      'CheckSvnForCommonMimeTypes', 'CheckSvnProperty',
      'RunPythonUnitTests', 'RunPylint',
    ]
    # If this test fails, you should add the relevant test.
    self.compareMembers(presubmit_canned_checks, members)

  def DescriptionTest(self, check, description1, description2, error_type,
                      committing):
    change1 = presubmit.Change('foo1', description1, self.fake_root_dir, None,
                               0, 0)
    input_api1 = self.MockInputApi(change1, committing)
    change2 = presubmit.Change('foo2', description2, self.fake_root_dir, None,
                               0, 0)
    input_api2 = self.MockInputApi(change2, committing)
    self.mox.ReplayAll()

    results1 = check(input_api1, presubmit.OutputApi)
    self.assertEquals(results1, [])
    results2 = check(input_api2, presubmit.OutputApi)
    self.assertEquals(len(results2), 1)
    self.assertEquals(results2[0].__class__, error_type)

  def ContentTest(self, check, content1, content2, error_type):
    change1 = presubmit.Change('foo1', 'foo1\n', self.fake_root_dir, None,
                               0, 0)
    input_api1 = self.MockInputApi(change1, False)
    affected_file = self.mox.CreateMock(presubmit.SvnAffectedFile)
    affected_file.LocalPath().AndReturn('foo.cc')
    # Format is (file, line number, line content)
    output1 = [
      (affected_file, 42, 'yo, ' + content1),
      (affected_file, 43, 'yer'),
      (affected_file, 23, 'ya'),
    ]
    input_api1.RightHandSideLines(mox.IgnoreArg()).AndReturn(output1)
    change2 = presubmit.Change('foo2', 'foo2\n', self.fake_root_dir, None,
                               0, 0)
    input_api2 = self.MockInputApi(change2, False)
    output2 = [
      (affected_file, 42, 'yo, ' + content2),
      (affected_file, 43, 'yer'),
      (affected_file, 23, 'ya'),
    ]
    input_api2.RightHandSideLines(mox.IgnoreArg()).AndReturn(output2)
    self.mox.ReplayAll()

    results1 = check(input_api1, presubmit.OutputApi, None)
    self.assertEquals(results1, [])
    results2 = check(input_api2, presubmit.OutputApi, None)
    self.assertEquals(len(results2), 1)
    self.assertEquals(results2[0].__class__, error_type)

  def ReadFileTest(self, check, content1, content2, error_type):
    self.mox.StubOutWithMock(presubmit.InputApi, 'ReadFile')
    change1 = presubmit.Change('foo1', 'foo1\n', self.fake_root_dir, None,
                               0, 0)
    input_api1 = self.MockInputApi(change1, False)
    affected_file1 = self.mox.CreateMock(presubmit.SvnAffectedFile)
    input_api1.AffectedSourceFiles(None).AndReturn([affected_file1])
    input_api1.ReadFile(affected_file1, 'rb').AndReturn(content1)
    change2 = presubmit.Change('foo2', 'foo2\n', self.fake_root_dir, None,
                               0, 0)
    input_api2 = self.MockInputApi(change2, False)
    affected_file2 = self.mox.CreateMock(presubmit.SvnAffectedFile)
    input_api2.AffectedSourceFiles(None).AndReturn([affected_file2])
    input_api2.ReadFile(affected_file2, 'rb').AndReturn(content2)
    affected_file2.LocalPath().AndReturn('bar.cc')
    self.mox.ReplayAll()

    results = check(input_api1, presubmit.OutputApi)
    self.assertEquals(results, [])
    results2 = check(input_api2, presubmit.OutputApi)
    self.assertEquals(len(results2), 1)
    self.assertEquals(results2[0].__class__, error_type)

  def SvnPropertyTest(self, check, property_name, value1, value2, committing,
                      error_type, use_source_file):
    change1 = presubmit.SvnChange('mychange', '', self.fake_root_dir, [], 0, 0)
    input_api1 = self.MockInputApi(change1, committing)
    files1 = [
      presubmit.SvnAffectedFile('foo/bar.cc', 'A'),
      presubmit.SvnAffectedFile('foo.cc', 'M'),
    ]
    if use_source_file:
      input_api1.AffectedSourceFiles(None).AndReturn(files1)
    else:
      input_api1.AffectedFiles(include_deleted=False).AndReturn(files1)
    presubmit.scm.SVN.GetFileProperty(presubmit.normpath('foo/bar.cc'),
                                      property_name).AndReturn(value1)
    presubmit.scm.SVN.GetFileProperty(presubmit.normpath('foo.cc'),
                                      property_name).AndReturn(value1)
    change2 = presubmit.SvnChange('mychange', '', self.fake_root_dir, [], 0, 0)
    input_api2 = self.MockInputApi(change2, committing)
    files2 = [
      presubmit.SvnAffectedFile('foo/bar.cc', 'A'),
      presubmit.SvnAffectedFile('foo.cc', 'M'),
    ]
    if use_source_file:
      input_api2.AffectedSourceFiles(None).AndReturn(files2)
    else:
      input_api2.AffectedFiles(include_deleted=False).AndReturn(files2)

    presubmit.scm.SVN.GetFileProperty(presubmit.normpath('foo/bar.cc'),
                                      property_name).AndReturn(value2)
    presubmit.scm.SVN.GetFileProperty(presubmit.normpath('foo.cc'),
                                      property_name).AndReturn(value2)
    self.mox.ReplayAll()

    results1 = check(input_api1, presubmit.OutputApi, None)
    self.assertEquals(results1, [])
    results2 = check(input_api2, presubmit.OutputApi, None)
    self.assertEquals(len(results2), 1)
    self.assertEquals(results2[0].__class__, error_type)

  def testCannedCheckChangeHasBugField(self):
    self.DescriptionTest(presubmit_canned_checks.CheckChangeHasBugField,
                         'Foo\nBUG=1234', 'Foo\n',
                         presubmit.OutputApi.PresubmitNotifyResult,
                         False)

  def testCheckChangeHasDescription(self):
    self.DescriptionTest(presubmit_canned_checks.CheckChangeHasDescription,
                         'Bleh', '',
                         presubmit.OutputApi.PresubmitNotifyResult,
                         False)
    self.mox.VerifyAll()
    self.DescriptionTest(presubmit_canned_checks.CheckChangeHasDescription,
                         'Bleh', '',
                         presubmit.OutputApi.PresubmitError,
                         True)

  def testCannedCheckChangeHasTestField(self):
    self.DescriptionTest(presubmit_canned_checks.CheckChangeHasTestField,
                         'Foo\nTEST=did some stuff', 'Foo\n',
                         presubmit.OutputApi.PresubmitNotifyResult,
                         False)

  def testCannedCheckChangeHasTestedField(self):
    self.DescriptionTest(presubmit_canned_checks.CheckChangeHasTestedField,
                         'Foo\nTESTED=did some stuff', 'Foo\n',
                         presubmit.OutputApi.PresubmitError,
                         False)

  def testCannedCheckChangeHasQAField(self):
    self.DescriptionTest(presubmit_canned_checks.CheckChangeHasQaField,
                         'Foo\nQA=BSOD your machine', 'Foo\n',
                         presubmit.OutputApi.PresubmitError,
                         False)

  def testCannedCheckDoNotSubmitInDescription(self):
    self.DescriptionTest(presubmit_canned_checks.CheckDoNotSubmitInDescription,
                         'Foo\nDO NOTSUBMIT', 'Foo\nDO NOT ' + 'SUBMIT',
                         presubmit.OutputApi.PresubmitError,
                         False)

  def testCannedCheckDoNotSubmitInFiles(self):
    self.ContentTest(
        lambda x,y,z: presubmit_canned_checks.CheckDoNotSubmitInFiles(x, y),
        'DO NOTSUBMIT', 'DO NOT ' + 'SUBMIT',
        presubmit.OutputApi.PresubmitError)

  def testCheckChangeHasNoStrayWhitespace(self):
    self.ContentTest(
        lambda x,y,z:
            presubmit_canned_checks.CheckChangeHasNoStrayWhitespace(x, y),
        'Foo', 'Foo ',
        presubmit.OutputApi.PresubmitPromptWarning)

  def testCheckChangeHasOnlyOneEol(self):
    self.ReadFileTest(presubmit_canned_checks.CheckChangeHasOnlyOneEol,
                      "Hey!\nHo!\n", "Hey!\nHo!\n\n",
                      presubmit.OutputApi.PresubmitPromptWarning)

  def testCheckChangeHasNoCR(self):
    self.ReadFileTest(presubmit_canned_checks.CheckChangeHasNoCR,
                      "Hey!\nHo!\n", "Hey!\r\nHo!\r\n",
                      presubmit.OutputApi.PresubmitPromptWarning)

  def testCheckChangeHasNoCrAndHasOnlyOneEol(self):
    self.ReadFileTest(
        presubmit_canned_checks.CheckChangeHasNoCrAndHasOnlyOneEol,
        "Hey!\nHo!\n", "Hey!\nHo!\n\n",
        presubmit.OutputApi.PresubmitPromptWarning)
    self.mox.VerifyAll()
    self.ReadFileTest(
        presubmit_canned_checks.CheckChangeHasNoCrAndHasOnlyOneEol,
        "Hey!\nHo!\n", "Hey!\r\nHo!\r\n",
        presubmit.OutputApi.PresubmitPromptWarning)

  def testCheckChangeTodoHasOwner(self):
    self.ContentTest(presubmit_canned_checks.CheckChangeTodoHasOwner,
                     "TODO(foo): bar", "TODO: bar",
                     presubmit.OutputApi.PresubmitPromptWarning)

  def testCannedCheckChangeHasNoTabs(self):
    self.ContentTest(presubmit_canned_checks.CheckChangeHasNoTabs,
                     'blah blah', 'blah\tblah',
                     presubmit.OutputApi.PresubmitPromptWarning)

    # Make sure makefiles are ignored.
    change1 = presubmit.Change('foo1', 'foo1\n', self.fake_root_dir, None,
                               0, 0)
    input_api1 = self.MockInputApi(change1, False)
    affected_file1 = self.mox.CreateMock(presubmit.SvnAffectedFile)
    affected_file1.LocalPath().AndReturn('foo.cc')
    affected_file2 = self.mox.CreateMock(presubmit.SvnAffectedFile)
    affected_file2.LocalPath().AndReturn('foo/Makefile')
    affected_file3 = self.mox.CreateMock(presubmit.SvnAffectedFile)
    affected_file3.LocalPath().AndReturn('makefile')
    # Only this one will trigger.
    affected_file4 = self.mox.CreateMock(presubmit.SvnAffectedFile)
    affected_file4.LocalPath().AndReturn('makefile.foo')
    affected_file4.LocalPath().AndReturn('makefile.foo')
    output1 = [
      (affected_file1, 42, 'yo, '),
      (affected_file2, 43, 'yer\t'),
      (affected_file3, 45, 'yr\t'),
      (affected_file4, 46, 'ye\t'),
    ]
    def test(source_filter):
      for i in output1:
        if source_filter(i[0]):
          yield i
    # Override the mock of these functions.
    input_api1.FilterSourceFile = lambda x: x
    input_api1.RightHandSideLines = test
    self.mox.ReplayAll()

    results1 = presubmit_canned_checks.CheckChangeHasNoTabs(input_api1,
        presubmit.OutputApi, None)
    self.assertEquals(len(results1), 1)
    self.assertEquals(results1[0].__class__,
        presubmit.OutputApi.PresubmitPromptWarning)
    self.assertEquals(results1[0]._long_text,
        'makefile.foo, line 46')


  def testCannedCheckLongLines(self):
    check = lambda x, y, z: presubmit_canned_checks.CheckLongLines(x, y, 10, z)
    self.ContentTest(check, '', 'blah blah blah',
                     presubmit.OutputApi.PresubmitPromptWarning)

  def testCheckChangeSvnEolStyleCommit(self):
    # Test CheckSvnProperty at the same time.
    self.SvnPropertyTest(presubmit_canned_checks.CheckChangeSvnEolStyle,
                         'svn:eol-style', 'LF', '', True,
                         presubmit.OutputApi.PresubmitError, True)

  def testCheckChangeSvnEolStyleUpload(self):
    self.SvnPropertyTest(presubmit_canned_checks.CheckChangeSvnEolStyle,
                         'svn:eol-style', 'LF', '', False,
                         presubmit.OutputApi.PresubmitNotifyResult, True)

  def _LicenseCheck(self, text, license_text, committing, expected_result,
      **kwargs):
    change = self.mox.CreateMock(presubmit.SvnChange)
    change.scm = 'svn'
    input_api = self.MockInputApi(change, committing)
    affected_file = self.mox.CreateMock(presubmit.SvnAffectedFile)
    input_api.AffectedSourceFiles(42).AndReturn([affected_file])
    input_api.ReadFile(affected_file, 'rb').AndReturn(text)
    if expected_result:
      affected_file.LocalPath().AndReturn('bleh')

    self.mox.ReplayAll()
    result = presubmit_canned_checks.CheckLicense(
                 input_api, presubmit.OutputApi, license_text,
                 source_file_filter=42,
                 **kwargs)
    if expected_result:
      self.assertEqual(len(result), 1)
      self.assertEqual(result[0].__class__, expected_result)
    else:
      self.assertEqual(result, [])

  def testCheckLicenseSuccess(self):
    text = (
        "#!/bin/python\n"
        "# Copyright (c) 2037 Nobody.\n"
        "# All Rights Reserved.\n"
        "print 'foo'\n"
    )
    license_text = (
        r".*? Copyright \(c\) 2037 Nobody." "\n"
        r".*? All Rights Reserved\." "\n"
    )
    self._LicenseCheck(text, license_text, True, None)

  def testCheckLicenseFailCommit(self):
    text = (
        "#!/bin/python\n"
        "# Copyright (c) 2037 Nobody.\n"
        "# All Rights Reserved.\n"
        "print 'foo'\n"
    )
    license_text = (
        r".*? Copyright \(c\) 0007 Nobody." "\n"
        r".*? All Rights Reserved\." "\n"
    )
    self._LicenseCheck(text, license_text, True,
                       presubmit.OutputApi.PresubmitPromptWarning)

  def testCheckLicenseFailUpload(self):
    text = (
        "#!/bin/python\n"
        "# Copyright (c) 2037 Nobody.\n"
        "# All Rights Reserved.\n"
        "print 'foo'\n"
    )
    license_text = (
        r".*? Copyright \(c\) 0007 Nobody." "\n"
        r".*? All Rights Reserved\." "\n"
    )
    self._LicenseCheck(text, license_text, False,
                       presubmit.OutputApi.PresubmitNotifyResult)

  def testCheckLicenseEmptySuccess(self):
    text = ''
    license_text = (
        r".*? Copyright \(c\) 2037 Nobody." "\n"
        r".*? All Rights Reserved\." "\n"
    )
    self._LicenseCheck(text, license_text, True, None, accept_empty_files=True)

  def testCannedCheckSvnAccidentalSubmission(self):
    modified_dir_file = 'foo/'
    accidental_submssion_file = 'foo/bar.cc'

    change = self.mox.CreateMock(presubmit.SvnChange)
    change.scm = 'svn'
    change.GetModifiedFiles().AndReturn([modified_dir_file])
    change.GetAllModifiedFiles().AndReturn([modified_dir_file,
                                            accidental_submssion_file])
    input_api = self.MockInputApi(change, True)

    affected_file = self.mox.CreateMock(presubmit.SvnAffectedFile)
    affected_file.Action().AndReturn('M')
    affected_file.IsDirectory().AndReturn(True)
    affected_file.AbsoluteLocalPath().AndReturn(accidental_submssion_file)
    affected_file.LocalPath().AndReturn(accidental_submssion_file)
    input_api.AffectedFiles(None).AndReturn([affected_file])

    self.mox.ReplayAll()

    check = presubmit_canned_checks.CheckSvnModifiedDirectories
    results = check(input_api, presubmit.OutputApi, None)
    self.assertEquals(len(results), 1)
    self.assertEquals(results[0].__class__,
                      presubmit.OutputApi.PresubmitPromptWarning)

  def testCheckSvnForCommonMimeTypes(self):
    self.mox.StubOutWithMock(presubmit_canned_checks, 'CheckSvnProperty')
    input_api = self.MockInputApi(None, False)
    output_api = presubmit.OutputApi()
    A = lambda x: presubmit.AffectedFile(x, 'M')
    files = [
      A('a.pdf'), A('b.bmp'), A('c.gif'), A('d.png'), A('e.jpg'), A('f.jpe'),
      A('random'), A('g.jpeg'), A('h.ico'),
    ]
    input_api.AffectedFiles(include_deletes=False).AndReturn(files)
    presubmit_canned_checks.CheckSvnProperty(
        input_api, output_api, 'svn:mime-type', 'application/pdf', [files[0]]
        ).AndReturn([1])
    presubmit_canned_checks.CheckSvnProperty(
        input_api, output_api, 'svn:mime-type', 'image/bmp', [files[1]]
        ).AndReturn([2])
    presubmit_canned_checks.CheckSvnProperty(
        input_api, output_api, 'svn:mime-type', 'image/gif', [files[2]]
        ).AndReturn([3])
    presubmit_canned_checks.CheckSvnProperty(
        input_api, output_api, 'svn:mime-type', 'image/png', [files[3]]
        ).AndReturn([4])
    presubmit_canned_checks.CheckSvnProperty(
        input_api, output_api, 'svn:mime-type', 'image/jpeg',
        [files[4], files[5], files[7]]
        ).AndReturn([5])
    presubmit_canned_checks.CheckSvnProperty(
        input_api, output_api, 'svn:mime-type', 'image/vnd.microsoft.icon',
        [files[8]]).AndReturn([6])
    self.mox.ReplayAll()

    results = presubmit_canned_checks.CheckSvnForCommonMimeTypes(
        input_api, output_api)
    self.assertEquals(results, [1, 2, 3, 4, 5, 6])

  def testCannedCheckTreeIsOpenOpen(self):
    input_api = self.MockInputApi(None, True)
    connection = self.mox.CreateMockAnything()
    input_api.urllib2.urlopen('url_to_open').AndReturn(connection)
    connection.read().AndReturn('The tree is open')
    connection.close()
    self.mox.ReplayAll()
    results = presubmit_canned_checks.CheckTreeIsOpen(
        input_api, presubmit.OutputApi, url='url_to_open', closed='.*closed.*')
    self.assertEquals(results, [])

  def testCannedCheckTreeIsOpenClosed(self):
    input_api = self.MockInputApi(None, True)
    connection = self.mox.CreateMockAnything()
    input_api.urllib2.urlopen('url_to_closed').AndReturn(connection)
    connection.read().AndReturn('Tree is closed for maintenance')
    connection.close()
    self.mox.ReplayAll()
    results = presubmit_canned_checks.CheckTreeIsOpen(
        input_api, presubmit.OutputApi,
        url='url_to_closed', closed='.*closed.*')
    self.assertEquals(len(results), 1)
    self.assertEquals(results[0].__class__,
                      presubmit.OutputApi.PresubmitError)

  def testCannedCheckJsonTreeIsOpenOpen(self):
    input_api = self.MockInputApi(None, True)
    input_api.json = presubmit.json
    connection = self.mox.CreateMockAnything()
    input_api.urllib2.urlopen('url_to_open').AndReturn(connection)
    status = {
        'can_commit_freely': True,
        'general_state': 'open',
        'message': 'The tree is open'
    }
    connection.read().AndReturn(input_api.json.dumps(status))
    connection.close()
    self.mox.ReplayAll()
    results = presubmit_canned_checks.CheckTreeIsOpen(
        input_api, presubmit.OutputApi, json_url='url_to_open')
    self.assertEquals(results, [])

  def testCannedCheckJsonTreeIsOpenClosed(self):
    input_api = self.MockInputApi(None, True)
    input_api.json = presubmit.json
    connection = self.mox.CreateMockAnything()
    input_api.urllib2.urlopen('url_to_closed').AndReturn(connection)
    status = {
        'can_commit_freely': False,
        'general_state': 'closed',
        'message': 'The tree is close',
    }
    connection.read().AndReturn(input_api.json.dumps(status))
    connection.close()
    self.mox.ReplayAll()
    results = presubmit_canned_checks.CheckTreeIsOpen(
        input_api, presubmit.OutputApi, json_url='url_to_closed')
    self.assertEquals(len(results), 1)
    self.assertEquals(results[0].__class__,
                      presubmit.OutputApi.PresubmitError)

  def testRunPythonUnitTestsNoTest(self):
    input_api = self.MockInputApi(None, False)
    self.mox.ReplayAll()
    results = presubmit_canned_checks.RunPythonUnitTests(
        input_api, presubmit.OutputApi, [])
    self.assertEquals(results, [])

  def testRunPythonUnitTestsNonExistentUpload(self):
    input_api = self.MockInputApi(None, False)
    process = self.mox.CreateMockAnything()
    process.returncode = 2
    input_api.subprocess.Popen(
        ['pyyyyython', '-m', '_non_existent_module'], cwd=None, env=None,
        stderr=presubmit.subprocess.PIPE, stdin=presubmit.subprocess.PIPE,
        stdout=presubmit.subprocess.PIPE).AndReturn(process)
    process.communicate().AndReturn(
        ('', 'pyyython: module _non_existent_module not found'))
    self.mox.ReplayAll()

    results = presubmit_canned_checks.RunPythonUnitTests(
        input_api, presubmit.OutputApi, ['_non_existent_module'])
    self.assertEquals(len(results), 1)
    self.assertEquals(results[0].__class__,
                      presubmit.OutputApi.PresubmitNotifyResult)

  def testRunPythonUnitTestsNonExistentCommitting(self):
    input_api = self.MockInputApi(None, True)
    process = self.mox.CreateMockAnything()
    process.returncode = 2
    input_api.subprocess.Popen(
        ['pyyyyython', '-m', '_non_existent_module'], cwd=None, env=None,
        stderr=presubmit.subprocess.PIPE, stdin=presubmit.subprocess.PIPE,
        stdout=presubmit.subprocess.PIPE).AndReturn(process)
    process.communicate().AndReturn(
        ('', 'pyyython: module _non_existent_module not found'))
    self.mox.ReplayAll()
    results = presubmit_canned_checks.RunPythonUnitTests(
        input_api, presubmit.OutputApi, ['_non_existent_module'])
    self.assertEquals(len(results), 1)
    self.assertEquals(results[0].__class__, presubmit.OutputApi.PresubmitError)

  def testRunPythonUnitTestsFailureUpload(self):
    input_api = self.MockInputApi(None, False)
    input_api.unittest = self.mox.CreateMock(unittest)
    input_api.cStringIO = self.mox.CreateMock(presubmit.cStringIO)
    process = self.mox.CreateMockAnything()
    process.returncode = -1
    input_api.subprocess.Popen(
        ['pyyyyython', '-m', 'test_module'], cwd=None, env=None,
        stderr=presubmit.subprocess.PIPE, stdin=presubmit.subprocess.PIPE,
        stdout=presubmit.subprocess.PIPE).AndReturn(process)
    process.communicate().AndReturn(('BOO HOO!', ''))
    self.mox.ReplayAll()

    results = presubmit_canned_checks.RunPythonUnitTests(
        input_api, presubmit.OutputApi, ['test_module'])
    self.assertEquals(len(results), 1)
    self.assertEquals(results[0].__class__,
                      presubmit.OutputApi.PresubmitNotifyResult)
    self.assertEquals(results[0]._long_text,
                      "Test 'test_module' failed with code -1\nBOO HOO!")

  def testRunPythonUnitTestsFailureCommitting(self):
    input_api = self.MockInputApi(None, True)
    process = self.mox.CreateMockAnything()
    process.returncode = 1
    input_api.subprocess.Popen(
        ['pyyyyython', '-m', 'test_module'], cwd=None, env=None,
        stderr=presubmit.subprocess.PIPE, stdin=presubmit.subprocess.PIPE,
        stdout=presubmit.subprocess.PIPE).AndReturn(process)
    process.communicate().AndReturn(('BOO HOO!', ''))
    self.mox.ReplayAll()

    results = presubmit_canned_checks.RunPythonUnitTests(
        input_api, presubmit.OutputApi, ['test_module'])
    self.assertEquals(len(results), 1)
    self.assertEquals(results[0].__class__, presubmit.OutputApi.PresubmitError)
    self.assertEquals(results[0]._long_text,
                      "Test 'test_module' failed with code 1\nBOO HOO!")

  def testRunPythonUnitTestsSuccess(self):
    input_api = self.MockInputApi(None, False)
    input_api.cStringIO = self.mox.CreateMock(presubmit.cStringIO)
    input_api.unittest = self.mox.CreateMock(unittest)
    process = self.mox.CreateMockAnything()
    process.returncode = 0
    input_api.subprocess.Popen(
        ['pyyyyython', '-m', 'test_module'], cwd=None, env=None,
        stderr=presubmit.subprocess.PIPE, stdin=presubmit.subprocess.PIPE,
        stdout=presubmit.subprocess.PIPE).AndReturn(process)
    process.communicate().AndReturn(('', ''))
    self.mox.ReplayAll()

    results = presubmit_canned_checks.RunPythonUnitTests(
        input_api, presubmit.OutputApi, ['test_module'])
    self.assertEquals(len(results), 0)

  def testCheckRietveldTryJobExecutionBad(self):
    change = self.mox.CreateMock(presubmit.SvnChange)
    change.scm = 'svn'
    change.issue = 2
    change.patchset = 5
    input_api = self.MockInputApi(change, True)
    connection = self.mox.CreateMockAnything()
    input_api.urllib2.urlopen('uurl/2/get_build_results/5').AndReturn(
        connection)
    connection.read().AndReturn('foo')
    connection.close()
    self.mox.ReplayAll()

    results = presubmit_canned_checks.CheckRietveldTryJobExecution(
        input_api, presubmit.OutputApi, 'uurl', ('mac', 'linux'), 'georges')
    self.assertEquals(len(results), 1)
    self.assertEquals(results[0].__class__,
        presubmit.OutputApi.PresubmitNotifyResult)

  def testCheckRietveldTryJobExecutionGood(self):
    change = self.mox.CreateMock(presubmit.SvnChange)
    change.scm = 'svn'
    change.issue = 2
    change.patchset = 5
    input_api = self.MockInputApi(change, True)
    connection = self.mox.CreateMockAnything()
    input_api.urllib2.urlopen('uurl/2/get_build_results/5').AndReturn(
        connection)
    connection.read().AndReturn("""amiga|Foo|blah
linux|failure|bleh
mac|success|blew
""")
    connection.close()
    self.mox.ReplayAll()

    results = presubmit_canned_checks.CheckRietveldTryJobExecution(
        input_api, presubmit.OutputApi, 'uurl', ('mac', 'linux', 'amiga'),
        'georges')
    self.assertEquals(len(results), 1)
    self.assertEquals(results[0].__class__,
        presubmit.OutputApi.PresubmitPromptWarning)

  def testCheckBuildbotPendingBuildsBad(self):
    input_api = self.MockInputApi(None, True)
    input_api.json = presubmit.json
    connection = self.mox.CreateMockAnything()
    input_api.urllib2.urlopen('uurl').AndReturn(connection)
    connection.read().AndReturn('foo')
    connection.close()
    self.mox.ReplayAll()

    results = presubmit_canned_checks.CheckBuildbotPendingBuilds(
        input_api, presubmit.OutputApi, 'uurl', 2, ('foo'))
    self.assertEquals(len(results), 1)
    self.assertEquals(results[0].__class__,
        presubmit.OutputApi.PresubmitNotifyResult)

  def testCheckBuildbotPendingBuildsGood(self):
    input_api = self.MockInputApi(None, True)
    input_api.json = presubmit.json
    connection = self.mox.CreateMockAnything()
    input_api.urllib2.urlopen('uurl').AndReturn(connection)
    connection.read().AndReturn("""
    {
      'b1': { 'pending_builds': [0, 1, 2, 3, 4, 5, 6, 7] },
      'foo': { 'pending_builds': [0, 1, 2, 3, 4, 5, 6, 7] },
      'b2': { 'pending_builds': [0] }
    }""")
    connection.close()
    self.mox.ReplayAll()

    results = presubmit_canned_checks.CheckBuildbotPendingBuilds(
        input_api, presubmit.OutputApi, 'uurl', 2, ('foo'))
    self.assertEquals(len(results), 1)
    self.assertEquals(results[0].__class__,
        presubmit.OutputApi.PresubmitNotifyResult)

  def AssertOwnersWorks(self, tbr=False, issue='1', approvers=None,
      rietveld_response=None, host_url=None,
      uncovered_files=None, expected_output=''):
    if approvers is None:
      approvers = set()
    if uncovered_files is None:
      uncovered_files = set()

    change = self.mox.CreateMock(presubmit.Change)
    change.issue = issue
    affected_file = self.mox.CreateMock(presubmit.SvnAffectedFile)
    input_api = self.MockInputApi(change, False)
    fake_db = self.mox.CreateMock(owners.Database)
    fake_db.email_regexp = input_api.re.compile(owners.BASIC_EMAIL_REGEXP)
    input_api.owners_db = fake_db
    input_api.is_committing = True
    input_api.tbr = tbr

    if not tbr and issue:
      affected_file.LocalPath().AndReturn('foo.cc')
      change.AffectedFiles(None).AndReturn([affected_file])

      expected_host = 'http://localhost'
      if host_url:
        input_api.host_url = host_url
        if host_url.startswith('https'):
          expected_host = host_url

      owner_email = 'john@example.com'
      messages = list('{"sender": "' + a + '","text": "lgtm"}' for
                      a in approvers)
      if not rietveld_response:
        rietveld_response = ('{"owner_email": "' + owner_email + '",'
                            '"messages": [' + ','.join(messages) + ']}')
      input_api.urllib2.urlopen(
          expected_host + '/api/1?messages=true').AndReturn(
          StringIO.StringIO(rietveld_response))
      input_api.json = presubmit.json
      fake_db.files_not_covered_by(set(['foo.cc']),
         approvers.union(set([owner_email]))).AndReturn(uncovered_files)

    self.mox.ReplayAll()
    output = presubmit.PresubmitOutput()
    results = presubmit_canned_checks.CheckOwners(input_api,
        presubmit.OutputApi)
    if results:
      results[0].handle(output)
    self.assertEquals(output.getvalue(), expected_output)

  def testCannedCheckOwners_LGTMPhrases(self):
    def phrase_test(phrase, approvers=None, expected_output=''):
      if approvers is None:
        approvers = set(['ben@example.com'])
      self.AssertOwnersWorks(approvers=approvers,
          rietveld_response='{"owner_email": "john@example.com",' +
                            '"messages": [{"sender": "ben@example.com",' +
                                          '"text": "' + phrase + '"}]}',
          expected_output=expected_output)

    phrase_test('LGTM')
    phrase_test('\\nlgtm')
    phrase_test('> foo\\n> bar\\nlgtm\\n')
    phrase_test('> LGTM', approvers=set(),
                expected_output='Missing LGTM from someone other than '
                                'john@example.com\n')

    # TODO(dpranke): these probably should pass.
    phrase_test('Looks Good To Me', approvers=set(),
                expected_output='Missing LGTM from someone other than '
                                'john@example.com\n')
    phrase_test('looks good to me', approvers=set(),
                expected_output='Missing LGTM from someone other than '
                                'john@example.com\n')

    # TODO(dpranke): this probably shouldn't pass.
    phrase_test('no lgtm for you')

  def testCannedCheckOwners_HTTPS_HostURL(self):
    self.AssertOwnersWorks(approvers=set(['ben@example.com']),
                           host_url='https://localhost')

  def testCannedCheckOwners_MissingSchemeInHostURL(self):
    self.AssertOwnersWorks(approvers=set(['ben@example.com']),
                           host_url='localhost')

  def testCannedCheckOwners_NoIssue(self):
    self.AssertOwnersWorks(issue=None,
        expected_output="OWNERS check failed: this change has no Rietveld "
                        "issue number, so we can't check it for approvals.\n")

  def testCannedCheckOwners_NoLGTM(self):
    self.AssertOwnersWorks(expected_output='Missing LGTM from someone '
                                           'other than john@example.com\n')

  def testCannedCheckOwners_OnlyOwnerLGTM(self):
    self.AssertOwnersWorks(approvers=set(['john@example.com']),
                           expected_output='Missing LGTM from someone '
                                           'other than john@example.com\n')

  def testCannedCheckOwners_TBR(self):
    self.AssertOwnersWorks(tbr=True,
        expected_output='--tbr was specified, skipping OWNERS check\n')

  def testCannedCheckOwners_Upload(self):
    class FakeInputAPI(object):
      is_committing = False

    results = presubmit_canned_checks.CheckOwners(FakeInputAPI(),
                                                  presubmit.OutputApi)
    self.assertEqual(results, [])

  def testCannedCheckOwners_WithoutOwnerLGTM(self):
    self.AssertOwnersWorks(uncovered_files=set(['foo.cc']),
        expected_output='Missing LGTM from an OWNER for: foo.cc\n')

  def testCannedCheckOwners_WithLGTMs(self):
    self.AssertOwnersWorks(approvers=set(['ben@example.com']),
                           uncovered_files=set())



if __name__ == '__main__':
  import unittest
  unittest.main()
