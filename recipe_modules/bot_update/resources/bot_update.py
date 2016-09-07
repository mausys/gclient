#!/usr/bin/env python
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# TODO(hinoka): Use logging.

import cStringIO
import codecs
import collections
import copy
import ctypes
import json
import optparse
import os
import pprint
import random
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib2
import urlparse
import uuid

import os.path as path

# How many bytes at a time to read from pipes.
BUF_SIZE = 256


# TODO(luqui): This is a horrible hack to identify build_internal when build
# is a recipe dependency.  bot_update should not be depending on internal,
# rather the arrow should go the other way (or just be destroyed).
def check_dir(name, dirs, default=None):
  for d in dirs:
    d = path.abspath(d)
    if path.basename(d) == name and path.isdir(d):
      return d
  return default


# Define a bunch of directory paths.
# Relative to the current working directory.
CURRENT_DIR = path.abspath(os.getcwd())
BUILDER_DIR = path.dirname(CURRENT_DIR)
SLAVE_DIR = path.dirname(BUILDER_DIR)

# Relative to this script's filesystem path.
THIS_DIR = path.dirname(path.abspath(__file__))
SCRIPTS_DIR = check_dir(
    'scripts', [
        path.dirname(THIS_DIR),
        path.join(SLAVE_DIR, '..', 'scripts'),
        path.join(THIS_DIR,  # resources
                  '..',      # bot_update
                  '..',      # recipe_modules
                  '..',      # depot_tools
                  '..',      # .recipe_deps
                  '..',      # slave
                  '..',      # scripts
                  '..',      # build_internal
                  '..',      # ROOT_DIR
                  'build',
                  'scripts'),
        path.join(SLAVE_DIR, '..', 'build', 'scripts'),
    ], default=path.dirname(THIS_DIR))
BUILD_DIR = path.dirname(SCRIPTS_DIR)
ROOT_DIR = path.dirname(BUILD_DIR)

DEPOT_TOOLS_DIR = path.abspath(path.join(THIS_DIR, '..', '..', '..'))

BUILD_INTERNAL_DIR = check_dir(
    'build_internal', [
        path.join(ROOT_DIR, 'build_internal'),
        path.join(ROOT_DIR,      # .recipe_deps
                  path.pardir,   # slave
                  path.pardir,   # scripts
                  path.pardir),  # build_internal
    ])


CHROMIUM_GIT_HOST = 'https://chromium.googlesource.com'
CHROMIUM_SRC_URL = CHROMIUM_GIT_HOST + '/chromium/src.git'

BRANCH_HEADS_REFSPEC = '+refs/branch-heads/*'

BUILDSPEC_COMMIT_RE = (
    re.compile(r'Buildspec for.*version (\d+\.\d+\.\d+\.\d+)'),
    re.compile(r'Create (\d+\.\d+\.\d+\.\d+) buildspec'),
    re.compile(r'Auto-converted (\d+\.\d+\.\d+\.\d+) buildspec to git'),
)

# Regular expression that matches a single commit footer line.
COMMIT_FOOTER_ENTRY_RE = re.compile(r'([^:]+):\s+(.+)')

# Footer metadata keys for regular and gsubtreed mirrored commit positions.
COMMIT_POSITION_FOOTER_KEY = 'Cr-Commit-Position'
COMMIT_ORIGINAL_POSITION_FOOTER_KEY = 'Cr-Original-Commit-Position'
# Regular expression to parse a commit position
COMMIT_POSITION_RE = re.compile(r'(.+)@\{#(\d+)\}')

# Regular expression to parse gclient's revinfo entries.
REVINFO_RE = re.compile(r'^([^:]+):\s+([^@]+)@(.+)$')


# Copied from scripts/recipes/chromium.py.
GOT_REVISION_MAPPINGS = {
    CHROMIUM_SRC_URL: {
        'src/': 'got_revision',
        'src/native_client/': 'got_nacl_revision',
        'src/tools/swarm_client/': 'got_swarm_client_revision',
        'src/tools/swarming_client/': 'got_swarming_client_revision',
        'src/third_party/WebKit/': 'got_webkit_revision',
        'src/third_party/webrtc/': 'got_webrtc_revision',
        'src/v8/': 'got_v8_revision',
    }
}


BOT_UPDATE_MESSAGE = """
What is the "Bot Update" step?
==============================

This step ensures that the source checkout on the bot (e.g. Chromium's src/ and
its dependencies) is checked out in a consistent state. This means that all of
the necessary repositories are checked out, no extra repositories are checked
out, and no locally modified files are present.

These actions used to be taken care of by the "gclient revert" and "update"
steps. However, those steps are known to be buggy and occasionally flaky. This
step has two main advantages over them:
  * it only operates in Git, so the logic can be clearer and cleaner; and
  * it is a slave-side script, so its behavior can be modified without
    restarting the master.

Debugging information:
(master/builder/slave may be unspecified on recipes)
master: %(master)s
builder: %(builder)s
slave: %(slave)s
forced by recipes: %(recipe)s
CURRENT_DIR: %(CURRENT_DIR)s
BUILDER_DIR: %(BUILDER_DIR)s
SLAVE_DIR: %(SLAVE_DIR)s
THIS_DIR: %(THIS_DIR)s
SCRIPTS_DIR: %(SCRIPTS_DIR)s
BUILD_DIR: %(BUILD_DIR)s
ROOT_DIR: %(ROOT_DIR)s
DEPOT_TOOLS_DIR: %(DEPOT_TOOLS_DIR)s
bot_update.py is:"""

ACTIVATED_MESSAGE = """ACTIVE.
The bot will perform a Git checkout in this step.
The "gclient revert" and "update" steps are no-ops.

"""

NOT_ACTIVATED_MESSAGE = """INACTIVE.
This step does nothing. You actually want to look at the "update" step.

"""


GCLIENT_TEMPLATE = """solutions = %(solutions)s

cache_dir = r%(cache_dir)s
%(target_os)s
%(target_os_only)s
"""


internal_data = {}
if BUILD_INTERNAL_DIR:
  local_vars = {}
  try:
    execfile(os.path.join(
        BUILD_INTERNAL_DIR, 'scripts', 'slave', 'bot_update_cfg.py'),
        local_vars)
  except Exception:
    # Same as if BUILD_INTERNAL_DIR didn't exist in the first place.
    print 'Warning: unable to read internal configuration file.'
    print 'If this is an internal bot, this step may be erroneously inactive.'
  internal_data = local_vars


