# -*- coding: utf-8 -*-
#
# Copyright (C) 2016 Bitergia
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
#     Alvaro del Castillo <acs@bitergia.com>
#

import json
import logging
import os.path

import requests


from ...backend import Backend, BackendCommand, metadata
from ...cache import Cache
from ...errors import BackendError, CacheError, ParseError

from ...utils import (DEFAULT_DATETIME,
                     datetime_to_utc,
                     str_to_datetime,
                     urljoin)


logger = logging.getLogger(__name__)

MOZILLA_CLUB_URL = "https://spreadsheets.google.com/feeds/cells/1QHl2bjBhMslyFzR5XXPzMLdzzx7oeSKTbgR5PM8qp64/ohaibtm/public/values?alt=json"

class MozillaClub(Backend):
    """MozillaClub backend for Perceval.

    This class retrieves the data from MozillaClub.

    :param url: Mozilla Club Events url
    :param cache: cache object to store raw data
    :param tag: label used to mark the data
    """
    version = '0.1.0'

    event_template = {
        "1": "Status",
        "2": "Date of Event",
        "3": "Club Name",
        "4": "Country",
        "5": "Your Name",
        "6": "Your Twitter Handle (Optional)",
        "7": "Event Description",
        "8": "Attendance",
        "9": "Club Link",
        "10": "City",
        "11": "Event Creations",
        "12": "Web Literacy Skills",
        "13": "Links to Curriculum (Optional)",
        "14": "Links to Blogpost (Optional)",
        "15": "Links to Video (Optional)",
        "16": "Links to Photos (Optional)",
        "17": "Feedback from Attendees",
        "18": "Your Feedback",
        "19": "Timestamp",
        "20": "Event Cover Photo"
    }

    def __init__(self, url=MOZILLA_CLUB_URL, cache=None, tag=None):
        origin = url
        self.url = url
        super().__init__(origin, tag=tag, cache=cache)
        self.client = MozillaClubClient(url)
        self.__users = {}  # internal users cache

    def __get_event_fields(self, cells):
        """ Get the events fields (columns) from the cells received """

        event_fields = {}
        # Check that the columns names are the same we have as template
        # Create the event template from the data retrieved
        column_names = True
        while column_names:
            cell = cells[0]
            row = cell['gs$cell']['row']
            if int(row) > 1:
                break
            # Remove the cells with column names
            cell = cells.pop(0)
            col = cell['gs$cell']['col']
            name = cell['content']['$t']
            event_fields[col] = name
            if col in MozillaClub.event_template:
                if event_fields[col] != MozillaClub.event_template[col]:
                    logger.warning("Event template changed in spreadsheet %s vs %s",
                                    name, MozillaClub.event_template[col])
            else:
                logger.warning("Event template changed in spreadsheet. New column: %s", name)
        return event_fields

    def __get_next_event(self, event_fields, cells):
        """ Get next event from the remaining the cells """
        event = {}
        last_col = 0
        cell_cols = len(event_fields.keys())

        # Fill the empty event with all fields as None
        for i in range (1, cell_cols+1):
            event[event_fields[str(i)]] = None
        while True and cells:
            # Get all cols (cells) for the event (row)
            cell = cells[0]
            col = cell['gs$cell']['col']
            if int(col) < int(last_col):
                # new event (row) detected: new cell column lower than last
                break
            else:
                # The next cell is for the current row (event)
                cell = cells.pop(0)
            event[event_fields[str(col)]] = cell['content']['$t']
            if int(col) >= cell_cols:
                # row (event) completed, all fields (cols) read
                break
            last_col = col

        return event


    @metadata
    def fetch(self):
        """Fetch events from the MozillaClub url.

        The method retrieves, from a MozillaClub url, the
        events. The data is a Google spreadsheet retrieved using
        the feed API REST.

        Events are rows in the spreadsheet. The columns are the fields
        for the event. The JSON retrieved from the spreadsheet feed is
        a plain list with all the cells from all the rows.

        :returns: a generator of events
        """

        logger.info("Looking for events at url '%s'", self.url)

        nevents = 0  # number of events processed
        nevents_wrong = 0  # number of events with wrong data

        self._purge_cache_queue()

        raw_cells = self.client.get_cells()
        self._push_cache_queue(raw_cells)
        sheet_json = json.loads(raw_cells)
        self._flush_cache_queue()

        cells = sheet_json['feed']['entry']
        if len(cells) == 0:
            logger.info("Total number of events: %i", nevents)
            return

        event_fields = self.__get_event_fields(cells)

        # Process all events reading the rows according to the event template
        # The only way to detect the end of row is looking to the
        # number of column. When the max number is reached (cell_cols) the next
        # cell is from the next row.
        # The first while is for looping rows and the second columns
        while cells:
            # Process the next row (event) getting all cols to build the event
            event = self.__get_next_event(event_fields, cells)

            if event['Date of Event'] is None or event['Club Name'] is None:
                logger.error("Wrong event data: %s", event)
                nevents_wrong += 1
                continue
            yield event
            nevents += 1

        logger.info("Total number of events: %i", nevents)
        logger.info("Total number of wrong events: %i", nevents_wrong)

    @metadata
    def fetch_from_cache(self):
        """Fetch the events from the cache.

        :returns: a generator of events

        :raises CacheError: raised when an error occurs accessing the
            cache
        """

        logger.info("Retrieving cached events: '%s'", self.url)

        if not self.cache:
            raise CacheError(cause="cache instance was not provided")

        cache_items = next(self.cache.retrieve())
        sheet_json = json.loads(cache_items)
        cells = sheet_json['feed']['entry']

        event_fields = self.__get_event_fields(cells)

        nevents = 0
        nevents_wrong = 0

        while cells:
            # Process the next row (event) getting all cols to build the event
            event = self.__get_next_event(event_fields, cells)

            if event['Date of Event'] is None or event['Club Name'] is None:
                logger.error("Wrong event data: %s", event)
                nevents_wrong += 1
                continue
            yield event
            nevents += 1

        logger.info("Total number of events from cache: %i", nevents)
        logger.info("Total number of wrong events from cache: %i", nevents_wrong)


    @classmethod
    def has_caching(cls):
        """Returns whether it supports caching items on the fetch process.

        :returns: this backend supports items cache
        """
        return True

    @classmethod
    def has_resuming(cls):
        """Returns whether it supports to resume the fetch process.

        :returns: this backend supports items resuming
        """
        return False

    @staticmethod
    def metadata_id(item):
        """Extracts the identifier from an event item."""
        try:
            a = item.keys()
        except AttributeError:
            print ("->"+item+"<-")
            raise
        return str(item['Date of Event']+"_"+item['Club Name'])

    @staticmethod
    def metadata_category(item):
        """Extracts the category from a item.

        This backend only generates one type of item which is
        'event'.
        """
        return 'event'

    @staticmethod
    def metadata_updated_on(item):
        """Extracts the update time from a MozillaClub item.

        The timestamp is extracted from 'end' field.
        This date is a UNIX timestamp but needs to be converted to
        a float value.

        :param item: item generated by the backend

        :returns: a UNIX timestamp
        """
        return float(str_to_datetime(item['Date of Event']).timestamp())


