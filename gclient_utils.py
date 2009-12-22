# Copyright 2009 Google Inc.  All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Generic utils."""

import errno
import os
import re
import stat
import subprocess
import sys
import time
import xml.dom.minidom
import xml.parsers.expat


class CheckCallError(OSError):
  """CheckCall() returned non-0."""
  def __init__(self, command, cwd, retcode, stdout):
    OSError.__init__(self, command, cwd, retcode, stdout)
    self.command = command
    self.cwd = cwd
    self.retcode = retcode
    self.stdout = stdout


def CheckCall(command, cwd=None, print_error=True):
  """Like subprocess.check_call() but returns stdout.

  Works on python 2.4
  """
  try:
    stderr = None
    if not print_error:
      stderr = subprocess.PIPE
    process = subprocess.Popen(command, cwd=cwd,
                               shell=sys.platform.startswith('win'),
                               stdout=subprocess.PIPE,
                               stderr=stderr)
    output = process.communicate()[0]
  except OSError, e:
    raise CheckCallError(command, cwd, errno, None)
  if process.returncode:
    raise CheckCallError(command, cwd, process.returncode, output)
  return output


def SplitUrlRevision(url):
  """Splits url and returns a two-tuple: url, rev"""
  if url.startswith('ssh:'):
    # Make sure ssh://test@example.com/test.git@stable works
    regex = r"(ssh://(?:[\w]+@)?[-\w:\.]+/[-\w\./]+)(?:@(.+))?"
    components = re.search(regex, url).groups()
  else:
    components = url.split("@")
    if len(components) == 1:
      components += [None]
  return tuple(components)


def FullUrlFromRelative(base_url, url):
  # Find the forth '/' and strip from there. A bit hackish.
  return '/'.join(base_url.split('/')[:4]) + url


def FullUrlFromRelative2(base_url, url):
  # Strip from last '/'
  # Equivalent to unix basename
  return base_url[:base_url.rfind('/')] + url


def ParseXML(output):
  try:
    return xml.dom.minidom.parseString(output)
  except xml.parsers.expat.ExpatError:
    return None


def GetNamedNodeText(node, node_name):
  child_nodes = node.getElementsByTagName(node_name)
  if not child_nodes:
    return None
  assert len(child_nodes) == 1 and child_nodes[0].childNodes.length == 1
  return child_nodes[0].firstChild.nodeValue


def GetNodeNamedAttributeText(node, node_name, attribute_name):
  child_nodes = node.getElementsByTagName(node_name)
  if not child_nodes:
    return None
  assert len(child_nodes) == 1
  return child_nodes[0].getAttribute(attribute_name)


class Error(Exception):
  """gclient exception class."""
  pass


class PrintableObject(object):
  def __str__(self):
    output = ''
    for i in dir(self):
      if i.startswith('__'):
        continue
      output += '%s = %s\n' % (i, str(getattr(self, i, '')))
    return output


def FileRead(filename, mode='rU'):
  content = None
  f = open(filename, mode)
  try:
    content = f.read()
  finally:
    f.close()
  return content


def FileWrite(filename, content, mode='w'):
  f = open(filename, mode)
  try:
    f.write(content)
  finally:
    f.close()


def RemoveDirectory(*path):
  """Recursively removes a directory, even if it's marked read-only.

  Remove the directory located at *path, if it exists.

  shutil.rmtree() doesn't work on Windows if any of the files or directories
  are read-only, which svn repositories and some .svn files are.  We need to
  be able to force the files to be writable (i.e., deletable) as we traverse
  the tree.

  Even with all this, Windows still sometimes fails to delete a file, citing
  a permission error (maybe something to do with antivirus scans or disk
  indexing).  The best suggestion any of the user forums had was to wait a
  bit and try again, so we do that too.  It's hand-waving, but sometimes it
  works. :/

  On POSIX systems, things are a little bit simpler.  The modes of the files
  to be deleted doesn't matter, only the modes of the directories containing
  them are significant.  As the directory tree is traversed, each directory
  has its mode set appropriately before descending into it.  This should
  result in the entire tree being removed, with the possible exception of
  *path itself, because nothing attempts to change the mode of its parent.
  Doing so would be hazardous, as it's not a directory slated for removal.
  In the ordinary case, this is not a problem: for our purposes, the user
  will never lack write permission on *path's parent.
  """
  file_path = os.path.join(*path)
  if not os.path.exists(file_path):
    return

  if os.path.islink(file_path) or not os.path.isdir(file_path):
    raise Error("RemoveDirectory asked to remove non-directory %s" % file_path)

  has_win32api = False
  if sys.platform == 'win32':
    has_win32api = True
    # Some people don't have the APIs installed. In that case we'll do without.
    try:
      win32api = __import__('win32api')
      win32con = __import__('win32con')
    except ImportError:
      has_win32api = False
  else:
    # On POSIX systems, we need the x-bit set on the directory to access it,
    # the r-bit to see its contents, and the w-bit to remove files from it.
    # The actual modes of the files within the directory is irrelevant.
    os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
  for fn in os.listdir(file_path):
    fullpath = os.path.join(file_path, fn)

    # If fullpath is a symbolic link that points to a directory, isdir will
    # be True, but we don't want to descend into that as a directory, we just
    # want to remove the link.  Check islink and treat links as ordinary files
    # would be treated regardless of what they reference.
    if os.path.islink(fullpath) or not os.path.isdir(fullpath):
      if sys.platform == 'win32':
        os.chmod(fullpath, stat.S_IWRITE)
        if has_win32api:
          win32api.SetFileAttributes(fullpath, win32con.FILE_ATTRIBUTE_NORMAL)
      try:
        os.remove(fullpath)
      except OSError, e:
        if e.errno != errno.EACCES or sys.platform != 'win32':
          raise
        print 'Failed to delete %s: trying again' % fullpath
        time.sleep(0.1)
        os.remove(fullpath)
    else:
      RemoveDirectory(fullpath)

  if sys.platform == 'win32':
    os.chmod(file_path, stat.S_IWRITE)
    if has_win32api:
      win32api.SetFileAttributes(file_path, win32con.FILE_ATTRIBUTE_NORMAL)
  try:
    os.rmdir(file_path)
  except OSError, e:
    if e.errno != errno.EACCES or sys.platform != 'win32':
      raise
    print 'Failed to remove %s: trying again' % file_path
    time.sleep(0.1)
    os.rmdir(file_path)


