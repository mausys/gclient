# Copyright (c) 2012 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A database of OWNERS files.

OWNERS files indicate who is allowed to approve changes in a specific directory
(or who is allowed to make changes without needing approval of another OWNER).
Note that all changes must still be reviewed by someone familiar with the code,
so you may need approval from both an OWNER and a reviewer in many cases.

The syntax of the OWNERS file is, roughly:

lines     := (\s* line? \s* "\n")*

line      := directive
          | "per-file" \s+ glob "=" directive
          | comment

directive := "set noparent"
          |  email_address
          |  "*"

glob      := [a-zA-Z0-9_-*?]+

comment   := "#" [^"\n"]*

Email addresses must follow the foo@bar.com short form (exact syntax given
in BASIC_EMAIL_REGEXP, below). Filename globs follow the simple unix
shell conventions, and relative and absolute paths are not allowed (i.e.,
globs only refer to the files in the current directory).

If a user's email is one of the email_addresses in the file, the user is
considered an "OWNER" for all files in the directory.

If the "per-file" directive is used, the line only applies to files in that
directory that match the filename glob specified.

If the "set noparent" directive used, then only entries in this OWNERS file
apply to files in this directory; if the "set noparent" directive is not
used, then entries in OWNERS files in enclosing (upper) directories also
apply (up until a "set noparent is encountered").

If "per-file glob=set noparent" is used, then global directives are ignored
for the glob, and only the "per-file" owners are used for files matching that
glob.