class MozillaClubClient:
    """MozillaClub API client.

    This class implements a simple client to retrieve events from
    projects in a MozillaClub site.

    :param url: URL of MozillaClub

    :raises HTTPError: when an error occurs doing the request
    """

    def __init__(self, url):
        self.url = url

    def call(self, uri):
        """Run an API command.
        :param params: dict with the HTTP parameters needed to run
            the given command
        """
        logger.debug("MozillaClub client calls API: %s", self.url)

        req = requests.get(uri)
        req.raise_for_status()

        return req.text

    def get_cells(self):
        """Retrieve all cells from the spreadsheet"""

        logging.info("Retrieving all cells spreadsheet data ...")
        raw_cells = self.call(self.url)

        return raw_cells


class MozillaClubCommand(BackendCommand):
    """Class to run MozillaClub backend from the command line."""

    def __init__(self, *args):
        super().__init__(*args)
        self.url = self.parsed_args.url
        self.tag = self.parsed_args.tag
        self.outfile = self.parsed_args.outfile

        if not self.parsed_args.no_cache:
            if not self.parsed_args.cache_path:
                base_path = os.path.expanduser('~/.perceval/cache/')
            else:
                base_path = self.parsed_args.cache_path

            cache_path = os.path.join(base_path, self.url)

            cache = Cache(cache_path)

            if self.parsed_args.clean_cache:
                cache.clean()
            else:
                cache.backup()
        else:
            cache = None

        self.backend = MozillaClub(cache=cache, tag=self.tag)

    def run(self):
        """Fetch and print the Club Events data.

        This method runs the backend to fetch the events.
        Events are converted to JSON objects and printed to the
        defined output.
        """
        if self.parsed_args.fetch_cache:
            events = self.backend.fetch_from_cache()
        else:
            events = self.backend.fetch()

        try:
            for event in events:
                obj = json.dumps(event, indent=4, sort_keys=True)
                self.outfile.write(obj)
                self.outfile.write('\n')
        except requests.exceptions.HTTPError as e:
            raise requests.exceptions.HTTPError(str(e.response.json()))
        except IOError as e:
            raise RuntimeError(str(e))
        except Exception as e:
            if self.backend.cache:
                self.backend.cache.recover()
            raise RuntimeError(str(e))

    @classmethod
    def create_argument_parser(cls):
        """Returns the MozillaClub argument parser."""

        parser = super().create_argument_parser()

        # Remove --from-date argument from parent parser
        # because it is not needed by this backend
        action = parser._option_string_actions['--from-date']
        parser._handle_conflict_resolve(None, [('--from-date', action)])


        # MozillaClub options
        group = parser.add_argument_group('MozillaClub arguments')

        group.add_argument("url", default=MOZILLA_CLUB_URL, nargs='?',
                           help="MozillaClub URL")

        return parser
