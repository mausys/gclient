#!/usr/bin/env python

"""Tests for git_footers."""

import os
import StringIO
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from testing_support.auto_stub import TestCase

import git_footers

class GitFootersTest(TestCase):
  _message = """
This is my commit message. There are many like it, but this one is mine.

My commit message is my best friend. It is my life. I must master it.

"""

  _position = 'refs/heads/master@{#292272}'

  _position_footer = 'Cr-Commit-Position: %s\n' % _position

  def testFootersBasic(self):
    self.assertEqual(
        git_footers.split_footers('Not-A: footer'),
        (['Not-A: footer'], [], []))
    self.assertEqual(
        git_footers.split_footers('Header\n\nActual: footer'),
        (['Header', ''], ['Actual: footer'], [('Actual', 'footer')]))
    self.assertEqual(
        git_footers.split_footers('\nActual: footer'),
        ([''], ['Actual: footer'], [('Actual', 'footer')]))
    self.assertEqual(
        git_footers.split_footers('H\n\nBug:\nAlso: footer'),
        (['H', ''], ['Bug:', 'Also: footer'],
         [('Bug', ''), ('Also', 'footer')]))
    self.assertEqual(
        git_footers.split_footers('H\n\nBug:      '),
        (['H', ''], ['Bug:      '], [('Bug', '')]))

    self.assertEqual(
        git_footers.parse_footers(self._message), {})
    self.assertEqual(
        git_footers.parse_footers(self._message + self._position_footer),
        { 'Cr-Commit-Position': [ self._position ] })
    self.assertEqual(
        git_footers.parse_footers(self._message + self._position_footer
                                                + self._position_footer),
        { 'Cr-Commit-Position': [ self._position, self._position ] })
    self.assertEqual(
        git_footers.parse_footers(self._message +
                                  'Bug:\n' +
                                  self._position_footer),
        { 'Bug': [''],
          'Cr-Commit-Position': [ self._position ] })

  def testSkippingBadFooterLines(self):
    message = ('Title.\n'
               '\n'
               'Last: paragraph starts\n'
               'It-may: contain\n'
               'bad lines, which should be skipped\n'
               'For: example\n'
               '(cherry picked from)\n'
               'And-only-valid: footers taken')
    self.assertEqual(git_footers.split_footers(message),
                     (['Title.',
                       ''],
                      ['Last: paragraph starts',
                       'It-may: contain',
                       'bad lines, which should be skipped',
                       'For: example',
                       '(cherry picked from)',
                       'And-only-valid: footers taken'],
                      [('Last', 'paragraph starts'),
                       ('It-may', 'contain'),
                       ('For', 'example'),
                       ('And-only-valid', 'footers taken')]))
    self.assertEqual(git_footers.parse_footers(message),
                     {'Last': ['paragraph starts'],
                      'It-May': ['contain'],
                      'For': ['example'],
                      'And-Only-Valid': ['footers taken']})

  def testGetFooterChangeId(self):
    msg = '\n'.join(['whatever',
                     '',
                     'Change-Id: ignored',
                     '',  # Above is ignored because of this empty line.
                     'Change-Id: Ideadbeaf'])
    self.assertEqual(['Ideadbeaf'], git_footers.get_footer_change_id(msg))
    self.assertEqual([], git_footers.get_footer_change_id(
        'desc\nBUG=not-a-valid-footer\nChange-Id: Ixxx'))
    self.assertEqual(['Ixxx'], git_footers.get_footer_change_id(
        'desc\nBUG=not-a-valid-footer\n\nChange-Id: Ixxx'))

  def testAddFooterChangeId(self):
    with self.assertRaises(AssertionError):
      git_footers.add_footer_change_id('Already has\n\nChange-Id: Ixxx', 'Izzz')

    self.assertEqual(
        git_footers.add_footer_change_id('header-only', 'Ixxx'),
        'header-only\n\nChange-Id: Ixxx')

    self.assertEqual(
        git_footers.add_footer_change_id('header\n\nsome: footer', 'Ixxx'),
        'header\n\nsome: footer\nChange-Id: Ixxx')

    self.assertEqual(
        git_footers.add_footer_change_id('header\n\nBUG: yy', 'Ixxx'),
        'header\n\nBUG: yy\nChange-Id: Ixxx')

    self.assertEqual(
        git_footers.add_footer_change_id('header\n\nBUG: yy\nPos: 1', 'Ixxx'),
        'header\n\nBUG: yy\nChange-Id: Ixxx\nPos: 1')

    self.assertEqual(
        git_footers.add_footer_change_id('header\n\nBUG: yy\n\nPos: 1', 'Ixxx'),
        'header\n\nBUG: yy\n\nPos: 1\nChange-Id: Ixxx')

    # Special case: first line is never a footer, even if it looks line one.
    self.assertEqual(
        git_footers.add_footer_change_id('header: like footer', 'Ixxx'),
        'header: like footer\n\nChange-Id: Ixxx')

  def testAddFooter(self):
    self.assertEqual(
        git_footers.add_footer('', 'Key', 'Value'),
        '\nKey: Value')

    self.assertEqual(
        git_footers.add_footer('Header with empty line.\n\n', 'Key', 'Value'),
        'Header with empty line.\n\nKey: Value')

    self.assertEqual(
        git_footers.add_footer('Top\n\nSome: footer', 'Key', 'value'),
        'Top\n\nSome: footer\nKey: value')

    self.assertEqual(
        git_footers.add_footer('Top\n\nSome: footer', 'Key', 'value',
                               after_keys=['Any']),
        'Top\n\nSome: footer\nKey: value')

    self.assertEqual(
        git_footers.add_footer('Top\n\nSome: footer', 'Key', 'value',
                               after_keys=['Some']),
        'Top\n\nSome: footer\nKey: value')

    self.assertEqual(
         git_footers.add_footer('Top\n\nSome: footer\nOther: footer',
                                'Key', 'value', after_keys=['Some']),
         'Top\n\nSome: footer\nKey: value\nOther: footer')

    self.assertEqual(
         git_footers.add_footer('Top\n\nSome: footer\nOther: footer',
                                'Key', 'value', before_keys=['Other']),
         'Top\n\nSome: footer\nKey: value\nOther: footer')

    self.assertEqual(
        git_footers.add_footer(
              'Top\n\nSome: footer\nOther: footer\nFinal: footer',
              'Key', 'value', after_keys=['Some'], before_keys=['Final']),
        'Top\n\nSome: footer\nKey: value\nOther: footer\nFinal: footer')

    self.assertEqual(
        git_footers.add_footer(
              'Top\n\nSome: footer\nOther: footer\nFinal: footer',
              'Key', 'value', after_keys=['Other'], before_keys=['Some']),
        'Top\n\nSome: footer\nOther: footer\nKey: value\nFinal: footer')

  def testRemoveFooter(self):
    self.assertEqual(
        git_footers.remove_footer('message', 'Key'),
        'message')

    self.assertEqual(
        git_footers.remove_footer('message\n\nSome: footer', 'Key'),
        'message\n\nSome: footer')

    self.assertEqual(
        git_footers.remove_footer('message\n\nSome: footer\nKey: value', 'Key'),
        'message\n\nSome: footer')

    self.assertEqual(
        git_footers.remove_footer(
            'message\n\nKey: value\nSome: footer\nKey: value', 'Key'),
        'message\n\nSome: footer')


  def testReadStdin(self):
    self.mock(git_footers.sys, 'stdin', StringIO.StringIO(
        'line\r\notherline\r\n\r\n\r\nFoo: baz'))

    stdout = StringIO.StringIO()
    self.mock(git_footers.sys, 'stdout', stdout)

    self.assertEqual(git_footers.main([]), 0)
    self.assertEqual(stdout.getvalue(), "Foo: baz\n")



if __name__ == '__main__':
  unittest.main()
