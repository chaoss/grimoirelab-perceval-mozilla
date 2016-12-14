#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2016 Bitergia
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# Authors:
#     Santiago Dueñas <sduenas@bitergia.com>
#     Alvaro del Castillo <acs@bitergia.com>
#

import argparse
import json
import shutil
import sys
import tempfile
import unittest

import httpretty
import pkg_resources

# Hack to make sure that tests import the right packages
# due to setuptools behaviour
sys.path.insert(0, '..')
pkg_resources.declare_namespace('perceval.backends')

from perceval.cache import Cache
from perceval.errors import CacheError
from perceval.backends.mozilla.mozillaclub import MozillaClub, MozillaClubCommand, MozillaClubClient


MozillaClub_FEED_URL = 'http://example.com/feed'

requests_http = []

def read_file(filename, mode='r'):
    with open(filename, mode) as f:
        content = f.read()
    return content

def configure_http_server():
    bodies_entries_job = read_file('data/mozillaclub/feed.json')

    http_requests = []

    def request_callback(method, uri, headers):
        last_request = httpretty.last_request()

        if uri.startswith(MozillaClub_FEED_URL):
            body = bodies_entries_job
        else:
            body = ''

        requests_http.append(httpretty.last_request())

        http_requests.append(last_request)

        return (200, headers, body)

    httpretty.register_uri(httpretty.GET,
                           MozillaClub_FEED_URL,
                           responses=[
                                httpretty.Response(body=request_callback) \
                                for _ in range(2)
                           ])

    return http_requests


class TestMozillaClubBackend(unittest.TestCase):
    """MozillaClub backend tests"""

    def test_initialization(self):
        """Test whether attributes are initializated"""

        mozillaclub = MozillaClub(MozillaClub_FEED_URL, tag='test')

        self.assertEqual(mozillaclub.url, MozillaClub_FEED_URL)
        self.assertEqual(mozillaclub.origin, MozillaClub_FEED_URL)
        self.assertEqual(mozillaclub.tag, 'test')
        self.assertIsInstance(mozillaclub.client, MozillaClubClient)

        # When tag is empty or None it will be set to
        # the value in url
        mozillaclub = MozillaClub(MozillaClub_FEED_URL)
        self.assertEqual(mozillaclub.url, MozillaClub_FEED_URL)
        self.assertEqual(mozillaclub.origin, MozillaClub_FEED_URL)
        self.assertEqual(mozillaclub.tag, MozillaClub_FEED_URL)

        mozillaclub = MozillaClub(MozillaClub_FEED_URL, tag='')
        self.assertEqual(mozillaclub.url, MozillaClub_FEED_URL)
        self.assertEqual(mozillaclub.origin, MozillaClub_FEED_URL)
        self.assertEqual(mozillaclub.tag, MozillaClub_FEED_URL)

    def test_has_caching(self):
        """Test if it returns True when has_caching is called"""

        self.assertEqual(MozillaClub.has_caching(), True)

    def test_has_resuming(self):
        """Test if it returns False when has_resuming is called"""

        self.assertEqual(MozillaClub.has_resuming(), False)

    @httpretty.activate
    def test_fetch(self):
        """Test whether a list of entries is returned"""

        http_requests = configure_http_server()

        # Test fetch entries from feed
        mozillaclub = MozillaClub(MozillaClub_FEED_URL)
        entries = [entry for entry in mozillaclub.fetch()]
        self.assertEqual(len(entries), 92)
        self.assertEqual(len(http_requests), 1)

        # Test metadata
        expected = [('a60e67f5094f325f1cc826159749eaecbd177fc9', 1460937600.0,
                     'Rio Mozilla Club'),
                    ('2e6eaf1f174600d20233e5051e85d730952a8a31', 1460592000.0,
                     'Firefox club uog-skt'),
                    ('da8820deeb01616d22d6851272e8db915efc351b', 1460764800.0,
                     'Mozilla HETEC Club')]

        for x in range(len(expected)):
            entry = entries[x]
            self.assertEqual(entry['origin'], 'http://example.com/feed')
            self.assertEqual(entry['uuid'], expected[x][0])
            self.assertEqual(entry['updated_on'], expected[x][1])
            self.assertEqual(entry['category'], 'event')
            self.assertEqual(entry['tag'], 'http://example.com/feed')
            self.assertEqual(entry['data']['Club Name'], expected[x][2])

    @httpretty.activate
    def test_fetch_empty(self):
        """Test whether it works when no entries are fetched"""

        body = """
            {
                "encoding": "UTF-8",
                "feed": {
                "entry": []
                }
            }
        """
        httpretty.register_uri(httpretty.GET,
                               MozillaClub_FEED_URL,
                               body=body, status=200)

        mozillaclub = MozillaClub(MozillaClub_FEED_URL)
        entries = [entry for entry in mozillaclub.fetch()]

        self.assertEqual(len(entries), 0)