ENABLED_MASTERS = [
    'bot_update.always_on',
    'chromium.android',
    'chromium.angle',
    'chromium.chrome',
    'chromium.chromedriver',
    'chromium.chromiumos',
    'chromium',
    'chromium.fyi',
    'chromium.goma',
    'chromium.gpu',
    'chromium.gpu.fyi',
    'chromium.infra',
    'chromium.infra.cron',
    'chromium.linux',
    'chromium.lkgr',
    'chromium.mac',
    'chromium.memory',
    'chromium.memory.fyi',
    'chromium.perf',
    'chromium.perf.fyi',
    'chromium.swarm',
    'chromium.webkit',
    'chromium.webrtc',
    'chromium.webrtc.fyi',
    'chromium.win',
    'client.catapult',
    'client.drmemory',
    'client.mojo',
    'client.nacl',
    'client.nacl.ports',
    'client.nacl.sdk',
    'client.nacl.toolchain',
    'client.pdfium',
    'client.skia',
    'client.skia.fyi',
    'client.v8',
    'client.v8.branches',
    'client.v8.fyi',
    'client.v8.ports',
    'client.webrtc',
    'client.webrtc.fyi',
    'tryserver.blink',
    'tryserver.client.catapult',
    'tryserver.client.mojo',
    'tryserver.chromium.android',
    'tryserver.chromium.angle',
    'tryserver.chromium.linux',
    'tryserver.chromium.mac',
    'tryserver.chromium.perf',
    'tryserver.chromium.win',
    'tryserver.infra',
    'tryserver.nacl',
    'tryserver.v8',
    'tryserver.webrtc',
]
ENABLED_MASTERS += internal_data.get('ENABLED_MASTERS', [])

ENABLED_BUILDERS = {
    'client.dart.fyi': [
        'v8-linux-release',
        'v8-mac-release',
        'v8-win-release',
    ],
    'client.dynamorio': [
        'linux-v8-dr',
    ],
}
ENABLED_BUILDERS.update(internal_data.get('ENABLED_BUILDERS', {}))

ENABLED_SLAVES = {}
ENABLED_SLAVES.update(internal_data.get('ENABLED_SLAVES', {}))

# Disabled filters get run AFTER enabled filters, so for example if a builder
# config is enabled, but a bot on that builder is disabled, that bot will
# be disabled.
DISABLED_BUILDERS = {}
DISABLED_BUILDERS.update(internal_data.get('DISABLED_BUILDERS', {}))

DISABLED_SLAVES = {}
DISABLED_SLAVES.update(internal_data.get('DISABLED_SLAVES', {}))

# How many times to try before giving up.
ATTEMPTS = 5

GIT_CACHE_PATH = path.join(DEPOT_TOOLS_DIR, 'git_cache.py')

# Find the patch tool.
if sys.platform.startswith('win'):
  if not BUILD_INTERNAL_DIR:
    print 'Warning: could not find patch tool because there is no '
    print 'build_internal present.'
    PATCH_TOOL = None
  else:
    PATCH_TOOL = path.join(BUILD_INTERNAL_DIR, 'tools', 'patch.EXE')
else:
  PATCH_TOOL = '/usr/bin/patch'

# If there is less than 100GB of disk space on the system, then we do
# a shallow checkout.
SHALLOW_CLONE_THRESHOLD = 100 * 1024 * 1024 * 1024


class SubprocessFailed(Exception):
  def __init__(self, message, code, output):
    Exception.__init__(self, message)
    self.code = code
    self.output = output


class PatchFailed(SubprocessFailed):
  pass


class GclientSyncFailed(SubprocessFailed):
  pass


class InvalidDiff(Exception):
  pass


RETRY = object()
OK = object()
FAIL = object()


class PsPrinter(object):
  def __init__(self, interval=300):
    self.interval = interval
    self.active = sys.platform.startswith('linux2')
    self.thread = None

  @staticmethod
  def print_pstree():
    """Debugging function used to print "ps auxwwf" for stuck processes."""
    subprocess.call(['ps', 'auxwwf'])

  def poke(self):
    if self.active:
      self.cancel()
      self.thread = threading.Timer(self.interval, self.print_pstree)
      self.thread.start()

  def cancel(self):
    if self.active and self.thread is not None:
      self.thread.cancel()
      self.thread = None


def call(*args, **kwargs):  # pragma: no cover
  """Interactive subprocess call."""
  kwargs['stdout'] = subprocess.PIPE
  kwargs['stderr'] = subprocess.STDOUT
  kwargs.setdefault('bufsize', BUF_SIZE)
  cwd = kwargs.get('cwd', os.getcwd())
  result_fn = kwargs.pop('result_fn', lambda code, out: RETRY if code else OK)
  stdin_data = kwargs.pop('stdin_data', None)
  tries = kwargs.pop('tries', ATTEMPTS)
  if stdin_data:
    kwargs['stdin'] = subprocess.PIPE
  out = cStringIO.StringIO()
  new_env = kwargs.get('env', {})
  env = copy.copy(os.environ)
  env.update(new_env)
  kwargs['env'] = env
  attempt = 0
  for attempt in range(1, tries + 1):
    attempt_msg = ' (attempt #%d)' % attempt if attempt else ''
    if new_env:
      print '===Injecting Environment Variables==='
      for k, v in sorted(new_env.items()):
        print '%s: %s' % (k, v)
    print '===Running %s%s===' % (' '.join(args), attempt_msg)
    print 'In directory: %s' % cwd
    start_time = time.time()
    proc = subprocess.Popen(args, **kwargs)
    if stdin_data:
      proc.stdin.write(stdin_data)
      proc.stdin.close()
    psprinter = PsPrinter()
    # This is here because passing 'sys.stdout' into stdout for proc will
    # produce out of order output.
    hanging_cr = False
    while True:
      psprinter.poke()
      buf = proc.stdout.read(BUF_SIZE)
      if not buf:
        break
      if hanging_cr:
        buf = '\r' + buf
      hanging_cr = buf.endswith('\r')
      if hanging_cr:
        buf = buf[:-1]
      buf = buf.replace('\r\n', '\n').replace('\r', '\n')
      sys.stdout.write(buf)
      out.write(buf)
    if hanging_cr:
      sys.stdout.write('\n')
      out.write('\n')
    psprinter.cancel()

    code = proc.wait()
    elapsed_time = ((time.time() - start_time) / 60.0)
    outval = out.getvalue()
    result = result_fn(code, outval)
    if result in (FAIL, RETRY):
      print '===Failed in %.1f mins===' % elapsed_time
      print
    else:
      print '===Succeeded in %.1f mins===' % elapsed_time
      print
      return outval
    if result is FAIL:
      break
    if result is RETRY and attempt < tries:
      sleep_backoff = 4 ** attempt
      sleep_time = random.randint(sleep_backoff, int(sleep_backoff * 1.2))
      print '===backing off, sleeping for %d secs===' % sleep_time
      time.sleep(sleep_time)

  raise SubprocessFailed('%s failed with code %d in %s after %d attempts.' %
                         (' '.join(args), code, cwd, attempt),
                         code, outval)


