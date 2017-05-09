#!/usr/bin/env python

# Copyright 2017 The LUCI Authors. All rights reserved.
# Use of this source code is governed under the Apache License, Version 2.0
# that can be found in the LICENSE file.

"""Bootstrap script to clone and forward to the recipe engine tool.

*******************
** DO NOT MODIFY **
*******************

This is a copy of https://github.com/luci/recipes-py/blob/master/doc/recipes.py.
To fix bugs, fix in the github repo then run the autoroller.
"""

import os

#### PER-REPO CONFIGURATION (editable) ####
# The root of the repository relative to the directory of this file.
REPO_ROOT = os.path.join(os.pardir)
# The path of the recipes.cfg file relative to the root of the repository.
RECIPES_CFG = os.path.join('infra', 'config', 'recipes.cfg')
#### END PER-REPO CONFIGURATION ####

import argparse
import json
import logging
import random
import subprocess
import sys
import time
import urlparse

from collections import namedtuple

from cStringIO import StringIO

# The dependency entry for the recipe_engine in the client repo's recipes.cfg
#
# url (str) - the url to the engine repo we want to use.
# revision (str) - the git revision for the engine to get.
# path_override (str) - the subdirectory in the engine repo we should use to
#   find it's recipes.py entrypoint. This is here for completeness, but will
#   essentially always be empty. It would be used if the recipes-py repo was
#   merged as a subdirectory of some other repo and you depended on that
#   subdirectory.
# branch (str) - the branch to fetch for the engine as an absolute ref (e.g.
#   refs/heads/master)
# repo_type ("GIT"|"GITILES") - An ignored enum which will be removed soon.
EngineDep = namedtuple('EngineDep',
                       'url revision path_override branch repo_type')

def parse(repo_root, recipes_cfg_path):
  """Parse is transitional code which parses a recipes.cfg file as either jsonpb
  or as textpb.

  Args:
    repo_root (str) - native path to the root of the repo we're trying to run
      recipes for.
    recipes_cfg_path (str) - native path to the recipes.cfg file to process.

  Returns (as tuple):
    engine_dep (EngineDep): The recipe_engine dependency.
    recipes_path (str) - native path to where the recipes live inside of the
      current repo (i.e. the folder containing `recipes/` and/or
      `recipe_modules`)
  """
  with open(recipes_cfg_path, 'rU') as fh:
    pb = json.load(fh)

  if pb['api_version'] == 1:
    # TODO(iannucci): remove when we only support version 2
    engine = next(
      (d for d in pb['deps'] if d['project_id'] == 'recipe_engine'), None)
    if engine is None:
      raise ValueError('could not find recipe_engine dep in %r'
                       % recipes_cfg_path)
  else:
    engine = pb['deps']['recipe_engine']

  if 'url' not in engine:
    raise ValueError(
      'Required field "url" in dependency "recipe_engine" not found: %r' %
      (recipes_cfg_path,)
    )

  engine.setdefault('revision', '')
  engine.setdefault('path_override', '')
  engine.setdefault('branch', 'refs/heads/master')
  recipes_path = pb.get('recipes_path', '')

  # TODO(iannucci): only support absolute refs
  if not engine['branch'].startswith('refs/'):
    engine['branch'] = 'refs/heads/' + engine['branch']

  engine.setdefault('repo_type', 'GIT')
  if engine['repo_type'] not in ('GIT', 'GITILES'):
    raise ValueError(
      'Unsupported "repo_type" value in dependency "recipe_engine": %r' %
      (recipes_cfg_path,)
    )

  recipes_path = os.path.join(repo_root, recipes_path.replace('/', os.path.sep))
  return EngineDep(**engine), recipes_path


GIT = 'git.bat' if sys.platform.startswith(('win', 'cygwin')) else 'git'


def _subprocess_call(argv, **kwargs):
  logging.info('Running %r', argv)
  return subprocess.call(argv, **kwargs)


def _git_check_call(argv, **kwargs):
  argv = [GIT]+argv
  logging.info('Running %r', argv)
  subprocess.check_call(argv, **kwargs)


def _git_output(argv, **kwargs):
  argv = [GIT]+argv
  logging.info('Running %r', argv)
  return subprocess.check_output(argv, **kwargs)


def find_engine_override(argv):
  """Since the bootstrap process attempts to defer all logic to the recipes-py
  repo, we need to be aware if the user is overriding the recipe_engine
  dependency. This looks for and returns the overridden recipe_engine path, if
  any, or None if the user didn't override it."""
  PREFIX = 'recipe_engine='

  p = argparse.ArgumentParser(add_help=False)
  p.add_argument('-O', '--project-override', action='append')
  args, _ = p.parse_known_args(argv)
  for override in args.project_override or ():
    if override.startswith(PREFIX):
      return override[len(PREFIX):]
  return None


def checkout_engine(repo_root, recipes_cfg_path):
  """Checks out"""

  dep, recipes_path = parse(repo_root, recipes_cfg_path)

  url = dep.url

  engine_path = find_engine_override(sys.argv[1:])
  if not engine_path and url.startswith('file://'):
    engine_path = urlparse.urlparse(url).path

  if not engine_path:
    revision = dep.revision
    subpath = dep.path_override
    branch = dep.branch

    # Ensure that we have the recipe engine cloned.
    engine = os.path.join(recipes_path, '.recipe_deps', 'recipe_engine')
    engine_path = os.path.join(engine, subpath)

    with open(os.devnull, 'w') as NUL:
      # Note: this logic mirrors the logic in recipe_engine/fetch.py
      _git_check_call(['init', engine], stdout=NUL)

      try:
        _git_check_call(['rev-parse', '--verify', '%s^{commit}' % revision],
                        cwd=engine, stdout=NUL, stderr=NUL)
      except subprocess.CalledProcessError:
        _git_check_call(['fetch', url, branch], cwd=engine, stdout=NUL,
                        stderr=NUL)

    try:
      _git_check_call(['diff', '--quiet', revision], cwd=engine)
    except subprocess.CalledProcessError:
      _git_check_call(['reset', '-q', '--hard', revision], cwd=engine)

  return engine_path


def main():
  if '--verbose' in sys.argv:
    logging.getLogger().setLevel(logging.INFO)

  repo_root = os.path.abspath(
    _git_output(['rev-parse', '--show-toplevel'],
                cwd=os.path.dirname(__file__)).strip())

  # TODO(iannucci): Actually make the location of recipes.cfg configurable.
  recipes_cfg_path = os.path.join(repo_root, 'infra', 'config', 'recipes.cfg')

  engine_path = checkout_engine(repo_root, recipes_cfg_path)

  args = ['--package', recipes_cfg_path] + sys.argv[1:]
  return _subprocess_call([
      sys.executable, '-u',
      os.path.join(engine_path, 'recipes.py')] + args)


if __name__ == '__main__':
  sys.exit(main())
