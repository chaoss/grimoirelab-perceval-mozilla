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
import time

import requests

from grimoirelab_toolkit.datetime import str_to_datetime, datetime_to_utc
from grimoirelab_toolkit.uris import urijoin

from ...backend import (Backend,
                        BackendCommand,
                        BackendCommandArgumentParser,
                        OriginUniqueField)
from ...client import HttpClient
from ...errors import ParseError, RateLimitError, HttpClientError
from ...utils import DEFAULT_DATETIME


logger = logging.getLogger(__name__)


KITSUNE_URL = "https://support.mozilla.org"

CATEGORY_QUESTION = "question"

DEFAULT_SLEEP_TIME = 180
MAX_RETRIES = 5


class Kitsune(Backend):
    """Kitsune backend for Perceval.

    This class retrieves the questions and answers from a
    Kitsune URL. To initialize this class a URL may be provided.
    If not, https://support.mozilla.org will be used. The origin
    of the data will be set to this URL.

    Questions and answers are returned from older to newer.

    :param url: Kitsune URL
    :param tag: label used to mark the data
    :param archive: archive to store/retrieve items
    :param ssl_verify: enable/disable SSL verification
    :param sleep_for_rate: sleep until rate limit is reset
    :param sleep_time: time (in seconds) to sleep in case
        of connection problems
    :param max_retries: number of max retries to a data source
        before raising a RetryError exception
    :param blacklist_ids: ids of items that must not be retrieved
    """
    version = '2.1.0'

    CATEGORIES = [CATEGORY_QUESTION]
    ORIGIN_UNIQUE_FIELD = OriginUniqueField(name='id', type=int)

    def __init__(self, url=None, tag=None, archive=None, ssl_verify=True,
                 sleep_for_rate=False, sleep_time=DEFAULT_SLEEP_TIME,
                 max_retries=MAX_RETRIES, blacklist_ids=None):
        if not url:
            url = KITSUNE_URL
        origin = url

        super().__init__(origin, tag=tag, archive=archive, blacklist_ids=blacklist_ids,
                         ssl_verify=ssl_verify)
        self.url = url
        self.sleep_for_rate = sleep_for_rate
        self.sleep_time = sleep_time
        self.max_retries = max_retries

        self.client = None

    def fetch(self, category=CATEGORY_QUESTION, from_date=DEFAULT_DATETIME):
        """Fetch questions from the Kitsune url.

        :param category: the category of items to fetch
        :offset: obtain questions after offset
        :returns: a generator of questions
        """
        if not from_date:
            from_date = DEFAULT_DATETIME

        kwargs = {"from_date": from_date}
        items = super().fetch(category, **kwargs)

        return items

    def fetch_items(self, category, **kwargs):
        """Fetch questions from the Kitsune url

        :param category: the category of items to fetch
        :param kwargs: backend arguments

        :returns: a generator of items
        """
        from_date = kwargs['from_date']

        logger.info("Looking for questions at url '%s' updated after %s",
                    self.url, str(from_date))

        nquestions = 0  # number of questions processed
        tquestions = 0  # number of questions from API data

        for questions_page in self.client.get_questions(from_date):
            try:
                questions_data = json.loads(questions_page)
                tquestions = questions_data['count']
                questions = questions_data['results']
            except (ValueError, KeyError) as ex:
                logger.error(ex)
                cause = "Bad JSON format for mozilla_questions: %s" % (questions_page)
                raise ParseError(cause=cause)

            for question in questions:
                if self._skip_item(question):
                    self.summary.skipped += 1
                    continue

                question['answers_data'] = []
                for raw_answers in self.client.get_question_answers(question['id']):
                    answers = json.loads(raw_answers)['results']
                    question['answers_data'] += answers
                yield question
                nquestions += 1

        equestions = tquestions - nquestions

        logger.info("Total number of questions: %i (%i total)", nquestions, tquestions)
        logger.info("Questions with errors dropped: %i", equestions)

    @classmethod
    def has_archiving(cls):
        """Returns whether it supports archiving items on the fetch process.

        :returns: this backend does not support items archive
        """
        return False

    @classmethod
    def has_resuming(cls):
        """Returns whether it supports to resume the fetch process.

        :returns: this backend supports items resuming
        """
        return True

    @staticmethod
    def metadata_id(item):
        """Extracts the identifier from a Kitsune item."""

        return str(item['id'])

    @staticmethod
    def metadata_updated_on(item):
        """Extracts the update time from a Kitsune item.

        The timestamp is the maximum 'updated' field from the question
        and the answers. This date is a UNIX timestamp but needs to be
        converted to a float value.

        :param item: item generated by the backend

        :returns: a UNIX timestamp
        """
        max_updated_on = float(str_to_datetime(item['updated']).timestamp())

        for answer in item['answers_data']:
            answer_updated_on = float(str_to_datetime(answer['updated']).timestamp())
            max_updated_on = max(max_updated_on, answer_updated_on)

        return max_updated_on

    @staticmethod
    def metadata_category(item):
        """Extracts the category from a Kitsune item.

        This backend only generates one type of item which is
        'question'.
        """
        return CATEGORY_QUESTION

    def _init_client(self):
        """Init client"""

        return KitsuneClient(self.url, self.ssl_verify, self.sleep_for_rate,
                             self.sleep_time, self.max_retries)


