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
#     Alvaro del Castillo <acs@bitergia.com>
#     Quan Zhou <quan@bitergia.com>
#

import json
import logging

from grimoirelab_toolkit.datetime import str_to_datetime

from ...backend import (Backend,
                        BackendCommand,
                        BackendCommandArgumentParser)
from ...client import HttpClient
from ...utils import DEFAULT_DATETIME

MOZILLA_CLUB_URL = \
    "https://spreadsheets.google.com/feeds/cells/1QHl2bjBhMslyFzR5XXPzMLdzzx7oeSKTbgR5PM8qp64/ohaibtm/public/values?alt=json"

EVENT_TEMPLATE = {
    1: "Status",
    2: "Date of Event",
    3: "Club Name",
    4: "Country",
    5: "Your Name",
    6: "Your Twitter Handle (Optional)",
    7: "Event Description",
    8: "Attendance",
    9: "Club Link",
    10: "City",
    11: "Event Creations",
    12: "Web Literacy Skills",
    13: "Links to Curriculum (Optional)",
    14: "Links to Blogpost (Optional)",
    15: "Links to Video (Optional)",
    16: "Links to Photos (Optional)",
    17: "Feedback from Attendees",
    18: "Your Feedback",
    19: "Timestamp",
    20: "Event Cover Photo"
}

CATEGORY_EVENT = 'event'

logger = logging.getLogger(__name__)