def git(*args, **kwargs):  # pragma: no cover
  """Wrapper around call specifically for Git commands."""
  if args and args[0] == 'cache':
    # Rewrite "git cache" calls into "python git_cache.py".
    cmd = (sys.executable, '-u', GIT_CACHE_PATH) + args[1:]
  else:
    git_executable = 'git'
    # On windows, subprocess doesn't fuzzy-match 'git' to 'git.bat', so we
    # have to do it explicitly. This is better than passing shell=True.
    if sys.platform.startswith('win'):
      git_executable += '.bat'
    cmd = (git_executable,) + args
  return call(*cmd, **kwargs)


def get_gclient_spec(solutions, target_os, target_os_only, git_cache_dir):
  return GCLIENT_TEMPLATE % {
      'solutions': pprint.pformat(solutions, indent=4),
      'cache_dir': '"%s"' % git_cache_dir,
      'target_os': ('\ntarget_os=%s' % target_os) if target_os else '',
      'target_os_only': '\ntarget_os_only=%s' % target_os_only
  }


def check_enabled(master, builder, slave):
  if master in ENABLED_MASTERS:
    return True
  builder_list = ENABLED_BUILDERS.get(master)
  if builder_list and builder in builder_list:
    return True
  slave_list = ENABLED_SLAVES.get(master)
  if slave_list and slave in slave_list:
    return True
  return False


def check_disabled(master, builder, slave):
  """Returns True if disabled, False if not disabled."""
  builder_list = DISABLED_BUILDERS.get(master)
  if builder_list and builder in builder_list:
    return True
  slave_list = DISABLED_SLAVES.get(master)
  if slave_list and slave in slave_list:
    return True
  return False


def check_valid_host(master, builder, slave):
  return (check_enabled(master, builder, slave)
          and not check_disabled(master, builder, slave))


def solutions_printer(solutions):
  """Prints gclient solution to stdout."""
  print 'Gclient Solutions'
  print '================='
  for solution in solutions:
    name = solution.get('name')
    url = solution.get('url')
    print '%s (%s)' % (name, url)
    if solution.get('deps_file'):
      print '  Dependencies file is %s' % solution['deps_file']
    if 'managed' in solution:
      print '  Managed mode is %s' % ('ON' if solution['managed'] else 'OFF')
    custom_vars = solution.get('custom_vars')
    if custom_vars:
      print '  Custom Variables:'
      for var_name, var_value in sorted(custom_vars.iteritems()):
        print '    %s = %s' % (var_name, var_value)
    custom_deps = solution.get('custom_deps')
    if 'custom_deps' in solution:
      print '  Custom Dependencies:'
      for deps_name, deps_value in sorted(custom_deps.iteritems()):
        if deps_value:
          print '    %s -> %s' % (deps_name, deps_value)
        else:
          print '    %s: Ignore' % deps_name
    for k, v in solution.iteritems():
      # Print out all the keys we don't know about.
      if k in ['name', 'url', 'deps_file', 'custom_vars', 'custom_deps',
               'managed']:
        continue
      print '  %s is %s' % (k, v)
    print


def modify_solutions(input_solutions):
  """Modifies urls in solutions to point at Git repos.

  returns: new solution dictionary
  """
  assert input_solutions
  solutions = copy.deepcopy(input_solutions)
  for solution in solutions:
    original_url = solution['url']
    parsed_url = urlparse.urlparse(original_url)
    parsed_path = parsed_url.path

    solution['managed'] = False
    # We don't want gclient to be using a safesync URL. Instead it should
    # using the lkgr/lkcr branch/tags.
    if 'safesync_url' in solution:
      print 'Removing safesync url %s from %s' % (solution['safesync_url'],
                                                  parsed_path)
      del solution['safesync_url']

  return solutions


def remove(target):
  """Remove a target by moving it into build.dead."""
  dead_folder = path.join(BUILDER_DIR, 'build.dead')
  if not path.exists(dead_folder):
    os.makedirs(dead_folder)
  os.rename(target, path.join(dead_folder, uuid.uuid4().hex))


def ensure_no_checkout(dir_names):
  """Ensure that there is no undesired checkout under build/."""
  build_dir = os.getcwd()
  has_checkout = any(path.exists(path.join(build_dir, dir_name, '.git'))
                     for dir_name in dir_names)
  if has_checkout:
    for filename in os.listdir(build_dir):
      deletion_target = path.join(build_dir, filename)
      print '.git detected in checkout, deleting %s...' % deletion_target,
      remove(deletion_target)
      print 'done'


def gclient_configure(solutions, target_os, target_os_only, git_cache_dir):
  """Should do the same thing as gclient --spec='...'."""
  with codecs.open('.gclient', mode='w', encoding='utf-8') as f:
    f.write(get_gclient_spec(
        solutions, target_os, target_os_only, git_cache_dir))


def gclient_sync(with_branch_heads, shallow):
  # We just need to allocate a filename.
  fd, gclient_output_file = tempfile.mkstemp(suffix='.json')
  os.close(fd)
  gclient_bin = 'gclient.bat' if sys.platform.startswith('win') else 'gclient'
  cmd = [gclient_bin, 'sync', '--verbose', '--reset', '--force',
         '--ignore_locks', '--output-json', gclient_output_file,
         '--nohooks', '--noprehooks', '--delete_unversioned_trees']
  if with_branch_heads:
    cmd += ['--with_branch_heads']
  if shallow:
    cmd += ['--shallow']

  try:
    call(*cmd, tries=1)
  except SubprocessFailed as e:
    # Throw a GclientSyncFailed exception so we can catch this independently.
    raise GclientSyncFailed(e.message, e.code, e.output)
  else:
    with open(gclient_output_file) as f:
      return json.load(f)
  finally:
    os.remove(gclient_output_file)


