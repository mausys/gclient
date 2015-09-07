#!/usr/bin/env python
# Copyright (c) 2012 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Get stats about your activity.

Example:
  - my_activity.py  for stats for the current week (last week on mondays).
  - my_activity.py -Q  for stats for last quarter.
  - my_activity.py -Y  for stats for this year.
  - my_activity.py -b 4/5/12  for stats since 4/5/12.
  - my_activity.py -b 4/5/12 -e 6/7/12 for stats between 4/5/12 and 6/7/12.
"""

# TODO(vadimsh): This script knows too much about ClientLogin and cookies. It
# will stop to work on ~20 Apr 2015.

# These services typically only provide a created time and a last modified time
# for each item for general queries. This is not enough to determine if there
# was activity in a given time period. So, we first query for all things created
# before end and modified after begin. Then, we get the details of each item and
# check those details to determine if there was activity in the given period.
# This means that query time scales mostly with (today() - begin).

import cookielib
import datetime
from datetime import datetime
from datetime import timedelta
from functools import partial
import json
import optparse
import os
import subprocess
import sys
import urllib
import urllib2

import auth
import fix_encoding
import gerrit_util
import rietveld
from third_party import upload

import auth
from third_party import httplib2

try:
  from dateutil.relativedelta import relativedelta # pylint: disable=F0401
except ImportError:
  print 'python-dateutil package required'
  exit(1)

# python-keyring provides easy access to the system keyring.
try:
  import keyring  # pylint: disable=W0611,F0401
except ImportError:
  print 'Consider installing python-keyring'

rietveld_instances = [
  {
    'url': 'codereview.chromium.org',
    'shorturl': 'crrev.com',
    'supports_owner_modified_query': True,
    'requires_auth': False,
    'email_domain': 'chromium.org',
  },
  {
    'url': 'chromereviews.googleplex.com',
    'shorturl': 'go/chromerev',
    'supports_owner_modified_query': True,
    'requires_auth': True,
    'email_domain': 'google.com',
  },
  {
    'url': 'codereview.appspot.com',
    'supports_owner_modified_query': True,
    'requires_auth': False,
    'email_domain': 'chromium.org',
  },
  {
    'url': 'breakpad.appspot.com',
    'supports_owner_modified_query': False,
    'requires_auth': False,
    'email_domain': 'chromium.org',
  },
]

gerrit_instances = [
  {
    'url': 'chromium-review.googlesource.com',
    'shorturl': 'crosreview.com',
  },
  {
    'url': 'chrome-internal-review.googlesource.com',
    'shorturl': 'crosreview.com/i',
  },
]

google_code_projects = [
  {
    'name': 'brillo',
    'shorturl': 'brbug.com',
  },
  {
    'name': 'chromium',
    'shorturl': 'crbug.com',
  },
  {
    'name': 'chromium-os',
    'shorturl': 'crosbug.com',
  },
  {
    'name': 'chrome-os-partner',
  },
  {
    'name': 'google-breakpad',
  },
  {
    'name': 'gyp',
  },
  {
    'name': 'skia',
  },
]

def username(email):
  """Keeps the username of an email address."""
  return email and email.split('@', 1)[0]


def datetime_to_midnight(date):
  return date - timedelta(hours=date.hour, minutes=date.minute,
                          seconds=date.second, microseconds=date.microsecond)


def get_quarter_of(date):
  begin = (datetime_to_midnight(date) -
           relativedelta(months=(date.month % 3) - 1, days=(date.day - 1)))
  return begin, begin + relativedelta(months=3)


def get_year_of(date):
  begin = (datetime_to_midnight(date) -
           relativedelta(months=(date.month - 1), days=(date.day - 1)))
  return begin, begin + relativedelta(years=1)


def get_week_of(date):
  begin = (datetime_to_midnight(date) - timedelta(days=date.weekday()))
  return begin, begin + timedelta(days=7)


def get_yes_or_no(msg):
  while True:
    response = raw_input(msg + ' yes/no [no] ')
    if response == 'y' or response == 'yes':
      return True
    elif not response or response == 'n' or response == 'no':
      return False


def datetime_from_gerrit(date_string):
  return datetime.strptime(date_string, '%Y-%m-%d %H:%M:%S.%f000')


def datetime_from_rietveld(date_string):
  try:
    return datetime.strptime(date_string, '%Y-%m-%d %H:%M:%S.%f')
  except ValueError:
    # Sometimes rietveld returns a value without the milliseconds part, so we
    # attempt to parse those cases as well.
    return datetime.strptime(date_string, '%Y-%m-%d %H:%M:%S')


def datetime_from_google_code(date_string):
  return datetime.strptime(date_string, '%Y-%m-%dT%H:%M:%S.%fZ')


class MyActivity(object):
  def __init__(self, options):
    self.options = options
    self.modified_after = options.begin
    self.modified_before = options.end
    self.user = options.user
    self.changes = []
    self.reviews = []
    self.issues = []
    self.check_cookies()
    self.google_code_auth_token = None

  # Check the codereview cookie jar to determine which Rietveld instances to
  # authenticate to.
  def check_cookies(self):
    filtered_instances = []

    def has_cookie(instance):
      auth_config = auth.extract_auth_config_from_options(self.options)
      a = auth.get_authenticator_for_host(instance['url'], auth_config)
      return a.has_cached_credentials()

    for instance in rietveld_instances:
      instance['auth'] = has_cookie(instance)

    if filtered_instances:
      print ('No cookie found for the following Rietveld instance%s:' %
             ('s' if len(filtered_instances) > 1 else ''))
      for instance in filtered_instances:
        print '\t' + instance['url']
      print 'Use --auth if you would like to authenticate to them.\n'

  def rietveld_search(self, instance, owner=None, reviewer=None):
    if instance['requires_auth'] and not instance['auth']:
      return []


    email = None if instance['auth'] else ''
    auth_config = auth.extract_auth_config_from_options(self.options)
    remote = rietveld.Rietveld('https://' + instance['url'], auth_config, email)

    # See def search() in rietveld.py to see all the filters you can use.
    query_modified_after = None

    if instance['supports_owner_modified_query']:
      query_modified_after = self.modified_after.strftime('%Y-%m-%d')

    # Rietveld does not allow search by both created_before and modified_after.
    # (And some instances don't allow search by both owner and modified_after)
    owner_email = None
    reviewer_email = None
    if owner:
      owner_email = owner + '@' + instance['email_domain']
    if reviewer:
      reviewer_email = reviewer + '@' + instance['email_domain']
    issues = remote.search(
        owner=owner_email,
        reviewer=reviewer_email,
        modified_after=query_modified_after,
        with_messages=True)

    issues = filter(
        lambda i: (datetime_from_rietveld(i['created']) < self.modified_before),
        issues)
    issues = filter(
        lambda i: (datetime_from_rietveld(i['modified']) > self.modified_after),
        issues)

    should_filter_by_user = True
    issues = map(partial(self.process_rietveld_issue, instance), issues)
    issues = filter(
        partial(self.filter_issue, should_filter_by_user=should_filter_by_user),
        issues)
    issues = sorted(issues, key=lambda i: i['modified'], reverse=True)

    return issues

  def process_rietveld_issue(self, instance, issue):
    ret = {}
    ret['owner'] = issue['owner_email']
    ret['author'] = ret['owner']

    ret['reviewers'] = set(issue['reviewers'])

    shorturl = instance['url']
    if 'shorturl' in instance:
      shorturl = instance['shorturl']

    ret['review_url'] = 'http://%s/%d' % (shorturl, issue['issue'])

    # Rietveld sometimes has '\r\n' instead of '\n'.
    ret['header'] = issue['description'].replace('\r', '').split('\n')[0]

    ret['modified'] = datetime_from_rietveld(issue['modified'])
    ret['created'] = datetime_from_rietveld(issue['created'])
    ret['replies'] = self.process_rietveld_replies(issue['messages'])

    return ret

  @staticmethod
  def process_rietveld_replies(replies):
    ret = []
    for reply in replies:
      r = {}
      r['author'] = reply['sender']
      r['created'] = datetime_from_rietveld(reply['date'])
      r['content'] = ''
      ret.append(r)
    return ret

  @staticmethod
  def gerrit_changes_over_ssh(instance, filters):
    # See https://review.openstack.org/Documentation/cmd-query.html
    # Gerrit doesn't allow filtering by created time, only modified time.
    gquery_cmd = ['ssh', '-p', str(instance['port']), instance['host'],
                  'gerrit', 'query',
                  '--format', 'JSON',
                  '--comments',
                  '--'] + filters
    (stdout, _) = subprocess.Popen(gquery_cmd, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE).communicate()
    # Drop the last line of the output with the stats.
    issues = stdout.splitlines()[:-1]
    return map(json.loads, issues)

  @staticmethod
  def gerrit_changes_over_rest(instance, filters):
    # Convert the "key:value" filter to a dictionary.
    req = dict(f.split(':', 1) for f in filters)
    try:
      # Instantiate the generator to force all the requests now and catch the
      # errors here.
      return list(gerrit_util.GenerateAllChanges(instance['url'], req,
          o_params=['MESSAGES', 'LABELS', 'DETAILED_ACCOUNTS']))
    except gerrit_util.GerritError, e:
      print 'ERROR: Looking up %r: %s' % (instance['url'], e)
      return []

  def gerrit_search(self, instance, owner=None, reviewer=None):
    max_age = datetime.today() - self.modified_after
    max_age = max_age.days * 24 * 3600 + max_age.seconds
    user_filter = 'owner:%s' % owner if owner else 'reviewer:%s' % reviewer
    filters = ['-age:%ss' % max_age, user_filter]

    # Determine the gerrit interface to use: SSH or REST API:
    if 'host' in instance:
      issues = self.gerrit_changes_over_ssh(instance, filters)
      issues = [self.process_gerrit_ssh_issue(instance, issue)
                for issue in issues]
    elif 'url' in instance:
      issues = self.gerrit_changes_over_rest(instance, filters)
      issues = [self.process_gerrit_rest_issue(instance, issue)
                for issue in issues]
    else:
      raise Exception('Invalid gerrit_instances configuration.')

    # TODO(cjhopman): should we filter abandoned changes?
    issues = filter(self.filter_issue, issues)
    issues = sorted(issues, key=lambda i: i['modified'], reverse=True)

    return issues

  def process_gerrit_ssh_issue(self, instance, issue):
    ret = {}
    ret['review_url'] = issue['url']
    if 'shorturl' in instance:
      ret['review_url'] = 'http://%s/%s' % (instance['shorturl'],
                                            issue['number'])
    ret['header'] = issue['subject']
    ret['owner'] = issue['owner']['email']
    ret['author'] = ret['owner']
    ret['created'] = datetime.fromtimestamp(issue['createdOn'])
    ret['modified'] = datetime.fromtimestamp(issue['lastUpdated'])
    if 'comments' in issue:
      ret['replies'] = self.process_gerrit_ssh_issue_replies(issue['comments'])
    else:
      ret['replies'] = []
    ret['reviewers'] = set(r['author'] for r in ret['replies'])
    ret['reviewers'].discard(ret['author'])
    return ret

  @staticmethod
  def process_gerrit_ssh_issue_replies(replies):
    ret = []
    replies = filter(lambda r: 'email' in r['reviewer'], replies)
    for reply in replies:
      ret.append({
        'author': reply['reviewer']['email'],
        'created': datetime.fromtimestamp(reply['timestamp']),
        'content': '',
      })
    return ret

  def process_gerrit_rest_issue(self, instance, issue):
    ret = {}
    ret['review_url'] = 'https://%s/%s' % (instance['url'], issue['_number'])
    if 'shorturl' in instance:
      # TODO(deymo): Move this short link to https once crosreview.com supports
      # it.
      ret['review_url'] = 'http://%s/%s' % (instance['shorturl'],
                                            issue['_number'])
    ret['header'] = issue['subject']
    ret['owner'] = issue['owner']['email']
    ret['author'] = ret['owner']
    ret['created'] = datetime_from_gerrit(issue['created'])
    ret['modified'] = datetime_from_gerrit(issue['updated'])
    if 'messages' in issue:
      ret['replies'] = self.process_gerrit_rest_issue_replies(issue['messages'])
    else:
      ret['replies'] = []
    ret['reviewers'] = set(r['author'] for r in ret['replies'])
    ret['reviewers'].discard(ret['author'])
    return ret

  @staticmethod
  def process_gerrit_rest_issue_replies(replies):
    ret = []
    replies = filter(lambda r: 'author' in r and 'email' in r['author'],
        replies)
    for reply in replies:
      ret.append({
        'author': reply['author']['email'],
        'created': datetime_from_gerrit(reply['date']),
        'content': reply['message'],
      })
    return ret

  def project_hosting_issue_search(self, instance):
    auth_config = auth.extract_auth_config_from_options(self.options)
    authenticator = auth.get_authenticator_for_host(
        "code.google.com", auth_config)
    http = authenticator.authorize(httplib2.Http())
    url = "https://www.googleapis.com/projecthosting/v2/projects/%s/issues" % (
       instance["name"])
    epoch = datetime.utcfromtimestamp(0)
    user_str = '%s@chromium.org' % self.user

    query_data = urllib.urlencode({
      'maxResults': 10000,
      'q': user_str,
      'publishedMax': '%d' % (self.modified_before - epoch).total_seconds(),
      'updatedMin': '%d' % (self.modified_after - epoch).total_seconds(),
    })
    url = url + '?' + query_data
    _, body = http.request(url)
    content = json.loads(body)
    if not content:
      print "Unable to parse %s response from projecthosting." % (
          instance["name"])
      return []

    issues = []
    if 'items' in content:
      items = content['items']
      for item in items:
        issue = {
          "header": item["title"],
          "created": item["published"],
          "modified": item["updated"],
          "author": item["author"]["name"],
          "url": "https://code.google.com/p/%s/issues/detail?id=%s" % (
              instance["name"], item["id"]),
          "comments": []
        }
        if 'owner' in item:
          issue['owner'] = item['owner']['name']
        else:
          issue['owner'] = 'None'
        if issue['owner'] == user_str or issue['author'] == user_str:
          issues.append(issue)

    return issues

  def print_heading(self, heading):
    print
    print self.options.output_format_heading.format(heading=heading)

  def print_change(self, change):
    optional_values = {
        'reviewers': ', '.join(change['reviewers'])
    }
    self.print_generic(self.options.output_format,
                       self.options.output_format_changes,
                       change['header'],
                       change['review_url'],
                       change['author'],
                       optional_values)

  def print_issue(self, issue):
    optional_values = {
        'owner': issue['owner'],
    }
    self.print_generic(self.options.output_format,
                       self.options.output_format_issues,
                       issue['header'],
                       issue['url'],
                       issue['author'],
                       optional_values)

  def print_review(self, review):
    self.print_generic(self.options.output_format,
                       self.options.output_format_reviews,
                       review['header'],
                       review['review_url'],
                       review['author'])

  @staticmethod
  def print_generic(default_fmt, specific_fmt,
                    title, url, author,
                    optional_values=None):
    output_format = specific_fmt if specific_fmt is not None else default_fmt
    output_format = unicode(output_format)
    required_values = {
        'title': title,
        'url': url,
        'author': author,
    }
    # Merge required and optional values.
    if optional_values is not None:
      values = dict(required_values.items() + optional_values.items())
    else:
      values = required_values
    print output_format.format(**values).encode(sys.getdefaultencoding())


  def filter_issue(self, issue, should_filter_by_user=True):
    def maybe_filter_username(email):
      return not should_filter_by_user or username(email) == self.user
    if (maybe_filter_username(issue['author']) and
        self.filter_modified(issue['created'])):
      return True
    if (maybe_filter_username(issue['owner']) and
        (self.filter_modified(issue['created']) or
         self.filter_modified(issue['modified']))):
      return True
    for reply in issue['replies']:
      if self.filter_modified(reply['created']):
        if not should_filter_by_user:
          break
        if (username(reply['author']) == self.user
            or (self.user + '@') in reply['content']):
          break
    else:
      return False
    return True

  def filter_modified(self, modified):
    return self.modified_after < modified and modified < self.modified_before

  def auth_for_changes(self):
    #TODO(cjhopman): Move authentication check for getting changes here.
    pass

  def auth_for_reviews(self):
    # Reviews use all the same instances as changes so no authentication is
    # required.
    pass

  def get_changes(self):
    for instance in rietveld_instances:
      self.changes += self.rietveld_search(instance, owner=self.user)

    for instance in gerrit_instances:
      self.changes += self.gerrit_search(instance, owner=self.user)

  def print_changes(self):
    if self.changes:
      self.print_heading('Changes')
      for change in self.changes:
        self.print_change(change)

  def get_reviews(self):
    for instance in rietveld_instances:
      self.reviews += self.rietveld_search(instance, reviewer=self.user)

    for instance in gerrit_instances:
      reviews = self.gerrit_search(instance, reviewer=self.user)
      reviews = filter(lambda r: not username(r['owner']) == self.user, reviews)
      self.reviews += reviews

  def print_reviews(self):
    if self.reviews:
      self.print_heading('Reviews')
      for review in self.reviews:
        self.print_review(review)

  def get_issues(self):
    for project in google_code_projects:
      self.issues += self.project_hosting_issue_search(project)

  def print_issues(self):
    if self.issues:
      self.print_heading('Issues')
      for issue in self.issues:
        self.print_issue(issue)

  def print_activity(self):
    self.print_changes()
    self.print_reviews()
    self.print_issues()


def main():
  # Silence upload.py.
  rietveld.upload.verbosity = 0

  parser = optparse.OptionParser(description=sys.modules[__name__].__doc__)
  parser.add_option(
      '-u', '--user', metavar='<email>',
      default=os.environ.get('USER'),
      help='Filter on user, default=%default')
  parser.add_option(
      '-b', '--begin', metavar='<date>',
      help='Filter issues created after the date (mm/dd/yy)')
  parser.add_option(
      '-e', '--end', metavar='<date>',
      help='Filter issues created before the date (mm/dd/yy)')
  quarter_begin, quarter_end = get_quarter_of(datetime.today() -
                                              relativedelta(months=2))
  parser.add_option(
      '-Q', '--last_quarter', action='store_true',
      help='Use last quarter\'s dates, i.e. %s to %s' % (
        quarter_begin.strftime('%Y-%m-%d'), quarter_end.strftime('%Y-%m-%d')))
  parser.add_option(
      '-Y', '--this_year', action='store_true',
      help='Use this year\'s dates')
  parser.add_option(
      '-w', '--week_of', metavar='<date>',
      help='Show issues for week of the date (mm/dd/yy)')
  parser.add_option(
      '-W', '--last_week', action='count',
      help='Show last week\'s issues. Use more times for more weeks.')
  parser.add_option(
      '-a', '--auth',
      action='store_true',
      help='Ask to authenticate for instances with no auth cookie')

  activity_types_group = optparse.OptionGroup(parser, 'Activity Types',
                               'By default, all activity will be looked up and '
                               'printed. If any of these are specified, only '
                               'those specified will be searched.')
  activity_types_group.add_option(
      '-c', '--changes',
      action='store_true',
      help='Show changes.')
  activity_types_group.add_option(
      '-i', '--issues',
      action='store_true',
      help='Show issues.')
  activity_types_group.add_option(
      '-r', '--reviews',
      action='store_true',
      help='Show reviews.')
  parser.add_option_group(activity_types_group)

  output_format_group = optparse.OptionGroup(parser, 'Output Format',
                              'By default, all activity will be printed in the '
                              'following format: {url} {title}. This can be '
                              'changed for either all activity types or '
                              'individually for each activity type. The format '
                              'is defined as documented for '
                              'string.format(...). The variables available for '
                              'all activity types are url, title and author. '
                              'Format options for specific activity types will '
                              'override the generic format.')
  output_format_group.add_option(
      '-f', '--output-format', metavar='<format>',
      default=u'{url} {title}',
      help='Specifies the format to use when printing all your activity.')
  output_format_group.add_option(
      '--output-format-changes', metavar='<format>',
      default=None,
      help='Specifies the format to use when printing changes. Supports the '
      'additional variable {reviewers}')
  output_format_group.add_option(
      '--output-format-issues', metavar='<format>',
      default=None,
      help='Specifies the format to use when printing issues. Supports the '
           'additional variable {owner}.')
  output_format_group.add_option(
      '--output-format-reviews', metavar='<format>',
      default=None,
      help='Specifies the format to use when printing reviews.')
  output_format_group.add_option(
      '--output-format-heading', metavar='<format>',
      default=u'{heading}:',
      help='Specifies the format to use when printing headings.')
  output_format_group.add_option(
      '-m', '--markdown', action='store_true',
      help='Use markdown-friendly output (overrides --output-format '
           'and --output-format-heading)')
  parser.add_option_group(output_format_group)
  auth.add_auth_options(parser)

  # Remove description formatting
  parser.format_description = (
      lambda _: parser.description)  # pylint: disable=E1101

  options, args = parser.parse_args()
  options.local_user = os.environ.get('USER')
  if args:
    parser.error('Args unsupported')
  if not options.user:
    parser.error('USER is not set, please use -u')

  options.user = username(options.user)

  if not options.begin:
    if options.last_quarter:
      begin, end = quarter_begin, quarter_end
    elif options.this_year:
      begin, end = get_year_of(datetime.today())
    elif options.week_of:
      begin, end = (get_week_of(datetime.strptime(options.week_of, '%m/%d/%y')))
    elif options.last_week:
      begin, end = (get_week_of(datetime.today() -
                                timedelta(days=1 + 7 * options.last_week)))
    else:
      begin, end = (get_week_of(datetime.today() - timedelta(days=1)))
  else:
    begin = datetime.strptime(options.begin, '%m/%d/%y')
    if options.end:
      end = datetime.strptime(options.end, '%m/%d/%y')
    else:
      end = datetime.today()
  options.begin, options.end = begin, end

  if options.markdown:
    options.output_format = ' * [{title}]({url})'
    options.output_format_heading = '### {heading} ###'

  print 'Searching for activity by %s' % options.user
  print 'Using range %s to %s' % (options.begin, options.end)

  my_activity = MyActivity(options)

  if not (options.changes or options.reviews or options.issues):
    options.changes = True
    options.issues = True
    options.reviews = True

  # First do any required authentication so none of the user interaction has to
  # wait for actual work.
  if options.changes:
    my_activity.auth_for_changes()
  if options.reviews:
    my_activity.auth_for_reviews()

  print 'Looking up activity.....'

  try:
    if options.changes:
      my_activity.get_changes()
    if options.reviews:
      my_activity.get_reviews()
    if options.issues:
      my_activity.get_issues()
  except auth.AuthenticationError as e:
    print "auth.AuthenticationError: %s" % e

  print '\n\n\n'

  my_activity.print_changes()
  my_activity.print_reviews()
  my_activity.print_issues()
  return 0


if __name__ == '__main__':
  # Fix encoding to support non-ascii issue titles.
  fix_encoding.fix_encoding()

  try:
    sys.exit(main())
  except KeyboardInterrupt:
    sys.stderr.write('interrupted\n')
    sys.exit(1)
