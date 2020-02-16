#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2019 Bitergia
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
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
# Authors:
#     Santiago Dueñas <sduenas@bitergia.com>
#     Alvaro del Castillo <acs@bitergia.com>
#     Quan Zhou <quan@bitergia.com>
#

import re
import unittest

import httpretty

from perceval.backend import BackendError, BackendCommandArgumentParser
from perceval.backends.mozilla.remo import (ReMo,
                                            ReMoCommand,
                                            ReMoClient,
                                            MOZILLA_REPS_URL)
from base import TestCaseBackendArchive

MOZILLA_REPS_SERVER_URL = 'http://example.com'
MOZILLA_REPS_API = MOZILLA_REPS_SERVER_URL + '/api/remo/v1'

MOZILLA_REPS_CATEGORIES = ['events', 'activities', 'users']


def read_file(filename, mode='r'):
    with open(filename, mode) as f:
        content = f.read()
    return content


class HTTPServer():

    requests_http = []  # requests done to the server

    @classmethod
    def routes(cls, empty=False):
        """Configure in http the routes to be served"""

        mozilla_bodies = {}  # dict with all the bodies to be returned by category
        for category in MOZILLA_REPS_CATEGORIES:
            mozilla_bodies[category] = {}
            # First two pages for each category to test pagination
            mozilla_bodies[category]['1'] = read_file('data/remo/remo_' + category + '_page_1_2.json')
            mozilla_bodies[category]['2'] = read_file('data/remo/remo_' + category + '_page_2_2.json')
            # A sample item per each category
            mozilla_bodies[category]['item'] = read_file('data/remo/remo_' + category + '.json')

        if empty:
            for category in MOZILLA_REPS_CATEGORIES:
                mozilla_bodies[category]['1'] = read_file('data/remo/remo_' + category + '_page_empty.json')

        def request_callback(method, uri, headers):
            body = ''
            if 'page' in uri:
                # Page with item list query
                page = uri.split("page=")[1].split("&")[0]
                for category in MOZILLA_REPS_CATEGORIES:
                    if category in uri:
                        body = mozilla_bodies[category][page]
                        break
            else:
                # Specific item. Always return the same for each category.
                for category in MOZILLA_REPS_CATEGORIES:
                    if category in uri:
                        body = mozilla_bodies[category]['item']
                        break

            HTTPServer.requests_http.append(httpretty.last_request())

            return (200, headers, body)

        httpretty.register_uri(httpretty.GET,
                               re.compile(MOZILLA_REPS_API + ".*"),
                               responses=[
                                   httpretty.Response(body=request_callback)
                               ])


