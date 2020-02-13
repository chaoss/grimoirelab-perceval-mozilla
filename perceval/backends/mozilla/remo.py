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
import urllib.parse

from grimoirelab_toolkit.datetime import str_to_datetime
from grimoirelab_toolkit.uris import urijoin

from ...backend import (Backend,
                        BackendCommand,
                        BackendCommandArgumentParser)
from ...client import HttpClient

MOZILLA_REPS_URL = "https://reps.mozilla.org"
REMO_DEFAULT_OFFSET = 0

CATEGORY_EVENT = 'event'
CATEGORY_ACTIVITY = 'activity'
CATEGORY_USER = 'user'

logger = logging.getLogger(__name__)


class ReMo(Backend):
    """ReMo backend for Perceval.

    This class retrieves the events from a ReMo URL. To initialize
    this class an URL may be provided. If not, https://reps.mozilla.org
    will be used. The origin of the data will be set to this URL.

    It uses v2 API to get events, people and activities data.

    :param url: ReMo URL
    :param tag: label used to mark the data
    :param archive: archive to store/retrieve items
    :param ssl_verify: enable/disable SSL verification
    """
    version = '0.9.0'

    CATEGORIES = [CATEGORY_ACTIVITY, CATEGORY_EVENT, CATEGORY_USER]

    def __init__(self, url=None, tag=None, archive=None, ssl_verify=True):
        if not url:
            url = MOZILLA_REPS_URL
        origin = url

        super().__init__(origin, tag=tag, archive=archive, ssl_verify=ssl_verify)
        self.url = url
        self.client = None

        self.__users = {}  # internal users cache

    def fetch(self, category=CATEGORY_EVENT, offset=REMO_DEFAULT_OFFSET):
        """Fetch items from the ReMo url.

        The method retrieves, from a ReMo URL, the set of items
        of the given `category`.

        :param category: the category of items to fetch
        :param offset: obtain items after offset
        :returns: a generator of items
        """
        if not offset:
            offset = REMO_DEFAULT_OFFSET

        kwargs = {"offset": offset}
        items = super().fetch(category, **kwargs)

        return items

    def fetch_items(self, category, **kwargs):
        """Fetch items

        :param category: the category of items to fetch
        :param kwargs: backend arguments

        :returns: a generator of items
        """
        offset = kwargs['offset']

        logger.info("Looking for events at url '%s' of %s category and %i offset",
                    self.url, category, offset)

        nitems = 0  # number of items processed
        titems = 0  # number of items from API data

        # Always get complete pages so the first item is always
        # the first one in the page
        page = int(offset / ReMoClient.ITEMS_PER_PAGE)
        page_offset = page * ReMoClient.ITEMS_PER_PAGE
        # drop items from page before the offset
        drop_items = offset - page_offset
        logger.debug("%i items dropped to get %i offset starting in page %i (%i page offset)",
                     drop_items, offset, page, page_offset)
        current_offset = offset

        for raw_items in self.client.get_items(category, offset):
            items_data = json.loads(raw_items)
            titems = items_data['count']
            logger.info("Pending items to retrieve: %i, %i current offset",
                        titems - current_offset, current_offset)
            items = items_data['results']
            for item in items:
                if drop_items > 0:
                    # Remove extra items due to page base retrieval
                    drop_items -= 1
                    continue
                raw_item_details = self.client.fetch(item['_url'])
                item_details = json.loads(raw_item_details)
                item_details['offset'] = current_offset
                current_offset += 1
                yield item_details
                nitems += 1

        logger.info("Total number of events: %i (%i total, %i offset)", nitems, titems, offset)

    def metadata(self, item, filter_classified=False):
        """ReMo metadata.

        This method takes items overrides `metadata` method to add extra
        information related to Remo (offset of the item).

        :param item: an item fetched by a backend
        :param filter_classified: sets if classified fields were filtered
        """
        item = super().metadata(item, filter_classified=filter_classified)
        item['offset'] = item['data'].pop('offset')

        return item

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
        return True

    @staticmethod
    def metadata_id(item):
        """Extracts the identifier from a ReMo item."""
        return str(item['remo_url'])

    @staticmethod
    def metadata_updated_on(item):
        """Extracts the update time from a ReMo item.

        The timestamp is extracted from 'end' field.
        This date is converted to a perceval format using a float value.

        :param item: item generated by the backend

        :returns: a UNIX timestamp
        """
        if 'end' in item:
            # events updated field
            updated = item['end']
        elif 'date_joined_program' in item:
            # users updated field that always appear
            updated = item['date_joined_program']
        elif 'report_date' in item:
            # activities updated field
            updated = item['report_date']
        else:
            raise ValueError("Can't find updated field for item " + str(item))

        return float(str_to_datetime(updated).timestamp())

    @staticmethod
    def metadata_category(item):
        """Extracts the category from a ReMo item.

        This backend generates items types 'event', 'activity'
        or 'user'. To guess the type of item, the code will look
        for unique fields.
        """
        if 'estimated_attendance' in item:
            category = CATEGORY_EVENT
        elif 'activity' in item:
            category = CATEGORY_ACTIVITY
        elif 'first_name' in item:
            category = CATEGORY_USER
        else:
            raise TypeError("Could not define the category of item " + str(item))

        return category

    def _init_client(self, from_archive=False):
        """Init client"""

        return ReMoClient(self.url, self.archive, from_archive, self.ssl_verify)