class MozillaClub(Backend):
    """MozillaClub backend for Perceval.

    This class retrieves the data from MozillaClub.

    :param url: Mozilla Club Events url
    :param tag: label used to mark the data
    :param archive: archive to store/retrieve items
    :param ssl_verify: enable/disable SSL verification
    """
    version = '0.5.0'

    CATEGORIES = [CATEGORY_EVENT]
    EXTRA_SEARCH_FIELDS = {
        'club_name': ['Club Name']
    }

    def __init__(self, url=MOZILLA_CLUB_URL, tag=None, archive=None, ssl_verify=True):
        origin = url
        self.url = url
        super().__init__(origin, tag=tag, archive=archive, ssl_verify=ssl_verify)

        self.client = None

    def fetch(self, category=CATEGORY_EVENT):
        """Fetch events from the MozillaClub URL.

        The method retrieves, from a MozillaClub URL, the
        events. The data is a Google spreadsheet retrieved using
        the feed API REST.

        :param category: the category of items to fetch

        :returns: a generator of events
        """
        kwargs = {}
        items = super().fetch(category, **kwargs)

        return items

    def fetch_items(self, category, **kwargs):
        """Fetch events

        :param category: the category of items to fetch
        :param kwargs: backend arguments

        :returns: a generator of items
        """
        logger.info("Looking for events at url '%s'", self.url)

        nevents = 0  # number of events processed

        raw_cells = self.client.get_cells()
        parser = MozillaClubParser(raw_cells)

        for event in parser.parse():
            yield event
            nevents += 1

        logger.info("Total number of events: %i", nevents)

    @classmethod
    def has_archiving(cls):
        """Returns whether it supports archiving items on the fetch process.

        :returns: this backend supports items archive
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

        return str(item['Date of Event'] + "_" + item['Club Name'])

    @staticmethod
    def metadata_category(item):
        """Extracts the category from a item.

        This backend only generates one type of item which is
        'event'.
        """
        return CATEGORY_EVENT

    @staticmethod
    def metadata_updated_on(item):
        """Extracts the update time from a MozillaClub item.

        The timestamp is extracted from 'updated' field.
        This date is in ISO format and it needs to be converted to
        a float value.

        :param item: item generated by the backend

        :returns: a UNIX timestamp
        """
        date = str_to_datetime(item['updated'])
        return float(date.timestamp())

    def _init_client(self, from_archive=False):
        """Init client"""

        return MozillaClubClient(self.url, self.archive, from_archive, self.ssl_verify)


class MozillaClubClient(HttpClient):
    """MozillaClub API client.

    This class implements a simple client to retrieve events from
    projects in a MozillaClub site.

    :param url: URL of MozillaClub
    :param archive: an archive to store/read fetched data
    :param from_archive: it tells whether to write/read the archive
    :param ssl_verify: enable/disable SSL verification

    :raises HTTPError: when an error occurs doing the request
    """
    def __init__(self, url, archive=None, from_archive=False, ssl_verify=True):
        super().__init__(url, archive=archive, from_archive=from_archive, ssl_verify=ssl_verify)

    def get_cells(self):
        """Retrieve all cells from the spreadsheet."""

        logger.info("Retrieving all cells spreadsheet data ...")
        logger.debug("MozillaClub client calls API: %s", self.base_url)
        raw_cells = self.fetch(self.base_url)

        return raw_cells.text


class MozillaClubParser:
    """Git log parser.

    This class parses a string in JSON format from a Google Spreadsheet. The
    feed includes all the cells in a list.

    Events are rows in the spreadsheet. The columns are the fields
    for the event. The JSON retrieved from the spreadsheet feed is
    a plain list with all the cells from all the rows.

    The list of cells is returned in the feed raw JSON in:

    {
    "encoding": "UTF-8",
    "feed": {
        "entry": [cell-1, ..., cell-n],
        "updated": {
            "$t": "2016-12-13T15:44:04.821Z"
        },
        ...
    },
    "version": "1.0"
    }

    The format of a cell is:

    {
        "category": [
            {
                "scheme": "http://schemas.google.com/spreadsheets/2006",
                "term": "http://schemas.google.com/spreadsheets/2006#cell"
            }
        ],
        "content": {
            "$t": "Status",
            "type": "text"
        },
        "gs$cell": {
            "$t": "Status",
            "col": "1",
            "row": "1"
        },
        "id": {
            "$t": "https://spreadsheets.google.com/feeds/cells/1QHl2b...
        },
        "link": [
            {
                "href": "https://spreadsheets.google.com/feeds/cells/1QHl2b...
                "rel": "self",
                "type": "application/atom+xml"
            }
        ],
        "title": {
            "$t": "A1",
            "type": "text"
        },
        "updated": {
            "$t": "2016-12-13T15:44:04.821Z"
        }
    }
    """
    def __init__(self, feed):
        self.feed = feed  # Spreadsheet feed
        self.cells = None  # list with all cells to be processed
        self.ncell = None  # current cell being parsed

    def parse(self):
        """Parse the MozillaClub spreadsheet feed cells json."""

        nevents_wrong = 0

        feed_json = json.loads(self.feed)

        if 'entry' not in feed_json['feed']:
            return

        self.cells = feed_json['feed']['entry']
        self.ncell = 0

        event_fields = self.__get_event_fields()

        # Process all events reading the rows according to the event template
        # The only way to detect the end of row is looking to the
        # number of column. When the max number is reached (cell_cols) the next
        # cell is from the next row.
        while self.ncell < len(self.cells):
            # Process the next row (event) getting all cols to build the event
            event = self.__get_next_event(event_fields)

            if event['Date of Event'] is None or event['Club Name'] is None:
                logger.warning("Wrong event data: %s", event)
                nevents_wrong += 1
                continue
            yield event

        logger.info("Total number of wrong events: %i", nevents_wrong)

    def __get_event_fields(self):
        """Get the events fields (columns) from the cells received."""

        event_fields = {}
        # The cells in the first row are the column names
        # Check that the columns names are the same we have as template
        # Create the event template from the data retrieved
        while self.ncell < len(self.cells):
            cell = self.cells[self.ncell]
            row = cell['gs$cell']['row']
            if int(row) > 1:
                # When the row number >1 the column row is finished
                break
            ncol = int(cell['gs$cell']['col'])
            name = cell['content']['$t']
            event_fields[ncol] = name
            if ncol in EVENT_TEMPLATE:
                if event_fields[ncol] != EVENT_TEMPLATE[ncol]:
                    logger.warning("Event template changed in spreadsheet %s vs %s",
                                   name, EVENT_TEMPLATE[ncol])
            else:
                logger.warning("Event template changed in spreadsheet. New column: %s", name)

            self.ncell += 1
        return event_fields

    def __get_next_event(self, event_fields):
        # Fill the empty event with all fields as None
        event = {key: None for key in event_fields.values()}
        event['updated'] = DEFAULT_DATETIME.isoformat()

        last_col = 0
        while self.ncell < len(self.cells):
            # Get all cols (cells) for the event (row)
            cell = self.cells[self.ncell]
            ncol = int(cell['gs$cell']['col'])
            if ncol <= last_col:
                # new event (row) detected: new cell column lower than last
                break
            event[event_fields[ncol]] = cell['content']['$t']
            # Add an extra column with the update datetime
            cell_update = str_to_datetime(cell['updated']['$t'])
            if cell_update > str_to_datetime(event['updated']):
                event['updated'] = cell['updated']['$t']
            last_col = ncol
            self.ncell += 1

        return event


class MozillaClubCommand(BackendCommand):
    """Class to run MozillaClub backend from the command line."""

    BACKEND = MozillaClub

    @classmethod
    def setup_cmd_parser(cls):
        """Returns the MozillaClub argument parser."""

        parser = BackendCommandArgumentParser(cls.BACKEND,
                                              archive=True,
                                              ssl_verify=True)

        # Required arguments
        parser.parser.add_argument('url', nargs='?',
                                   default=MOZILLA_CLUB_URL,
                                   help="MozillaClub URL")

        return parser