def gclient_runhooks(gyp_envs):
  gclient_bin = 'gclient.bat' if sys.platform.startswith('win') else 'gclient'
  env = dict([env_var.split('=', 1) for env_var in gyp_envs])
  call(gclient_bin, 'runhooks', env=env)


def gclient_revinfo():
  gclient_bin = 'gclient.bat' if sys.platform.startswith('win') else 'gclient'
  return call(gclient_bin, 'revinfo', '-a') or ''


def create_manifest():
  manifest = {}
  output = gclient_revinfo()
  for line in output.strip().splitlines():
    match = REVINFO_RE.match(line.strip())
    if match:
      manifest[match.group(1)] = {
        'repository': match.group(2),
        'revision': match.group(3),
      }
    else:
      print "WARNING: Couldn't match revinfo line:\n%s" % line
  return manifest


def get_commit_message_footer_map(message):
  """Returns: (dict) A dictionary of commit message footer entries.
  """
  footers = {}

  # Extract the lines in the footer block.
  lines = []
  for line in message.strip().splitlines():
    line = line.strip()
    if len(line) == 0:
      del lines[:]
      continue
    lines.append(line)

  # Parse the footer
  for line in lines:
    m = COMMIT_FOOTER_ENTRY_RE.match(line)
    if not m:
      # If any single line isn't valid, the entire footer is invalid.
      footers.clear()
      return footers
    footers[m.group(1)] = m.group(2).strip()
  return footers


def get_commit_message_footer(message, key):
  """Returns: (str/None) The footer value for 'key', or None if none was found.
  """
  return get_commit_message_footer_map(message).get(key)


def emit_log_lines(name, lines):
  for line in lines.splitlines():
    print '@@@STEP_LOG_LINE@%s@%s@@@' % (name, line)
  print '@@@STEP_LOG_END@%s@@@' % name


def emit_properties(properties):
  for property_name, property_value in sorted(properties.items()):
    print '@@@SET_BUILD_PROPERTY@%s@"%s"@@@' % (property_name, property_value)


# Derived from:
# http://code.activestate.com/recipes/577972-disk-usage/?in=user-4178764
def get_total_disk_space():
  cwd = os.getcwd()
  # Windows is the only platform that doesn't support os.statvfs, so
  # we need to special case this.
  if sys.platform.startswith('win'):
    _, total, free = (ctypes.c_ulonglong(), ctypes.c_ulonglong(), \
                      ctypes.c_ulonglong())
    if sys.version_info >= (3,) or isinstance(cwd, unicode):
      fn = ctypes.windll.kernel32.GetDiskFreeSpaceExW
    else:
      fn = ctypes.windll.kernel32.GetDiskFreeSpaceExA
    ret = fn(cwd, ctypes.byref(_), ctypes.byref(total), ctypes.byref(free))
    if ret == 0:
      # WinError() will fetch the last error code.
      raise ctypes.WinError()
    return (total.value, free.value)

  else:
    st = os.statvfs(cwd)
    free = st.f_bavail * st.f_frsize
    total = st.f_blocks * st.f_frsize
    return (total, free)


def get_target_revision(folder_name, git_url, revisions):
  normalized_name = folder_name.strip('/')
  if normalized_name in revisions:
    return revisions[normalized_name]
  if git_url in revisions:
    return revisions[git_url]
  return None


def force_revision(folder_name, revision):
  split_revision = revision.split(':', 1)
  branch = 'master'
  if len(split_revision) == 2:
    # Support for "branch:revision" syntax.
    branch, revision = split_revision

  if revision and revision.upper() != 'HEAD':
    git('checkout', '--force', revision, cwd=folder_name)
  else:
    ref = branch if branch.startswith('refs/') else 'origin/%s' % branch
    git('checkout', '--force', ref, cwd=folder_name)


def git_checkout(solutions, revisions, shallow, refs, git_cache_dir):
  build_dir = os.getcwd()
  # Before we do anything, break all git_cache locks.
  if path.isdir(git_cache_dir):
    git('cache', 'unlock', '-vv', '--force', '--all',
        '--cache-dir', git_cache_dir)
    for item in os.listdir(git_cache_dir):
      filename = os.path.join(git_cache_dir, item)
      if item.endswith('.lock'):
        raise Exception('%s exists after cache unlock' % filename)
  first_solution = True
  for sln in solutions:
    # This is so we can loop back and try again if we need to wait for the
    # git mirrors to update from SVN.
    done = False
    tries_left = 60
    while not done:
      name = sln['name']
      url = sln['url']
      if url == CHROMIUM_SRC_URL or url + '.git' == CHROMIUM_SRC_URL:
        # Experiments show there's little to be gained from
        # a shallow clone of src.
        shallow = False
      sln_dir = path.join(build_dir, name)
      s = ['--shallow'] if shallow else []
      populate_cmd = (['cache', 'populate', '--ignore_locks', '-v',
                       '--cache-dir', git_cache_dir] + s + [url])
      for ref in refs:
        populate_cmd.extend(['--ref', ref])
      git(*populate_cmd)
      mirror_dir = git(
          'cache', 'exists', '--quiet',
          '--cache-dir', git_cache_dir, url).strip()
      clone_cmd = (
          'clone', '--no-checkout', '--local', '--shared', mirror_dir, sln_dir)

      try:
        if not path.isdir(sln_dir):
          git(*clone_cmd)
        else:
          git('remote', 'set-url', 'origin', mirror_dir, cwd=sln_dir)
          git('fetch', 'origin', cwd=sln_dir)
        for ref in refs:
          refspec = '%s:%s' % (ref, ref.lstrip('+'))
          git('fetch', 'origin', refspec, cwd=sln_dir)

        revision = get_target_revision(name, url, revisions) or 'HEAD'
        force_revision(sln_dir, revision)
        done = True
      except SubprocessFailed as e:
        # Exited abnormally, theres probably something wrong.
        # Lets wipe the checkout and try again.
        tries_left -= 1
        if tries_left > 0:
          print 'Something failed: %s.' % str(e)
          print 'waiting 5 seconds and trying again...'
          time.sleep(5)
        else:
          raise
        remove(sln_dir)

    git('clean', '-dff', cwd=sln_dir)

    if first_solution:
      git_ref = git('log', '--format=%H', '--max-count=1',
                    cwd=sln_dir).strip()
    first_solution = False
  return git_ref


