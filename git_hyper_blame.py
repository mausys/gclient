#!/usr/bin/env python
# Copyright 2016 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Wrapper around git blame that ignores certain commits.
"""

from __future__ import print_function

import argparse
import collections
import logging
import os
import subprocess2
import sys

import git_common
import git_dates


logging.getLogger().setLevel(logging.INFO)


class Commit(object):
  """Info about a commit."""
  def __init__(self, commithash):
    self.commithash = commithash
    self.author = None
    self.author_mail = None
    self.author_time = None
    self.author_tz = None
    self.committer = None
    self.committer_mail = None
    self.committer_time = None
    self.committer_tz = None
    self.summary = None
    self.boundary = None
    self.previous = None
    self.filename = None

  def __repr__(self):  # pragma: no cover
    return '<Commit %s>' % self.commithash


BlameLine = collections.namedtuple(
    'BlameLine',
    'commit context lineno_then lineno_now modified')


def parse_blame(blameoutput):
  """Parses the output of git blame -p into a data structure."""
  lines = blameoutput.split('\n')
  i = 0
  commits = {}

  while i < len(lines):
    # Read a commit line and parse it.
    line = lines[i]
    i += 1
    if not line.strip():
      continue
    commitline = line.split()
    commithash = commitline[0]
    lineno_then = int(commitline[1])
    lineno_now = int(commitline[2])

    try:
      commit = commits[commithash]
    except KeyError:
      commit = Commit(commithash)
      commits[commithash] = commit

    # Read commit details until we find a context line.
    while i < len(lines):
      line = lines[i]
      i += 1
      if line.startswith('\t'):
        break

      try:
        key, value = line.split(' ', 1)
      except ValueError:
        key = line
        value = True
      setattr(commit, key.replace('-', '_'), value)

    context = line[1:]

    yield BlameLine(commit, context, lineno_then, lineno_now, False)


def print_table(table, colsep=' ', rowsep='\n', align=None, out=sys.stdout):
  """Print a 2D rectangular array, aligning columns with spaces.

  Args:
    align: Optional string of 'l' and 'r', designating whether each column is
           left- or right-aligned. Defaults to left aligned.
  """
  if len(table) == 0:
    return

  colwidths = None
  for row in table:
    if colwidths is None:
      colwidths = [len(x) for x in row]
    else:
      colwidths = [max(colwidths[i], len(x)) for i, x in enumerate(row)]

  if align is None:  # pragma: no cover
    align = 'l' * len(colwidths)

  for row in table:
    cells = []
    for i, cell in enumerate(row):
      padding = ' ' * (colwidths[i] - len(cell))
      if align[i] == 'r':
        cell = padding + cell
      elif i < len(row) - 1:
        # Do not pad the final column if left-aligned.
        cell += padding
      cells.append(cell)
    try:
      print(*cells, sep=colsep, end=rowsep, file=out)
    except IOError:  # pragma: no cover
      # Can happen on Windows if the pipe is closed early.
      pass


def pretty_print(parsedblame, show_filenames=False, out=sys.stdout):
  """Pretty-prints the output of parse_blame."""
  table = []
  for line in parsedblame:
    author_time = git_dates.timestamp_offset_to_datetime(
        line.commit.author_time, line.commit.author_tz)
    row = [line.commit.commithash[:8],
           '(' + line.commit.author,
           git_dates.datetime_string(author_time),
           str(line.lineno_now) + ('*' if line.modified else '') + ')',
           line.context]
    if show_filenames:
      row.insert(1, line.commit.filename)
    table.append(row)
  print_table(table, align='llllrl' if show_filenames else 'lllrl', out=out)


def get_parsed_blame(filename, revision='HEAD'):
  blame = git_common.blame(filename, revision=revision, porcelain=True)
  return list(parse_blame(blame))


def hyper_blame(ignored, filename, revision='HEAD', out=sys.stdout,
                err=sys.stderr):
  # Map from commit to parsed blame from that commit.
  blame_from = {}

  def cache_blame_from(filename, commithash):
    try:
      return blame_from[commithash]
    except KeyError:
      parsed = get_parsed_blame(filename, commithash)
      blame_from[commithash] = parsed
      return parsed

  try:
    parsed = cache_blame_from(filename, git_common.hash_one(revision))
  except subprocess2.CalledProcessError as e:
    err.write(e.stderr)
    return e.returncode

  new_parsed = []

  # We don't show filenames in blame output unless we have to.
  show_filenames = False

  for line in parsed:
    # If a line references an ignored commit, blame that commit's parent
    # repeatedly until we find a non-ignored commit.
    while line.commit.commithash in ignored:
      if line.commit.previous is None:
        # You can't ignore the commit that added this file.
        break

      previouscommit, previousfilename = line.commit.previous.split(' ', 1)
      parent_blame = cache_blame_from(previousfilename, previouscommit)

      if len(parent_blame) == 0:
        # The previous version of this file was empty, therefore, you can't
        # ignore this commit.
        break

      # line.lineno_then is the line number in question at line.commit.
      # TODO(mgiuca): This will be incorrect if line.commit added or removed
      # lines. Translate that line number so that it refers to the position of
      # the same line on previouscommit.
      lineno_previous = line.lineno_then
      logging.debug('ignore commit %s on line p%d/t%d/n%d',
                    line.commit.commithash, lineno_previous, line.lineno_then,
                    line.lineno_now)

      # Get the line at lineno_previous in the parent commit.
      assert lineno_previous > 0
      try:
        newline = parent_blame[lineno_previous - 1]
      except IndexError:
        # lineno_previous is a guess, so it may be past the end of the file.
        # Just grab the last line in the file.
        newline = parent_blame[-1]

      # Replace the commit and lineno_then, but not the lineno_now or context.
      logging.debug('    replacing with %r', newline)
      line = BlameLine(newline.commit, line.context, lineno_previous,
                       line.lineno_now, True)

    # If any line has a different filename to the file's current name, turn on
    # filename display for the entire blame output.
    if line.commit.filename != filename:
      show_filenames = True

    new_parsed.append(line)

  pretty_print(new_parsed, show_filenames=show_filenames, out=out)

  return 0

def main(args, stdout=sys.stdout, stderr=sys.stderr):
  parser = argparse.ArgumentParser(
      prog='git hyper-blame',
      description='git blame with support for ignoring certain commits.')
  parser.add_argument('-i', metavar='REVISION', action='append', dest='ignored',
                      default=[], help='a revision to ignore')
  parser.add_argument('revision', nargs='?', default='HEAD', metavar='REVISION',
                      help='revision to look at')
  parser.add_argument('filename', metavar='FILE', help='filename to blame')

  args = parser.parse_args(args)
  try:
    repo_root = git_common.repo_root()
  except subprocess2.CalledProcessError as e:
    stderr.write(e.stderr)
    return e.returncode

  # Make filename relative to the repository root, and cd to the root dir (so
  # all filenames throughout this script are relative to the root).
  filename = os.path.relpath(args.filename, repo_root)
  os.chdir(repo_root)

  # Normalize filename so we can compare it to other filenames git gives us.
  filename = os.path.normpath(filename)
  filename = os.path.normcase(filename)

  ignored = set()
  for c in args.ignored:
    try:
      ignored.add(git_common.hash_one(c))
    except subprocess2.CalledProcessError as e:
      # Custom error message (the message from git-rev-parse is inappropriate).
      stderr.write('fatal: unknown revision \'%s\'.\n' % c)
      return e.returncode

  return hyper_blame(ignored, filename, args.revision, out=stdout, err=stderr)


if __name__ == '__main__':  # pragma: no cover
  with git_common.less() as less_input:
    sys.exit(main(sys.argv[1:], stdout=less_input))