class ReMoClient(HttpClient):
    """ReMo API client.

    This class implements a simple client to retrieve events from
    projects in a ReMo site.

    :param url: URL of ReMo (sample https://reps.mozilla.org)
    :param archive: an archive to store/read fetched data
    :param from_archive: it tells whether to write/read the archive
    :param ssl_verify: enable/disable SSL verification

    :raises HTTPError: when an error occurs doing the request
    """

    FIRST_PAGE = 1  # Initial page in ReMo API
    ITEMS_PER_PAGE = 20  # Items per page in ReMo API
    API_PATH = '/api/remo/v1'

    def __init__(self, url, archive=None, from_archive=False, ssl_verify=True):
        super().__init__(url, archive=archive, from_archive=from_archive, ssl_verify=ssl_verify)
        self.api_activities_url = urijoin(self.base_url, ReMoClient.API_PATH + '/activities/')
        self.api_activities_url += '/'  # API needs a final /
        self.api_events_url = urijoin(self.base_url, ReMoClient.API_PATH + '/events/')
        self.api_events_url += '/'  # API needs a final /
        self.api_users_url = urijoin(self.base_url, ReMoClient.API_PATH + '/users/')
        self.api_users_url += '/'  # API needs a final /

    def get_items(self, category=CATEGORY_EVENT, offset=REMO_DEFAULT_OFFSET):
        """Retrieve all items for category using pagination """

        more = True  # There are more items to be processed
        next_uri = None  # URI for the next items page query
        page = ReMoClient.FIRST_PAGE
        page += int(offset / ReMoClient.ITEMS_PER_PAGE)

        if category == CATEGORY_EVENT:
            api = self.api_events_url
        elif category == CATEGORY_ACTIVITY:
            api = self.api_activities_url
        elif category == CATEGORY_USER:
            api = self.api_users_url
        else:
            raise ValueError(category + ' not supported in ReMo')

        while more:
            params = {
                "page": page,
                "orderby": "ASC"
            }

            logger.debug("ReMo client calls APIv2: %s params: %s",
                         api, str(params))

            raw_items = self.fetch(api, payload=params)
            yield raw_items

            items_data = json.loads(raw_items)
            next_uri = items_data['next']

            if not next_uri:
                more = False
            else:
                # https://reps.mozilla.org/remo/api/remo/v1/events/?orderby=ASC&page=269
                parsed_uri = urllib.parse.urlparse(next_uri)
                parsed_params = urllib.parse.parse_qs(parsed_uri.query)
                page = parsed_params['page'][0]

    def fetch(self, url, payload=None):
        """Return the textual content associated to the Response object"""

        response = super().fetch(url, payload)

        return response.text


class ReMoCommand(BackendCommand):
    """Class to run ReMo backend from the command line."""

    BACKEND = ReMo

    @classmethod
    def setup_cmd_parser(cls):
        """Returns the ReMo argument parser."""

        parser = BackendCommandArgumentParser(cls.BACKEND,
                                              offset=True,
                                              archive=True,
                                              ssl_verify=True)
        # Required arguments
        parser.parser.add_argument('url', nargs='?',
                                   default="https://reps.mozilla.org",
                                   help="ReMo URL (default: https://reps.mozilla.org)")

        return parser