def _download(url):
  """Fetch url and return content, with retries for flake."""
  for attempt in xrange(ATTEMPTS):
    try:
      return urllib2.urlopen(url).read()
    except Exception:
      if attempt == ATTEMPTS - 1:
        raise


def apply_rietveld_issue(issue, patchset, root, server, _rev_map, _revision,
                         email_file, key_file, whitelist=None, blacklist=None):
  apply_issue_bin = ('apply_issue.bat' if sys.platform.startswith('win')
                     else 'apply_issue')
  cmd = [apply_issue_bin,
         # The patch will be applied on top of this directory.
         '--root_dir', root,
         # Tell apply_issue how to fetch the patch.
         '--issue', issue,
         '--server', server,
         # Always run apply_issue.py, otherwise it would see update.flag
         # and then bail out.
         '--force',
         # Don't run gclient sync when it sees a DEPS change.
         '--ignore_deps',
  ]
  # Use an oauth key file if specified.
  if email_file and key_file:
    cmd.extend(['--email-file', email_file, '--private-key-file', key_file])
  else:
    cmd.append('--no-auth')

  if patchset:
    cmd.extend(['--patchset', patchset])
  if whitelist:
    for item in whitelist:
      cmd.extend(['--whitelist', item])
  elif blacklist:
    for item in blacklist:
      cmd.extend(['--blacklist', item])

  # TODO(kjellander): Remove this hack when http://crbug.com/611808 is fixed.
  if root == path.join('src', 'third_party', 'webrtc'):
    cmd.extend(['--extra_patchlevel=1'])

  # Only try once, since subsequent failures hide the real failure.
  try:
    call(*cmd, tries=1)
  except SubprocessFailed as e:
    raise PatchFailed(e.message, e.code, e.output)

def apply_gerrit_ref(gerrit_repo, gerrit_ref, root, gerrit_reset,
                     gerrit_rebase_patch_ref):
  gerrit_repo = gerrit_repo or 'origin'
  assert gerrit_ref
  base_rev = git('rev-parse', 'HEAD', cwd=root).strip()

  print '===Applying gerrit ref==='
  print 'Repo is %r @ %r, ref is %r, root is %r' % (
      gerrit_repo, base_rev, gerrit_ref, root)
  try:
    git('retry', 'fetch', gerrit_repo, gerrit_ref, cwd=root, tries=1)
    git('checkout', 'FETCH_HEAD', cwd=root)

    if gerrit_rebase_patch_ref:
      print '===Rebasing==='
      # git rebase requires a branch to operate on.
      temp_branch_name = 'tmp/' + uuid.uuid4().hex
      try:
        ok = False
        git('checkout', '-b', temp_branch_name, cwd=root)
        git('rebase', base_rev, cwd=root)

        # Get off of the temporary branch since it can't be deleted otherwise.
        cur_rev = git('rev-parse', 'HEAD', cwd=root).strip()
        git('checkout', cur_rev, cwd=root)
        git('branch', '-D', temp_branch_name, cwd=root)
        ok = True
      finally:
        if not ok:
          # Get off of the temporary branch since it can't be deleted otherwise.
          git('checkout', base_rev, cwd=root)
          git('branch', '-D', temp_branch_name, cwd=root)

    if gerrit_reset:
      git('reset', '--soft', base_rev, cwd=root)
  except SubprocessFailed as e:
    raise PatchFailed(e.message, e.code, e.output)

def check_flag(flag_file):
  """Returns True if the flag file is present."""
  return os.path.isfile(flag_file)


def delete_flag(flag_file):
  """Remove bot update flag."""
  if os.path.isfile(flag_file):
    os.remove(flag_file)


def emit_flag(flag_file):
  """Deposit a bot update flag on the system to tell gclient not to run."""
  print 'Emitting flag file at %s' % flag_file
  with open(flag_file, 'wb') as f:
    f.write('Success!')


def get_commit_position(git_path, revision='HEAD'):
  """Dumps the 'git' log for a specific revision and parses out the commit
  position.

  If a commit position metadata key is found, its value will be returned.
  """
  # TODO(iannucci): Use git-footers for this.
  git_log = git('log', '--format=%B', '-n1', revision, cwd=git_path)
  footer_map = get_commit_message_footer_map(git_log)

  # Search for commit position metadata
  value = (footer_map.get(COMMIT_POSITION_FOOTER_KEY) or
           footer_map.get(COMMIT_ORIGINAL_POSITION_FOOTER_KEY))
  if value:
    return value
  return None


def parse_got_revision(gclient_output, got_revision_mapping):
  """Translate git gclient revision mapping to build properties."""
  properties = {}
  solutions_output = {
      # Make sure path always ends with a single slash.
      '%s/' % path.rstrip('/') : solution_output for path, solution_output
      in gclient_output['solutions'].iteritems()
  }
  for dir_name, property_name in got_revision_mapping.iteritems():
    # Make sure dir_name always ends with a single slash.
    dir_name = '%s/' % dir_name.rstrip('/')
    if dir_name not in solutions_output:
      continue
    solution_output = solutions_output[dir_name]
    if solution_output.get('scm') is None:
      # This is an ignored DEPS, so the output got_revision should be 'None'.
      git_revision = revision = commit_position = None
    else:
      # Since we are using .DEPS.git, everything had better be git.
      assert solution_output.get('scm') == 'git'
      revision = git('rev-parse', 'HEAD', cwd=dir_name).strip()
      commit_position = get_commit_position(dir_name)

    properties[property_name] = revision
    if revision != git_revision:
      properties['%s_git' % property_name] = git_revision
    if commit_position:
      properties['%s_cp' % property_name] = commit_position

  return properties