class TestReMoBackend(unittest.TestCase):
    """ReMo backend tests"""

    def test_initialization(self):
        """Test whether attributes are initializated"""

        remo = ReMo(MOZILLA_REPS_SERVER_URL, tag='test')

        self.assertEqual(remo.url, MOZILLA_REPS_SERVER_URL)
        self.assertEqual(remo.origin, MOZILLA_REPS_SERVER_URL)
        self.assertEqual(remo.tag, 'test')
        self.assertIsNone(remo.client)
        self.assertTrue(remo.ssl_verify)

        # When tag is empty or None it will be set to
        # the value in url
        remo = ReMo(MOZILLA_REPS_SERVER_URL, ssl_verify=False)
        self.assertEqual(remo.url, MOZILLA_REPS_SERVER_URL)
        self.assertEqual(remo.origin, MOZILLA_REPS_SERVER_URL)
        self.assertEqual(remo.tag, MOZILLA_REPS_SERVER_URL)
        self.assertFalse(remo.ssl_verify)

        remo = ReMo(MOZILLA_REPS_SERVER_URL, tag='')
        self.assertEqual(remo.url, MOZILLA_REPS_SERVER_URL)
        self.assertEqual(remo.origin, MOZILLA_REPS_SERVER_URL)
        self.assertEqual(remo.tag, MOZILLA_REPS_SERVER_URL)
        self.assertTrue(remo.ssl_verify)

        # If no url is provided, MOZILLA_REPS_URL is used
        remo = ReMo()
        self.assertEqual(remo.url, MOZILLA_REPS_URL)
        self.assertEqual(remo.origin, MOZILLA_REPS_URL)
        self.assertEqual(remo.tag, MOZILLA_REPS_URL)

    def test_has_archiving(self):
        """Test if it returns True when has_archiving is called"""

        self.assertEqual(ReMo.has_archiving(), True)

    def test_has_resuming(self):
        """Test if it returns True when has_resuming is called"""

        self.assertEqual(ReMo.has_resuming(), True)

    def __check_events_contents(self, items):
        self.assertEqual(items[0]['data']['city'], 'Makassar')
        self.assertEqual(items[0]['data']['end'], '2012-06-10T11:00:00Z')
        self.assertEqual(items[0]['origin'], MOZILLA_REPS_SERVER_URL)
        self.assertEqual(items[0]['uuid'], 'e701d4ed3b954361383d678d2168a44307d7ff60')
        self.assertEqual(items[0]['updated_on'], 1339326000.0)
        self.assertEqual(items[0]['category'], 'event')
        self.assertEqual(items[0]['tag'], MOZILLA_REPS_SERVER_URL)
        self.assertEqual(items[0]['offset'], 0)
        self.assertEqual(items[3]['offset'], 3)

    def __check_activities_contents(self, items):
        self.assertEqual(items[0]['data']['location'], 'Bhopal, Madhya Pradesh, India')
        self.assertEqual(items[0]['data']['report_date'], '2016-11-05')
        self.assertEqual(items[0]['origin'], MOZILLA_REPS_SERVER_URL)
        self.assertEqual(items[0]['uuid'], '9e2b0c2c8ec8094d2c53a2621bd09f9d6f65e67f')
        self.assertEqual(items[0]['updated_on'], 1478304000.0)
        self.assertEqual(items[0]['category'], 'activity')
        self.assertEqual(items[0]['tag'], MOZILLA_REPS_SERVER_URL)
        self.assertEqual(items[0]['offset'], 0)
        self.assertEqual(items[3]['offset'], 3)

    def __check_users_contents(self, items):
        self.assertEqual(items[0]['data']['city'], 'Makati City')
        self.assertEqual(items[0]['data']['date_joined_program'], '2011-06-01')
        self.assertEqual(items[0]['origin'], MOZILLA_REPS_SERVER_URL)
        self.assertEqual(items[0]['uuid'], '90b0f5bc90ed8a694261df418a2b85beed94535a')
        self.assertEqual(items[0]['updated_on'], 1306886400.0)
        self.assertEqual(items[0]['category'], 'user')
        self.assertEqual(items[0]['tag'], MOZILLA_REPS_SERVER_URL)
        self.assertEqual(items[0]['offset'], 0)
        self.assertEqual(items[3]['offset'], 3)

    @httpretty.activate
    def __test_fetch(self, category='event'):
        """Test whether the events are returned"""

        items_page = ReMoClient.ITEMS_PER_PAGE
        pages = 2  # two pages of testing data

        HTTPServer.routes()
        prev_requests_http = len(HTTPServer.requests_http)

        # Test fetch events with their reviews
        remo = ReMo(MOZILLA_REPS_SERVER_URL)

        items = [page for page in remo.fetch(offset=None, category=category)]

        self.assertEqual(len(items), items_page * pages)

        if category == 'event':
            self.__check_events_contents(items)
        elif category == 'user':
            self.__check_users_contents(items)
        elif category == 'activity':
            self.__check_activities_contents(items)

        # Check requests: page list, items, page list, items
        expected = [{'page': ['1'], 'orderby': ['ASC']}]
        for i in range(0, items_page):
            expected += [{}]
        expected += [{'page': ['2'], 'orderby': ['ASC']}]
        for i in range(0, items_page):
            expected += [{}]

        self.assertEqual(len(HTTPServer.requests_http) - prev_requests_http, len(expected))

        for i in range(len(expected)):
            self.assertDictEqual(HTTPServer.requests_http[i].querystring, expected[i])

    @httpretty.activate
    def __test_search_terms(self, category='event'):
        """Test whether the search_fields is properly set"""

        items_page = ReMoClient.ITEMS_PER_PAGE
        pages = 2  # two pages of testing data

        HTTPServer.routes()

        # Test fetch events with their reviews
        remo = ReMo(MOZILLA_REPS_SERVER_URL)

        items = [page for page in remo.fetch(offset=None, category=category)]

        for item in items:
            self.assertEqual(remo.metadata_id(item['data']), item['search_fields']['item_id'])

    def test_fetch_events(self):
        self.__test_fetch(category='event')

    def test_fetch_activities(self):
        self.__test_fetch(category='activity')

    def test_fetch_users(self):
        self.__test_fetch(category='user')

    def test_search_terms_events(self):
        self.__test_search_terms(category='event')

    def test_search_terms_activities(self):
        self.__test_search_terms(category='activity')

    def test_search_terms_users(self):
        self.__test_search_terms(category='user')

    @httpretty.activate
    def tests_wrong_metadata_updated_on(self):

        HTTPServer.routes()
        prev_requests_http = len(HTTPServer.requests_http)

        # Test fetch events with their reviews
        remo = ReMo(MOZILLA_REPS_SERVER_URL)

        items = [page for page in remo.fetch(offset=None, category="event")]
        item = items[0]

        item.pop('end', None)

        with self.assertRaises(ValueError):
            remo.metadata_updated_on(item)

    @httpretty.activate
    def tests_wrong_metadata_category(self):

        HTTPServer.routes()
        prev_requests_http = len(HTTPServer.requests_http)

        # Test fetch events with their reviews
        remo = ReMo(MOZILLA_REPS_SERVER_URL)

        items = [page for page in remo.fetch(offset=None, category="event")]
        item = items[0]

        item.pop('estimated_attendance', None)

        with self.assertRaises(TypeError):
            remo.metadata_category(item)

    @httpretty.activate
    def test_fetch_offset(self):
        items_page = ReMoClient.ITEMS_PER_PAGE
        pages = 2  # two pages of testing data
        offset = 15

        HTTPServer.routes()
        prev_requests_http = len(HTTPServer.requests_http)

        # Test fetch events with their reviews
        remo = ReMo(MOZILLA_REPS_SERVER_URL)

        # Test we get the correct number of items from an offset
        items = [page for page in remo.fetch(offset=15)]
        self.assertEqual(len(items), (items_page * pages) - offset)

        # Test that the same offset (17) is the same item
        items = [page for page in remo.fetch(offset=5)]
        uuid_17_1 = items[12]['uuid']
        self.assertEqual(items[12]['offset'], 17)
        items = [page for page in remo.fetch(offset=12)]
        uuid_17_2 = items[5]['uuid']
        self.assertEqual(items[5]['offset'], 17)
        self.assertEqual(uuid_17_1, uuid_17_2)

    def test_fetch_wrong_category(self):
        with self.assertRaises(BackendError):
            self.__test_fetch(category='wrong')

    @httpretty.activate
    def test_fetch_empty(self):
        """Test whether it works when no items are fetched"""

        HTTPServer.routes(empty=True)

        remo = ReMo(MOZILLA_REPS_SERVER_URL)
        events = [event for event in remo.fetch()]

        self.assertEqual(len(events), 0)


