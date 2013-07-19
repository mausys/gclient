#!/bin/bash
# Copyright (c) 2013 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

if [ -n "$1" ]; then
  rundir="$1"
else
  rundir=$(mktemp -d)
fi

this_dir=$(dirname $0)
gerrit_exe="$this_dir/gerrit.war"

account_id=101
full_name='Test Account'
maximum_page_size='25'
password='test-password'
preferred_email="test-username@test.org"
registered_on=$(date '+%Y-%m-%d %H:%M:%S.000%:::z')
username='test-username'

# The python code below for picking the "latest" gerrit release is cribbed and
# ported from the javascript at:
#
#     http://gerrit-releases.storage.googleapis.com/index.html
url='https://www.googleapis.com/storage/v1beta2/b/gerrit-releases/o?projection=noAcl'
curl --ssl-reqd -s $url | python <(cat <<EOF
# Reads json-encoded text from stdin in the format:
#
#    {
#     "items": [
#      {
#       "name": "gerrit-<version>.war",
#       "md5Hash": "<base64 encoded md5sum>",
#      },
#      {
#       "name": "gerrit-<version>.war",
#       "md5Hash": "<base64 encoded md5sum>",
#      },
#      ...
#    }
#
# ...and prints the name and md5sum of the latest non-release-candidate version.

import json
import re
import sys

gerrit_re = re.compile('gerrit(?:-full)?-([0-9.]+(?:-rc[0-9]+)?)[.]war')
j = json.load(sys.stdin)
items = [(x, gerrit_re.match(x['name'])) for x in j['items']]
items = [(x, m.group(1)) for x, m in items if m]
def _cmp(a, b):
  an = a[1].replace('-rc', '.rc').split('.')
  bn = b[1].replace('-rc', '.rc').split('.')
  while len(an) < len(bn):
    an.append('0')
  while len(bn) < len(an):
    bn.append('0')
  for i in range(len(an)):
    ai = int(an[i][2:]) if 'rc' in an[i] else 1000 + int(an[i])
    bi = int(bn[i][2:]) if 'rc' in bn[i] else 1000 + int(bn[i])
    if ai != bi:
      return -1 if ai > bi else 1
  return 0
items.sort(cmp=_cmp)
for x in items:
  if 'rc' not in x[0]['name']:
    print '"%s" "%s"' % (x[0]['name'], x[0]['md5Hash'])
    sys.exit(0)
EOF
) | xargs | while read name md5; do
  # Download the latest gerrit version if necessary, and verify the md5sum.
  target="$this_dir/$name"
  net_sum=$(echo -n $md5 | base64 -d | od -tx1 | head -1 | cut -d ' ' -f 2- |
            sed 's/ //g')
  if [ -f "$target" ]; then
    file_sum=$(md5sum "$target" | awk '{print $1}' | xargs)
    if [ "$file_sum" = "$net_sum" ]; then
      ln -sf "$name" "$gerrit_exe"
      break
    else
      rm -rf "$target"
    fi
  fi
  curl --ssl-reqd -s -o "$target" \
      "https://gerrit-releases.storage.googleapis.com/$name"
  file_sum=$(md5sum "$target" | awk '{print $1}' | xargs)
  if [ "$file_sum" != "$net_sum" ]; then
    echo "ERROR: md5sum mismatch when downloading $name" 1>&2
    rm -rf "$target"
    exit 1
  else
    ln -sf "$name" "$gerrit_exe"
  fi
done

if [ ! -e "$gerrit_exe" ]; then
  echo "ERROR: No $gerrit_exe file or link present, and unable " 1>&2
  echo "       to download the latest version." 1>&2
  exit 1
fi

# By default, gerrit only accepts https connections, which is a good thing.  But
# for testing, it's convenient to enable plain http.
mkdir -p "${rundir}/etc"
cat <<EOF > "${rundir}/etc/gerrit.config"
[auth]
	type = http
	gitBasicAuth = true
EOF

# Initialize the gerrit instance.
java -jar "$gerrit_exe" init --no-auto-start --batch -d "${rundir}"

# Set up the first user, with admin priveleges.
cat <<EOF | java -jar "$gerrit_exe" gsql -d "${rundir}" > /dev/null
INSERT INTO ACCOUNTS (FULL_NAME, MAXIMUM_PAGE_SIZE, PREFERRED_EMAIL, REGISTERED_ON, ACCOUNT_ID) VALUES ('${full_name}', ${maximum_page_size}, '${preferred_email}', '${registered_on}', ${account_id});
INSERT INTO ACCOUNT_EXTERNAL_IDS (ACCOUNT_ID, EXTERNAL_ID) VALUES (${account_id}, 'gerrit:${username}');
INSERT INTO ACCOUNT_EXTERNAL_IDS (ACCOUNT_ID, EXTERNAL_ID) VALUES (${account_id}, 'username:${username}');
INSERT INTO ACCOUNT_EXTERNAL_IDS (ACCOUNT_ID, EMAIL_ADDRESS, PASSWORD) VALUES (${account_id}, '${preferred_email}', '${password}');
INSERT INTO ACCOUNT_GROUP_MEMBERS (ACCOUNT_ID, GROUP_ID) VALUES (${account_id}, 1);
EOF

# Create a netrc file to authenticate as the first user.
mkdir -p "${rundir}/tmp"
cat <<EOF > "${rundir}/tmp/.netrc"
machine localhost login ${username} password ${password}
EOF

# Create a .git-credentials file, to enable password-less push.
cat <<EOF > "${rundir}/tmp/.git-credentials"
http://${username}:${password}@localhost:8080
EOF

echo
echo "To start gerrit server:"
echo "  ${rundir}/bin/gerrit.sh start"
echo
echo "To use the REST API:"
echo "  curl --netrc-file ${rundir}/tmp/.netrc http://localhost:8080/<endpoint>"
echo
echo "To enable 'git push' without a password prompt:"
echo "  git config credential.helper 'store --file=${rundir}/tmp/.git-credentials'"
echo
echo "To stop the server:"
echo "  ${rundir}/bin/gerrit.sh stop"
echo