class KitsuneClient(HttpClient):
    """Kitsune API client.

    This class implements a simple client to retrieve questions and answers from
    a Kitsune site.

    :param url: URL of Kitsune (sample https://support.mozilla.org)
    :param ssl_verify: enable/disable SSL verification
    :param sleep_for_rate: sleep until rate limit is reset
    :param sleep_time: seconds to sleep for rate limit
    :param max_retries: number of max retries for RateLimit

    :raises HTTPError: when an error occurs doing the request
    """
    FIRST_PAGE = 1  # Initial page in Kitsune
    ITEMS_PER_PAGE = 20  # Items per page in Kitsune API

    def __init__(self, url, ssl_verify=True, sleep_for_rate=False,
                 sleep_time=DEFAULT_SLEEP_TIME, max_retries=MAX_RETRIES):
        super().__init__(urijoin(url, '/api/2/'), ssl_verify=ssl_verify)

        self.sleep_for_rate = sleep_for_rate
        self.sleep_time = sleep_time
        self.max_retries = max_retries

    def get_questions(self, from_date):
        """Retrieve questions from older to newer updated starting offset"""

        page = KitsuneClient.FIRST_PAGE

        from_date = datetime_to_utc(from_date)
        failures = 0

        while True:
            api_questions_url = urijoin(self.base_url, '/question') + '/'

            params = {
                "page": page,
                "ordering": "updated",
                "updated__gt": from_date.isoformat()
            }

            try:
                questions = self.fetch(api_questions_url, params)
                yield questions
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 500:
                    if failures >= self.max_retries:
                        raise e
                    logger.exception(e)
                    logger.error("Problem getting Kitsune questions. "
                                 "Loosing %i questions. Going to the next page.",
                                 KitsuneClient.ITEMS_PER_PAGE)
                    page += 1
                    failures += 1
                    continue
                else:
                    # If it is another error just propagate the exception
                    raise e

            failures = 0
            questions_json = json.loads(questions)
            next_uri = questions_json['next']
            if not next_uri:
                break
            page += 1

    def get_question_answers(self, question_id):
        """Retrieve all answers for a question from older to newer (updated)"""

        page = KitsuneClient.FIRST_PAGE

        while True:
            api_answers_url = urijoin(self.base_url, '/answer') + '/'
            params = {
                "page": page,
                "question": question_id,
                "ordering": "updated"
            }

            answers_raw = self.fetch(api_answers_url, params)
            yield answers_raw

            answers = json.loads(answers_raw)
            if not answers['next']:
                break
            page += 1

    def sleep_for_rate_limit(self):
        """The fetching process sleeps until the rate limit is restored or
           raises a RateLimitError exception if sleep_for_rate flag is disabled.
        """
        cause = "Rate limit exhausted."
        if self.sleep_for_rate:
            logger.info(f"{cause} Waiting {self.sleep_time} secs for rate limit reset.")
            time.sleep(self.sleep_time)
        else:
            raise RateLimitError(cause=cause, seconds_to_reset=self.sleep_time)

    def fetch(self, url, params):
        """Return the textual content associated to the Response object"""

        logger.debug("Kitsune client calls API: %s params: %s",
                     url, str(params))

        retries = self.max_retries
        while retries >= 0:
            try:
                response = super().fetch(url, payload=params)
                return response.text
            except requests.exceptions.HTTPError as ex:
                if ex.response.status_code == 429 and retries > 0:
                    retries -= 1
                    self.sleep_for_rate_limit()
                else:
                    raise ex

        raise HttpClientError(cause="Max retries exceeded")


class KitsuneCommand(BackendCommand):
    """Class to run Kitsune backend from the command line."""

    BACKEND = Kitsune

    @classmethod
    def setup_cmd_parser(cls):
        """Returns the Kitsune argument parser."""

        parser = BackendCommandArgumentParser(cls.BACKEND,
                                              from_date=True,
                                              blacklist=True,
                                              ssl_verify=True)

        # Required arguments
        parser.parser.add_argument('url', nargs='?',
                                   default="https://support.mozilla.org",
                                   help="Kitsune URL (default: https://support.mozilla.org)")

        # Kitsune options
        group = parser.parser.add_argument_group('Kitsune arguments')
        group.add_argument('--sleep-for-rate', dest='sleep_for_rate',
                           action='store_true',
                           help="sleep for getting more rate")
        group.add_argument('--max-retries', dest='max_retries',
                           default=MAX_RETRIES, type=int,
                           help="number of API call retries")
        group.add_argument('--sleep-time', dest='sleep_time',
                           default=DEFAULT_SLEEP_TIME, type=int,
                           help="sleeping time between API call retries")
        return parser