class TestRemoBackendArchive(TestCaseBackendArchive):
    """Remo backend tests using an archive"""

    def setUp(self):
        super().setUp()
        self.backend_write_archive = ReMo(MOZILLA_REPS_SERVER_URL, archive=self.archive)
        self.backend_read_archive = ReMo(MOZILLA_REPS_SERVER_URL, archive=self.archive)

    @httpretty.activate
    def __test_fetch_from_archive(self, category='event'):
        """Test whether the events are returned from archive"""

        HTTPServer.routes()
        self._test_fetch_from_archive(category=category)

    def test_fetch_events(self):
        self.__test_fetch_from_archive(category='event')

    def test_fetch_activities(self):
        self.__test_fetch_from_archive(category='activity')

    def test_fetch_users(self):
        self.__test_fetch_from_archive(category='user')

    @httpretty.activate
    def test_fetch_offset_from_archive_15(self):
        """Test whether the events with offset are returned from archive"""

        HTTPServer.routes()
        self._test_fetch_from_archive(offset=15)

    @httpretty.activate
    def test_fetch_offset_from_archive_5(self):
        """Test whether the events with offset are returned from archive"""

        HTTPServer.routes()
        self._test_fetch_from_archive(offset=5)

    @httpretty.activate
    def test_fetch_empty_from_archive(self):
        """Test whether it works when no items are fetched from archive"""

        HTTPServer.routes(empty=True)
        self._test_fetch_from_archive()