def emit_json(out_file, did_run, gclient_output=None, **kwargs):
  """Write run information into a JSON file."""
  output = {}
  output.update(gclient_output if gclient_output else {})
  output.update({'did_run': did_run})
  output.update(kwargs)
  with open(out_file, 'wb') as f:
    f.write(json.dumps(output, sort_keys=True))


def ensure_deps_revisions(deps_url_mapping, solutions, revisions):
  """Ensure correct DEPS revisions, ignores solutions."""
  for deps_name, deps_data in sorted(deps_url_mapping.items()):
    if deps_name.strip('/') in solutions:
      # This has already been forced to the correct solution by git_checkout().
      continue
    revision = get_target_revision(deps_name, deps_data.get('url', None),
                                   revisions)
    if not revision:
      continue
    git('fetch', 'origin', cwd=deps_name)
    force_revision(deps_name, revision)


def ensure_checkout(solutions, revisions, first_sln, target_os, target_os_only,
                    patch_root, issue, patchset, rietveld_server,
                    gerrit_repo, gerrit_ref, gerrit_rebase_patch_ref,
                    revision_mapping, apply_issue_email_file,
                    apply_issue_key_file, gyp_env, shallow, runhooks,
                    refs, git_cache_dir, gerrit_reset):
  # Get a checkout of each solution, without DEPS or hooks.
  # Calling git directly because there is no way to run Gclient without
  # invoking DEPS.
  print 'Fetching Git checkout'

  git_ref = git_checkout(solutions, revisions, shallow, refs, git_cache_dir)

  print '===Processing patch solutions==='
  already_patched = []
  patch_root = patch_root or ''
  applied_gerrit_patch = False
  print 'Patch root is %r' % patch_root
  for solution in solutions:
    print 'Processing solution %r' % solution['name']
    if (patch_root == solution['name'] or
        solution['name'].startswith(patch_root + '/')):
      relative_root = solution['name'][len(patch_root) + 1:]
      target = '/'.join([relative_root, 'DEPS']).lstrip('/')
      print '  relative root is %r, target is %r' % (relative_root, target)
      if issue:
        apply_rietveld_issue(issue, patchset, patch_root, rietveld_server,
                             revision_mapping, git_ref, apply_issue_email_file,
                             apply_issue_key_file, whitelist=[target])
        already_patched.append(target)
      elif gerrit_ref:
        apply_gerrit_ref(gerrit_repo, gerrit_ref, patch_root, gerrit_reset,
                         gerrit_rebase_patch_ref)
        applied_gerrit_patch = True

  # Ensure our build/ directory is set up with the correct .gclient file.
  gclient_configure(solutions, target_os, target_os_only, git_cache_dir)

  # Let gclient do the DEPS syncing.
  # The branch-head refspec is a special case because its possible Chrome
  # src, which contains the branch-head refspecs, is DEPSed in.
  gclient_output = gclient_sync(BRANCH_HEADS_REFSPEC in refs, shallow)

  # Now that gclient_sync has finished, we should revert any .DEPS.git so that
  # presubmit doesn't complain about it being modified.
  if git('ls-files', '.DEPS.git', cwd=first_sln).strip():
    git('checkout', 'HEAD', '--', '.DEPS.git', cwd=first_sln)

  # Finally, ensure that all DEPS are pinned to the correct revision.
  dir_names = [sln['name'] for sln in solutions]
  ensure_deps_revisions(gclient_output.get('solutions', {}),
                        dir_names, revisions)
  # Apply the rest of the patch here (sans DEPS)
  if issue:
    apply_rietveld_issue(issue, patchset, patch_root, rietveld_server,
                         revision_mapping, git_ref, apply_issue_email_file,
                         apply_issue_key_file, blacklist=already_patched)
  elif gerrit_ref and not applied_gerrit_patch:
    # If gerrit_ref was for solution's main repository, it has already been
    # applied above. This chunk is executed only for patches to DEPS-ed in
    # git repositories.
    apply_gerrit_ref(gerrit_repo, gerrit_ref, patch_root, gerrit_reset,
                     gerrit_rebase_patch_ref)

  # Reset the deps_file point in the solutions so that hooks get run properly.
  for sln in solutions:
    sln['deps_file'] = sln.get('deps_file', 'DEPS').replace('.DEPS.git', 'DEPS')
  gclient_configure(solutions, target_os, target_os_only, git_cache_dir)

  return gclient_output


def parse_revisions(revisions, root):
  """Turn a list of revision specs into a nice dictionary.

  We will always return a dict with {root: something}.  By default if root
  is unspecified, or if revisions is [], then revision will be assigned 'HEAD'
  """
  results = {root.strip('/'): 'HEAD'}
  expanded_revisions = []
  for revision in revisions:
    # Allow rev1,rev2,rev3 format.
    # TODO(hinoka): Delete this when webkit switches to recipes.
    expanded_revisions.extend(revision.split(','))
  for revision in expanded_revisions:
    split_revision = revision.split('@')
    if len(split_revision) == 1:
      # This is just a plain revision, set it as the revision for root.
      results[root] = split_revision[0]
    elif len(split_revision) == 2:
      # This is an alt_root@revision argument.
      current_root, current_rev = split_revision

      parsed_root = urlparse.urlparse(current_root)
      if parsed_root.scheme in ['http', 'https']:
        # We want to normalize git urls into .git urls.
        normalized_root = 'https://%s/%s' % (parsed_root.netloc,
                                             parsed_root.path)
        if not normalized_root.endswith('.git'):
          normalized_root = '%s.git' % normalized_root
      elif parsed_root.scheme:
        print 'WARNING: Unrecognized scheme %s, ignoring' % parsed_root.scheme
        continue
      else:
        # This is probably a local path.
        normalized_root = current_root.strip('/')

      results[normalized_root] = current_rev
    else:
      print ('WARNING: %r is not recognized as a valid revision specification,'
             'skipping' % revision)
  return results