class TestMozillaClubBackendCache(unittest.TestCase):
    """MozillaClub backend tests using a cache"""

    def setUp(self):
        self.tmp_path = tempfile.mkdtemp(prefix='perceval_')

    def tearDown(self):
        shutil.rmtree(self.tmp_path)

    @httpretty.activate
    def test_fetch_from_cache(self):
        """Test whether the cache works"""

        http_requests = configure_http_server()

        # First, we fetch the entries from the server, storing them
        # in a cache
        cache = Cache(self.tmp_path)
        mozillaclub = MozillaClub(MozillaClub_FEED_URL, cache=cache)

        entries = [entry for entry in mozillaclub.fetch()]
        self.assertEqual(len(http_requests), 1)

        # Now, we get the entries from the cache.
        # The contents should be the same and there won't be
        # any new request to the server
        cached_entries = [entry for entry in mozillaclub.fetch_from_cache()]
        self.assertEqual(len(cached_entries), len(entries))
        self.assertEqual(len(http_requests), 1)  # no more requests done

    def test_fetch_from_empty_cache(self):
        """Test if there are not any entries returned when the cache is empty"""

        cache = Cache(self.tmp_path)
        mozillaclub = MozillaClub(MozillaClub_FEED_URL, cache=cache)
        cached_entries = [entry for entry in mozillaclub.fetch_from_cache()]
        self.assertEqual(len(cached_entries), 0)

    def test_fetch_from_non_set_cache(self):
        """Test if a error is raised when the cache was not set"""

        mozillaclub = MozillaClub(MozillaClub_FEED_URL)

        with self.assertRaises(CacheError):
            _ = [entry for entry in mozillaclub.fetch_from_cache()]


class TestMozillaClubCommand(unittest.TestCase):

    @httpretty.activate
    def test_parsing_on_init(self):
        """Test if the class is initialized"""

        args = ['--tag', 'test', MozillaClub_FEED_URL]

        cmd = MozillaClubCommand(*args)
        self.assertIsInstance(cmd.parsed_args, argparse.Namespace)
        self.assertEqual(cmd.parsed_args.url, MozillaClub_FEED_URL)
        self.assertEqual(cmd.parsed_args.tag, 'test')
        self.assertIsInstance(cmd.backend, MozillaClub)

    def test_argument_parser(self):
        """Test if it returns a argument parser object"""

        parser = MozillaClubCommand.create_argument_parser()
        self.assertIsInstance(parser, argparse.ArgumentParser)


class TestMozillaClubClient(unittest.TestCase):
    """MozillaClub API client tests

    These tests not check the body of the response, only if the call
    was well formed and if a response was obtained. Due to this, take
    into account that the body returned on each request might not
    match with the parameters from the request.
    """
    @httpretty.activate
    def test_init(self):
        """Test initialization"""
        client = MozillaClubClient(MozillaClub_FEED_URL)

    @httpretty.activate
    def test_get_entries(self):
        """Test get_entries API call"""

        # Set up a mock HTTP server
        body = read_file('data/mozillaclub/feed.json')
        httpretty.register_uri(httpretty.GET,
                               MozillaClub_FEED_URL,
                               body=body, status=200)

        client = MozillaClubClient(MozillaClub_FEED_URL)
        response = client.get_cells()

        self.assertEqual(response, body)


if __name__ == "__main__":
    unittest.main(warnings='ignore')