def SubprocessCall(command, in_directory, fail_status=None):
  """Runs command, a list, in directory in_directory.

  This function wraps SubprocessCallAndFilter, but does not perform the
  filtering functions.  See that function for a more complete usage
  description.
  """
  # Call subprocess and capture nothing:
  SubprocessCallAndFilter(command, in_directory, True, True, fail_status)


def SubprocessCallAndFilter(command,
                            in_directory,
                            print_messages,
                            print_stdout,
                            fail_status=None, filter=None):
  """Runs command, a list, in directory in_directory.

  If print_messages is true, a message indicating what is being done
  is printed to stdout. If print_messages is false, the message is printed
  only if we actually need to print something else as well, so you can
  get the context of the output. If print_messages is false and print_stdout
  is false, no output at all is generated.

  Also, if print_stdout is true, the command's stdout is also forwarded
  to stdout.

  If a filter function is specified, it is expected to take a single
  string argument, and it will be called with each line of the
  subprocess's output. Each line has had the trailing newline character
  trimmed.

  If the command fails, as indicated by a nonzero exit status, gclient will
  exit with an exit status of fail_status.  If fail_status is None (the
  default), gclient will raise an Error exception.
  """

  if print_messages:
    print("\n________ running \'%s\' in \'%s\'"
          % (' '.join(command), in_directory))

  # *Sigh*:  Windows needs shell=True, or else it won't search %PATH% for the
  # executable, but shell=True makes subprocess on Linux fail when it's called
  # with a list because it only tries to execute the first item in the list.
  kid = subprocess.Popen(command, bufsize=0, cwd=in_directory,
      shell=(sys.platform == 'win32'), stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT)

  # Also, we need to forward stdout to prevent weird re-ordering of output.
  # This has to be done on a per byte basis to make sure it is not buffered:
  # normally buffering is done for each line, but if svn requests input, no
  # end-of-line character is output after the prompt and it would not show up.
  in_byte = kid.stdout.read(1)
  in_line = ""
  while in_byte:
    if in_byte != "\r":
      if print_stdout:
        if not print_messages:
          print("\n________ running \'%s\' in \'%s\'"
              % (' '.join(command), in_directory))
          print_messages = True
        sys.stdout.write(in_byte)
      if in_byte != "\n":
        in_line += in_byte
    if in_byte == "\n" and filter:
      filter(in_line)
      in_line = ""
    in_byte = kid.stdout.read(1)
  rv = kid.wait()

  if rv:
    msg = "failed to run command: %s" % " ".join(command)

    if fail_status != None:
      print >>sys.stderr, msg
      sys.exit(fail_status)

    raise Error(msg)


def IsUsingGit(root, paths):
  """Returns True if we're using git to manage any of our checkouts.
  |entries| is a list of paths to check."""
  for path in paths:
    if os.path.exists(os.path.join(root, path, '.git')):
      return True
  return False

def FindGclientRoot(from_dir):
  """Tries to find the gclient root."""
  path = os.path.realpath(from_dir)
  while not os.path.exists(os.path.join(path, '.gclient')):
    next = os.path.split(path)
    if not next[1]:
      return None
    path = next[0]
  return path

def PathDifference(root, subpath):
  """Returns the difference subpath minus root."""
  root = os.path.realpath(root)
  subpath = os.path.realpath(subpath)
  if not subpath.startswith(root):
    return None
  # If the root does not have a trailing \ or /, we add it so the returned
  # path starts immediately after the seperator regardless of whether it is
  # provided.
  root = os.path.join(root, '')
  return subpath[len(root):]
