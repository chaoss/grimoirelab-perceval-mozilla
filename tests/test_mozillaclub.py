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

import unittest

import httpretty

from perceval.backend import BackendCommandArgumentParser
from perceval.backends.mozilla.mozillaclub import (MozillaClub,
                                                   MozillaClubCommand,
                                                   MozillaClubClient,
                                                   MozillaClubParser)
from base import TestCaseBackendArchive


MozillaClub_FEED_URL = 'http://example.com/feed'

requests_http = []


def read_file(filename, mode='r'):
    with open(filename, mode) as f:
        content = f.read()
    return content


def configure_http_server():
    bodies_events_job = read_file('data/mozillaclub/feed.json')

    http_requests = []

    def request_callback(method, uri, headers):
        last_request = httpretty.last_request()

        if uri.startswith(MozillaClub_FEED_URL):
            body = bodies_events_job
        else:
            body = ''

        requests_http.append(httpretty.last_request())

        http_requests.append(last_request)

        return (200, headers, body)

    httpretty.register_uri(httpretty.GET,
                           MozillaClub_FEED_URL,
                           responses=[
                               httpretty.Response(body=request_callback)
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
        self.assertIsNone(mozillaclub.client)
        self.assertTrue(mozillaclub.ssl_verify)

        # When tag is empty or None it will be set to
        # the value in url
        mozillaclub = MozillaClub(MozillaClub_FEED_URL, ssl_verify=False)
        self.assertEqual(mozillaclub.url, MozillaClub_FEED_URL)
        self.assertEqual(mozillaclub.origin, MozillaClub_FEED_URL)
        self.assertEqual(mozillaclub.tag, MozillaClub_FEED_URL)
        self.assertFalse(mozillaclub.ssl_verify)

        mozillaclub = MozillaClub(MozillaClub_FEED_URL, tag='')
        self.assertEqual(mozillaclub.url, MozillaClub_FEED_URL)
        self.assertEqual(mozillaclub.origin, MozillaClub_FEED_URL)
        self.assertEqual(mozillaclub.tag, MozillaClub_FEED_URL)
        self.assertTrue(mozillaclub.ssl_verify)

    def test_has_archiving(self):
        """Test if it returns True when has_archiving is called"""

        self.assertEqual(MozillaClub.has_archiving(), True)

    def test_has_resuming(self):
        """Test if it returns False when has_resuming is called"""

        self.assertEqual(MozillaClub.has_resuming(), False)

    @httpretty.activate
    def test_fetch(self):
        """Test whether a list of events is returned"""

        http_requests = configure_http_server()

        # Test fetch events from feed
        mozillaclub = MozillaClub(MozillaClub_FEED_URL)
        events = [event for event in mozillaclub.fetch()]
        self.assertEqual(len(events), 92)
        self.assertEqual(len(http_requests), 1)

        # Test metadata
        expected = [('a60e67f5094f325f1cc826159749eaecbd177fc9', 1481643844.821,
                     'Rio Mozilla Club'),
                    ('2e6eaf1f174600d20233e5051e85d730952a8a31', 1481643844.821,
                     'Firefox club uog-skt'),
                    ('da8820deeb01616d22d6851272e8db915efc351b', 1481643844.821,
                     'Mozilla HETEC Club')]

        for x in range(len(expected)):
            event = events[x]
            self.assertEqual(event['origin'], 'http://example.com/feed')
            self.assertEqual(event['uuid'], expected[x][0])
            self.assertEqual(event['updated_on'], expected[x][1])
            self.assertEqual(event['category'], 'event')
            self.assertEqual(event['tag'], 'http://example.com/feed')
            self.assertEqual(event['data']['Club Name'], expected[x][2])

    @httpretty.activate
    def test_empty_cells(self):
        """
        Test whether the empty fields cells that are not included in the json
        feed, are filled with None in the generated event.
        """

        http_requests = configure_http_server()

        # https://docs.google.com/spreadsheets/d/1QHl2bjBhMslyFzR5XXPzMLdzzx7oeSKTbgR5PM8qp64/pubhtml
        # Club Link is always empty so it is not included in
        # https://spreadsheets.google.com/feeds/cells/1QHl2bjBhMslyFzR5XXPzMLdzzx7oeSKTbgR5PM8qp64/ohaibtm/public/values?alt=json
        # Check that the field 'Club Link' exist in the items with None value

        mozillaclub = MozillaClub(MozillaClub_FEED_URL)
        events = [event for event in mozillaclub.fetch()]
        self.assertEqual(len(events), 92)
        for event in events:
            self.assertEqual('Club Link' in event['data'].keys(), True)
            self.assertEqual(event['data']['Club Link'], None)

    @httpretty.activate
    def test_fetch_empty(self):
        """Test whether it works when no events are fetched"""

        body = """
            {
                "encoding": "UTF-8",
                "feed": {
                "event": []
                }
            }
        """
        httpretty.register_uri(httpretty.GET,
                               MozillaClub_FEED_URL,
                               body=body, status=200)

        mozillaclub = MozillaClub(MozillaClub_FEED_URL)
        events = [event for event in mozillaclub.fetch()]

        self.assertEqual(len(events), 0)

    @httpretty.activate
    def test_search_fields(self):
        """Test whether the search_fields is properly set"""

        configure_http_server()

        mozillaclub = MozillaClub(MozillaClub_FEED_URL)
        events = [event for event in mozillaclub.fetch()]

        event = events[0]
        self.assertEqual(mozillaclub.metadata_id(event['data']), event['search_fields']['item_id'])
        self.assertEqual(event['data']['Club Name'], 'Rio Mozilla Club')
        self.assertEqual(event['data']['Club Name'], event['search_fields']['club_name'])

        event = events[1]
        self.assertEqual(mozillaclub.metadata_id(event['data']), event['search_fields']['item_id'])
        self.assertEqual(event['data']['Club Name'], 'Firefox club uog-skt')
        self.assertEqual(event['data']['Club Name'], event['search_fields']['club_name'])

        event = events[2]
        self.assertEqual(mozillaclub.metadata_id(event['data']), event['search_fields']['item_id'])
        self.assertEqual(event['data']['Club Name'], 'Mozilla HETEC Club')
        self.assertEqual(event['data']['Club Name'], event['search_fields']['club_name'])


class TestMozillaClubBackendArchive(TestCaseBackendArchive):
    """MozillaClub backend tests using an archive"""

    def setUp(self):
        super().setUp()
        self.backend_write_archive = MozillaClub(MozillaClub_FEED_URL, archive=self.archive)
        self.backend_read_archive = MozillaClub(MozillaClub_FEED_URL, archive=self.archive)

    @httpretty.activate
    def test_fetch_from_archive(self):
        """Test whether a list of events is returned from archive"""

        configure_http_server()
        self._test_fetch_from_archive()

    @httpretty.activate
    def test_fetch_empty_from_archive(self):
        """Test whether it works when no events are fetched from archive"""

        body = """
                {
                    "encoding": "UTF-8",
                    "feed": {
                    "event": []
                    }
                }
            """
        httpretty.register_uri(httpretty.GET,
                               MozillaClub_FEED_URL,
                               body=body, status=200)

        self._test_fetch_from_archive()


class TestMozillaClubCommand(unittest.TestCase):
    """Tests for MozillaClubCommand class"""

    def test_backend_class(self):
        """Test if the backend class is MozillaClub"""

        self.assertIs(MozillaClubCommand.BACKEND, MozillaClub)

    def test_setup_cmd_parser(self):
        """Test if it parser object is correctly initialized"""

        parser = MozillaClubCommand.setup_cmd_parser()
        self.assertIsInstance(parser, BackendCommandArgumentParser)
        self.assertEqual(parser._backend, MozillaClub)

        args = [MozillaClub_FEED_URL,
                '--tag', 'test',
                '--no-archive']

        parsed_args = parser.parse(*args)
        self.assertEqual(parsed_args.url, MozillaClub_FEED_URL)
        self.assertEqual(parsed_args.tag, 'test')
        self.assertEqual(parsed_args.no_archive, True)
        self.assertTrue(parsed_args.ssl_verify)

        args = [MozillaClub_FEED_URL, '--no-ssl-verify']

        parsed_args = parser.parse(*args)
        self.assertEqual(parsed_args.url, MozillaClub_FEED_URL)
        self.assertFalse(parsed_args.ssl_verify)


class TestMozillaClubClient(unittest.TestCase):
    """MozillaClub API client tests

    These tests not check the body of the response, only if the call
    was well formed and if a response was obtained. Due to this, take
    into account that the body returned on each request might not
    match with the parameters from the request.
    """

    def test_init(self):
        """Test initialization"""

        mozillaclub = MozillaClubClient(MozillaClub_FEED_URL)

        self.assertEqual(mozillaclub.base_url, MozillaClub_FEED_URL)
        self.assertIsNone(mozillaclub.archive)
        self.assertFalse(mozillaclub.from_archive)
        self.assertTrue(mozillaclub.ssl_verify)

        mozillaclub = MozillaClubClient(MozillaClub_FEED_URL, ssl_verify=False)

        self.assertEqual(mozillaclub.base_url, MozillaClub_FEED_URL)
        self.assertIsNone(mozillaclub.archive)
        self.assertFalse(mozillaclub.from_archive)
        self.assertFalse(mozillaclub.ssl_verify)

    @httpretty.activate
    def test_get_events(self):
        """Test get_events API call"""

        # Set up a mock HTTP server
        body = read_file('data/mozillaclub/feed.json')
        httpretty.register_uri(httpretty.GET,
                               MozillaClub_FEED_URL,
                               body=body, status=200)

        client = MozillaClubClient(MozillaClub_FEED_URL)
        response = client.get_cells()

        self.assertEqual(response, body)


class TestMozillaClubParser(unittest.TestCase):
    """MozillaClub parser tests"""

    def test_parser(self):
        """Test if it parsers a JSON feed stream"""

        with open("data/mozillaclub/feed.json", 'r') as f:
            parser = MozillaClubParser(f.read())
            events = [event for event in parser.parse()]

        self.assertEqual(len(events), 92)

        # Checking some random data
        self.assertEqual(events[10]['City'], 'Cape Town')
        self.assertEqual(events[45]['Links to Photos (Optional)'], None)
        self.assertEqual(events[53]['updated'], '2016-12-13T15:44:04.821Z')


if __name__ == "__main__":
    unittest.main(warnings='ignore')