def parse_args():
  parse = optparse.OptionParser()

  parse.add_option('--issue', help='Issue number to patch from.')
  parse.add_option('--patchset',
                   help='Patchset from issue to patch from, if applicable.')
  parse.add_option('--apply_issue_email_file',
                   help='--email-file option passthrough for apply_patch.py.')
  parse.add_option('--apply_issue_key_file',
                   help='--private-key-file option passthrough for '
                        'apply_patch.py.')
  parse.add_option('--root', dest='patch_root',
                   help='DEPRECATED: Use --patch_root.')
  parse.add_option('--patch_root', help='Directory to patch on top of.')
  parse.add_option('--rietveld_server',
                   default='codereview.chromium.org',
                   help='Rietveld server.')
  parse.add_option('--gerrit_repo',
                   help='Gerrit repository to pull the ref from.')
  parse.add_option('--gerrit_ref', help='Gerrit ref to apply.')
  parse.add_option('--gerrit_no_rebase_patch_ref', action='store_true',
                   help='Bypass rebase of Gerrit patch ref after checkout.')
  parse.add_option('--gerrit_no_reset', action='store_true',
                   help='Bypass calling reset after applying a gerrit ref.')
  parse.add_option('--specs', help='Gcilent spec.')
  parse.add_option('--master',
                   help='Master name. If specified and it is not in '
                        'bot_update\'s whitelist, bot_update will be noop.')
  parse.add_option('-f', '--force', action='store_true',
                   help='Bypass check to see if we want to be run. '
                        'Should ONLY be used locally or by smart recipes.')
  parse.add_option('--revision_mapping',
                   help='{"path/to/repo/": "property_name"}')
  parse.add_option('--revision_mapping_file',
                   help=('Same as revision_mapping, except its a path to a json'
                         ' file containing that format.'))
  parse.add_option('--revision', action='append', default=[],
                   help='Revision to check out. Can be any form of git ref. '
                        'Can prepend root@<rev> to specify which repository, '
                        'where root is either a filesystem path or git https '
                        'url. To specify Tip of Tree, set rev to HEAD. ')
  parse.add_option('--output_manifest', action='store_true',
                   help=('Add manifest json to the json output.'))
  parse.add_option('--slave_name', default=socket.getfqdn().split('.')[0],
                   help='Hostname of the current machine, '
                   'used for determining whether or not to activate.')
  parse.add_option('--builder_name', help='Name of the builder, '
                   'used for determining whether or not to activate.')
  parse.add_option('--build_dir', default=os.getcwd())
  parse.add_option('--flag_file', default=path.join(os.getcwd(),
                                                    'update.flag'))
  parse.add_option('--shallow', action='store_true',
                   help='Use shallow clones for cache repositories.')
  parse.add_option('--gyp_env', action='append', default=[],
                   help='Environment variables to pass into gclient runhooks.')
  parse.add_option('--clobber', action='store_true',
                   help='Delete checkout first, always')
  parse.add_option('--bot_update_clobber', action='store_true', dest='clobber',
                   help='(synonym for --clobber)')
  parse.add_option('-o', '--output_json',
                   help='Output JSON information into a specified file')
  parse.add_option('--no_shallow', action='store_true',
                   help='Bypass disk detection and never shallow clone. '
                        'Does not override the --shallow flag')
  parse.add_option('--no_runhooks', action='store_true',
                   help='Do not run hooks on official builder.')
  parse.add_option('--refs', action='append',
                   help='Also fetch this refspec for the main solution(s). '
                        'Eg. +refs/branch-heads/*')
  parse.add_option('--with_branch_heads', action='store_true',
                    help='Always pass --with_branch_heads to gclient.  This '
                          'does the same thing as --refs +refs/branch-heads/*')
  parse.add_option('--git-cache-dir', default=path.join(SLAVE_DIR, 'cache_dir'),
                   help='Path to git cache directory.')


  options, args = parse.parse_args()

  if not options.refs:
    options.refs = []

  if options.with_branch_heads:
    options.refs.append(BRANCH_HEADS_REFSPEC)
    del options.with_branch_heads

  try:
    if options.revision_mapping_file:
      if options.revision_mapping:
        print ('WARNING: Ignoring --revision_mapping: --revision_mapping_file '
               'was set at the same time as --revision_mapping?')
      with open(options.revision_mapping_file, 'r') as f:
        options.revision_mapping = json.load(f)
    elif options.revision_mapping:
      options.revision_mapping = json.loads(options.revision_mapping)
  except Exception as e:
    print (
        'WARNING: Caught execption while parsing revision_mapping*: %s'
        % (str(e),)
    )

  # Because we print CACHE_DIR out into a .gclient file, and then later run
  # eval() on it, backslashes need to be escaped, otherwise "E:\b\build" gets
  # parsed as "E:[\x08][\x08]uild".
  if sys.platform.startswith('win'):
    options.git_cache_dir = options.git_cache_dir.replace('\\', '\\\\')

  return options, args


def prepare(options, git_slns, active):
  """Prepares the target folder before we checkout."""
  dir_names = [sln.get('name') for sln in git_slns if 'name' in sln]
  # If we're active now, but the flag file doesn't exist (we weren't active
  # last run) or vice versa, blow away all checkouts.
  if options.clobber or (bool(active) != bool(check_flag(options.flag_file))):
    ensure_no_checkout(dir_names)
  if options.output_json:
    # Make sure we tell recipes that we didn't run if the script exits here.
    emit_json(options.output_json, did_run=active)
  emit_flag(options.flag_file)

  # Do a shallow checkout if the disk is less than 100GB.
  total_disk_space, free_disk_space = get_total_disk_space()
  total_disk_space_gb = int(total_disk_space / (1024 * 1024 * 1024))
  used_disk_space_gb = int((total_disk_space - free_disk_space)
                           / (1024 * 1024 * 1024))
  percent_used = int(used_disk_space_gb * 100 / total_disk_space_gb)
  step_text = '[%dGB/%dGB used (%d%%)]' % (used_disk_space_gb,
                                           total_disk_space_gb,
                                           percent_used)
  if not options.output_json:
    print '@@@STEP_TEXT@%s@@@' % step_text
  if not options.shallow:
    options.shallow = (total_disk_space < SHALLOW_CLONE_THRESHOLD
                       and not options.no_shallow)

  # The first solution is where the primary DEPS file resides.
  first_sln = dir_names[0]

  # Split all the revision specifications into a nice dict.
  print 'Revisions: %s' % options.revision
  revisions = parse_revisions(options.revision, first_sln)
  print 'Fetching Git checkout at %s@%s' % (first_sln, revisions[first_sln])
  return revisions, step_text