class TestReMoCommand(unittest.TestCase):
    """Tests for ReMoCommand class"""

    def test_backend_class(self):
        """Test if the backend class is ReMo"""

        self.assertIs(ReMoCommand.BACKEND, ReMo)

    def test_setup_cmd_parser(self):
        """Test if it parser object is correctly initialized"""

        parser = ReMoCommand.setup_cmd_parser()
        self.assertIsInstance(parser, BackendCommandArgumentParser)
        self.assertEqual(parser._backend, ReMo)

        args = [MOZILLA_REPS_SERVER_URL,
                '--category', 'user',
                '--tag', 'test',
                '--no-archive',
                '--offset', '88']

        parsed_args = parser.parse(*args)
        self.assertEqual(parsed_args.url, MOZILLA_REPS_SERVER_URL)
        self.assertEqual(parsed_args.category, 'user')
        self.assertEqual(parsed_args.tag, 'test')
        self.assertEqual(parsed_args.no_archive, True)
        self.assertEqual(parsed_args.offset, 88)
        self.assertTrue(parsed_args.ssl_verify)

        args = [MOZILLA_REPS_SERVER_URL, '--no-ssl-verify']

        parsed_args = parser.parse(*args)
        self.assertEqual(parsed_args.url, MOZILLA_REPS_SERVER_URL)
        self.assertFalse(parsed_args.ssl_verify)


class TestReMoClient(unittest.TestCase):
    """ReMo API client tests

    These tests not check the body of the response, only if the call
    was well formed and if a response was obtained. Due to this, take
    into account that the body returned on each request might not
    match with the parameters from the request.
    """

    def test_init(self):
        """Test initialization"""

        remo = ReMoClient(MOZILLA_REPS_SERVER_URL)

        self.assertEqual(remo.base_url, MOZILLA_REPS_SERVER_URL)
        self.assertIsNone(remo.archive)
        self.assertFalse(remo.from_archive)
        self.assertTrue(remo.ssl_verify)

        remo = ReMoClient(MOZILLA_REPS_SERVER_URL, ssl_verify=False)

        self.assertEqual(remo.base_url, MOZILLA_REPS_SERVER_URL)
        self.assertIsNone(remo.archive)
        self.assertFalse(remo.from_archive)
        self.assertFalse(remo.ssl_verify)

    @httpretty.activate
    def test_get_items(self):
        """Test get_events API call"""

        HTTPServer.routes()

        # Set up a mock HTTP server
        body = read_file('data/remo/remo_events_page_1_2.json')
        client = ReMoClient(MOZILLA_REPS_SERVER_URL)
        response = next(client.get_items())
        req = HTTPServer.requests_http[-1]
        self.assertEqual(response, body)
        self.assertEqual(req.method, 'GET')
        self.assertRegex(req.path, '/api/remo/v1/events/')
        self.assertDictEqual(req.querystring, {'page': ['1'], 'orderby': ['ASC']})

    @httpretty.activate
    def test_get_wrong_items(self):
        """Test get_events API call"""

        HTTPServer.routes()

        # Set up a mock HTTP server
        body = read_file('data/remo/remo_events_page_1_2.json')
        client = ReMoClient(MOZILLA_REPS_SERVER_URL)

        with self.assertRaises(ValueError):
            _ = next(client.get_items(category='wrong'))

    @httpretty.activate
    def test_call(self):
        """Test get_all_users API call"""

        HTTPServer.routes()

        # Set up a mock HTTP server
        body = read_file('data/remo/remo_events_page_1_2.json')
        client = ReMoClient(MOZILLA_REPS_SERVER_URL)
        response = client.fetch(MOZILLA_REPS_API + '/events/?page=1')
        req = HTTPServer.requests_http[-1]
        self.assertEqual(response, body)
        self.assertEqual(req.method, 'GET')
        self.assertEqual(req.path, '/api/remo/v1/events/?page=1')
        # Check request params
        expected = {
            'page': ['1']
        }
        self.assertDictEqual(req.querystring, expected)


if __name__ == "__main__":
    unittest.main(warnings='ignore')