Examples for all of these combinations can be found in tests/owners_unittest.py.
"""

import collections
import re


# If this is present by itself on a line, this means that everyone can review.
EVERYONE = '*'


# Recognizes 'X@Y' email addresses. Very simplistic.
BASIC_EMAIL_REGEXP = r'^[\w\-\+\%\.]+\@[\w\-\+\%\.]+$'


def _assert_is_collection(obj):
  assert not isinstance(obj, basestring)
  # Module 'collections' has no 'Iterable' member
  # pylint: disable=E1101
  if hasattr(collections, 'Iterable') and hasattr(collections, 'Sized'):
    assert (isinstance(obj, collections.Iterable) and
            isinstance(obj, collections.Sized))


class SyntaxErrorInOwnersFile(Exception):
  def __init__(self, path, lineno, msg):
    super(SyntaxErrorInOwnersFile, self).__init__((path, lineno, msg))
    self.path = path
    self.lineno = lineno
    self.msg = msg

  def __str__(self):
    return "%s:%d syntax error: %s" % (self.path, self.lineno, self.msg)


class Database(object):
  """A database of OWNERS files for a repository.

  This class allows you to find a suggested set of reviewers for a list
  of changed files, and see if a list of changed files is covered by a
  list of reviewers."""

  def __init__(self, root, fopen, os_path, glob):
    """Args:
      root: the path to the root of the Repository
      open: function callback to open a text file for reading
      os_path: module/object callback with fields for 'abspath', 'dirname',
          'exists', and 'join'
      glob: function callback to list entries in a directory match a glob
          (i.e., glob.glob)
    """
    self.root = root
    self.fopen = fopen
    self.os_path = os_path
    self.glob = glob

    # Pick a default email regexp to use; callers can override as desired.
    self.email_regexp = re.compile(BASIC_EMAIL_REGEXP)

    # Mapping of owners to the paths they own.
    self.owned_by = {EVERYONE: set()}

    # Mapping of paths to authorized owners.
    self.owners_for = {}

    # Set of paths that stop us from looking above them for owners.
    # (This is implicitly true for the root directory).
    self.stop_looking = set([''])

  def reviewers_for(self, files):
    """Returns a suggested set of reviewers that will cover the files.

    files is a sequence of paths relative to (and under) self.root."""
    self._check_paths(files)
    self._load_data_needed_for(files)
    return self._covering_set_of_owners_for(files)

  # TODO(dpranke): rename to objects_not_covered_by
  def directories_not_covered_by(self, files, reviewers):
    """Returns the set of directories that are not owned by a reviewer.

    Determines which of the given files are not owned by at least one of the
    reviewers, then returns a set containing the applicable enclosing
    directories, i.e. the ones upward from the files that have OWNERS files.

    Args:
        files is a sequence of paths relative to (and under) self.root.
        reviewers is a sequence of strings matching self.email_regexp.
    """
    self._check_paths(files)
    self._check_reviewers(reviewers)
    self._load_data_needed_for(files)

    objs = set()
    for f in files:
      if f in self.owners_for:
        objs.add(f)
      else:
        objs.add(self.os_path.dirname(f))

    covered_objs = self._objs_covered_by(reviewers)
    uncovered_objs = [self._enclosing_obj_with_owners(o) for o in objs
                      if not self._is_obj_covered_by(o, covered_objs)]

    return set(uncovered_objs)

  objects_not_covered_by = directories_not_covered_by

  def _check_paths(self, files):
    def _is_under(f, pfx):
      return self.os_path.abspath(self.os_path.join(pfx, f)).startswith(pfx)
    _assert_is_collection(files)
    assert all(_is_under(f, self.os_path.abspath(self.root)) for f in files)

  def _check_reviewers(self, reviewers):
    _assert_is_collection(reviewers)
    assert all(self.email_regexp.match(r) for r in reviewers)

  # TODO(dpranke): Rename to _objs_covered_by and update_callers
  def _dirs_covered_by(self, reviewers):
    dirs = self.owned_by[EVERYONE]
    for r in reviewers:
      dirs = dirs | self.owned_by.get(r, set())
    return dirs

  _objs_covered_by = _dirs_covered_by

  def _stop_looking(self, dirname):
    return dirname in self.stop_looking

  # TODO(dpranke): Rename to _is_dir_covered_by and update callers.
  def _is_dir_covered_by(self, dirname, covered_dirs):
    while not dirname in covered_dirs and not self._stop_looking(dirname):
      dirname = self.os_path.dirname(dirname)
    return dirname in covered_dirs

  _is_obj_covered_by = _is_dir_covered_by

  # TODO(dpranke): Rename to _enclosing_obj_with_owners and update callers.
  def _enclosing_dir_with_owners(self, directory):
    """Returns the innermost enclosing directory that has an OWNERS file."""
    dirpath = directory
    while not dirpath in self.owners_for:
      if self._stop_looking(dirpath):
        break
      dirpath = self.os_path.dirname(dirpath)
    return dirpath

  _enclosing_obj_with_owners = _enclosing_dir_with_owners

  def _load_data_needed_for(self, files):
    for f in files:
      dirpath = self.os_path.dirname(f)
      while not dirpath in self.owners_for:
        self._read_owners_in_dir(dirpath)
        if self._stop_looking(dirpath):
          break
        dirpath = self.os_path.dirname(dirpath)

  def _read_owners_in_dir(self, dirpath):
    owners_path = self.os_path.join(self.root, dirpath, 'OWNERS')
    if not self.os_path.exists(owners_path):
      return

    lineno = 0
    for line in self.fopen(owners_path):
      lineno += 1
      line = line.strip()
      if line.startswith('#') or line == '':
        continue
      if line == 'set noparent':
        self.stop_looking.add(dirpath)
        continue

      m = re.match("per-file (.+)=(.+)", line)
      if m:
        glob_string = m.group(1)
        directive = m.group(2)
        full_glob_string = self.os_path.join(self.root, dirpath, glob_string)
        if '/' in glob_string or '\\' in glob_string:
          raise SyntaxErrorInOwnersFile(owners_path, lineno,
              'per-file globs cannot span directories or use escapes: "%s"' %
              line)
        baselines = self.glob(full_glob_string)
        for baseline in (self.os_path.relpath(b, self.root) for b in baselines):
          self._add_entry(baseline, directive, "per-file line",
                          owners_path, lineno)
        continue

      if line.startswith('set '):
        raise SyntaxErrorInOwnersFile(owners_path, lineno,
            'unknown option: "%s"' % line[4:].strip())

      self._add_entry(dirpath, line, "line", owners_path, lineno)

  def _add_entry(self, path, directive, line_type, owners_path, lineno):
    if directive == "set noparent":
      self.stop_looking.add(path)
    elif self.email_regexp.match(directive) or directive == EVERYONE:
      self.owned_by.setdefault(directive, set()).add(path)
      self.owners_for.setdefault(path, set()).add(directive)
    else:
      raise SyntaxErrorInOwnersFile(owners_path, lineno,
          ('%s is not a "set" directive, "*", '
           'or an email address: "%s"' % (line_type, directive)))


  def _covering_set_of_owners_for(self, files):
    # Get the set of directories from the files.
    dirs = set()
    for f in files:
      dirs.add(self.os_path.dirname(f))

    owned_dirs = {}
    dir_owners = {}

    for current_dir in dirs:
      # Get the list of owners for each directory.
      current_owners = set()
      dirname = current_dir
      while dirname in self.owners_for:
        current_owners |= self.owners_for[dirname]
        if self._stop_looking(dirname):
          break
        prev_parent = dirname
        dirname = self.os_path.dirname(dirname)
        if prev_parent == dirname:
          break

      # Map each directory to a list of its owners.
      dir_owners[current_dir] = current_owners

      # Add the directory to the list of each owner.
      for owner in current_owners:
        owned_dirs.setdefault(owner, set()).add(current_dir)

    final_owners = set()
    while dirs:
      # Find the owner that has the most directories.
      max_count = 0
      max_owner = None
      owner_count = {}
      for dirname in dirs:
        for owner in dir_owners[dirname]:
          count = owner_count.get(owner, 0) + 1
          owner_count[owner] = count
          if count >= max_count:
            max_owner = owner
            max_count = count

      # If no more directories have OWNERS, we're done.
      if not max_owner:
        break

      final_owners.add(max_owner)

      # Remove all directories owned by the current owner from the remaining
      # list.
      for dirname in owned_dirs[max_owner]:
        dirs.discard(dirname)

    return final_owners