def checkout(options, git_slns, specs, master, revisions, step_text):
  first_sln = git_slns[0]['name']
  dir_names = [sln.get('name') for sln in git_slns if 'name' in sln]
  try:
    # Outer try is for catching patch failures and exiting gracefully.
    # Inner try is for catching gclient failures and retrying gracefully.
    try:
      checkout_parameters = dict(
          # First, pass in the base of what we want to check out.
          solutions=git_slns,
          revisions=revisions,
          first_sln=first_sln,

          # Also, target os variables for gclient.
          target_os=specs.get('target_os', []),
          target_os_only=specs.get('target_os_only', False),

          # Then, pass in information about how to patch.
          patch_root=options.patch_root,
          issue=options.issue,
          patchset=options.patchset,
          rietveld_server=options.rietveld_server,
          gerrit_repo=options.gerrit_repo,
          gerrit_ref=options.gerrit_ref,
          gerrit_rebase_patch_ref=not options.gerrit_no_rebase_patch_ref,
          revision_mapping=options.revision_mapping,
          apply_issue_email_file=options.apply_issue_email_file,
          apply_issue_key_file=options.apply_issue_key_file,

          # For official builders.
          gyp_env=options.gyp_env,
          runhooks=not options.no_runhooks,

          # Finally, extra configurations such as shallowness of the clone.
          shallow=options.shallow,
          refs=options.refs,
          git_cache_dir=options.git_cache_dir,
          gerrit_reset=not options.gerrit_no_reset)
      gclient_output = ensure_checkout(**checkout_parameters)
    except GclientSyncFailed:
      print 'We failed gclient sync, lets delete the checkout and retry.'
      ensure_no_checkout(dir_names)
      gclient_output = ensure_checkout(**checkout_parameters)
  except PatchFailed as e:
    if options.output_json:
      # Tell recipes information such as root, got_revision, etc.
      emit_json(options.output_json,
                did_run=True,
                root=first_sln,
                log_lines=[('patch error', e.output),],
                patch_apply_return_code=e.code,
                patch_root=options.patch_root,
                patch_failure=True,
                step_text='%s PATCH FAILED' % step_text,
                fixed_revisions=revisions)
    else:
      # If we're not on recipes, tell annotator about our got_revisions.
      emit_log_lines('patch error', e.output)
      print '@@@STEP_TEXT@%s PATCH FAILED@@@' % step_text
    raise

  # Take care of got_revisions outputs.
  revision_mapping = GOT_REVISION_MAPPINGS.get(git_slns[0]['url'], {})
  if options.revision_mapping:
    revision_mapping.update(options.revision_mapping)

  # If the repo is not in the default GOT_REVISION_MAPPINGS and no
  # revision_mapping were specified on the command line then
  # default to setting 'got_revision' based on the first solution.
  if not revision_mapping:
    revision_mapping[first_sln] = 'got_revision'

  got_revisions = parse_got_revision(gclient_output, revision_mapping)

  if not got_revisions:
    # TODO(hinoka): We should probably bail out here, but in the interest
    # of giving mis-configured bots some time to get fixed use a dummy
    # revision here.
    got_revisions = { 'got_revision': 'BOT_UPDATE_NO_REV_FOUND' }
    #raise Exception('No got_revision(s) found in gclient output')

  if options.output_json:
    manifest = create_manifest() if options.output_manifest else None
    # Tell recipes information such as root, got_revision, etc.
    emit_json(options.output_json,
              did_run=True,
              root=first_sln,
              patch_root=options.patch_root,
              step_text=step_text,
              fixed_revisions=revisions,
              properties=got_revisions,
              manifest=manifest)
  else:
    # If we're not on recipes, tell annotator about our got_revisions.
    emit_properties(got_revisions)


def print_help_text(force, output_json, active, master, builder, slave):
  """Print helpful messages to tell devs whats going on."""
  if force and output_json:
    recipe_force = 'Forced on by recipes'
  elif active and output_json:
    recipe_force = 'Off by recipes, but forced on by bot update'
  elif not active and output_json:
    recipe_force = 'Forced off by recipes'
  else:
    recipe_force = 'N/A. Was not called by recipes'

  print BOT_UPDATE_MESSAGE % {
    'master': master or 'Not specified',
    'builder': builder or 'Not specified',
    'slave': slave or 'Not specified',
    'recipe': recipe_force,
    'CURRENT_DIR': CURRENT_DIR,
    'BUILDER_DIR': BUILDER_DIR,
    'SLAVE_DIR': SLAVE_DIR,
    'THIS_DIR': THIS_DIR,
    'SCRIPTS_DIR': SCRIPTS_DIR,
    'BUILD_DIR': BUILD_DIR,
    'ROOT_DIR': ROOT_DIR,
    'DEPOT_TOOLS_DIR': DEPOT_TOOLS_DIR,
  },
  print ACTIVATED_MESSAGE if active else NOT_ACTIVATED_MESSAGE


def main():
  # Get inputs.
  options, _ = parse_args()
  builder = options.builder_name
  slave = options.slave_name
  master = options.master

  # Always run. This option will be removed in a later CL, but for now make sure
  # that bot_update is ALWAYS set to run, no matter what.
  options.force = True

  # Check if this script should activate or not.
  active = options.force or check_valid_host(master, builder, slave)

  # Print a helpful message to tell developers whats going on with this step.
  print_help_text(
      options.force, options.output_json, active, master, builder, slave)

  # Parse, munipulate, and print the gclient solutions.
  specs = {}
  exec(options.specs, specs)
  orig_solutions = specs.get('solutions', [])
  git_slns = modify_solutions(orig_solutions)

  solutions_printer(git_slns)

  try:
    # Dun dun dun, the main part of bot_update.
    revisions, step_text = prepare(options, git_slns, active)
    checkout(options, git_slns, specs, master, revisions, step_text)

  except PatchFailed as e:
    emit_flag(options.flag_file)
    # Return a specific non-zero exit code for patch failure (because it is
    # a failure), but make it different than other failures to distinguish
    # between infra failures (independent from patch author), and patch
    # failures (that patch author can fix). However, PatchFailure due to
    # download patch failure is still an infra problem.
    if e.code == 3:
      # Patch download problem.
      return 87
    # Genuine patch problem.
    return 88
  except Exception:
    # Unexpected failure.
    emit_flag(options.flag_file)
    raise
  else:
    emit_flag(options.flag_file)


if __name__ == '__main__':
  sys.exit(main())
