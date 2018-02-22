# -*- coding: utf-8 -*-
#
# Copyright (C) 2016-2017 Bitergia
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
# Foundation, 51 Franklin Street, Fifth Floor, Boston, MA 02110-1335, USA.
#
# Authors:
#     Alvaro del Castillo <acs@bitergia.com>
#

import json
import logging

import requests

from grimoirelab.toolkit.datetime import str_to_datetime
from grimoirelab.toolkit.uris import urijoin

from ...backend import (Backend,
                        BackendCommand,
                        BackendCommandArgumentParser)
from ...client import HttpClient
from ...errors import ParseError


logger = logging.getLogger(__name__)

KITSUNE_URL = "https://support.mozilla.org"
DEFAULT_OFFSET = 0


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
    """
    version = '0.5.0'

    def __init__(self, url=None, tag=None, archive=None):
        if not url:
            url = KITSUNE_URL
        origin = url

        super().__init__(origin, tag=tag, archive=archive)
        self.url = url

        self.client = None

    def fetch(self, offset=DEFAULT_OFFSET):
        """Fetch questions from the Kitsune url.

        :offset: obtain questions after offset
        :returns: a generator of questions
        """
        if not offset:
            offset = DEFAULT_OFFSET

        kwargs = {"offset": offset}
        items = super().fetch("question", **kwargs)

        return items

    def fetch_items(self, **kwargs):
        """Fetch questions from the Kitsune url"""

        offset = kwargs['offset']

        logger.info("Looking for questions at url '%s' using offset %s",
                    self.url, str(offset))

        nquestions = 0  # number of questions processed
        tquestions = 0  # number of questions from API data
        equestions = 0  # number of questions dropped by errors

        # Always get complete pages so the first item is always
        # the first one in the page
        page = int(offset / KitsuneClient.ITEMS_PER_PAGE)
        page_offset = page * KitsuneClient.ITEMS_PER_PAGE
        # drop questions from page before the offset
        drop_questions = offset - page_offset
        current_offset = offset

        questions_page = self.client.get_questions(offset)

        while True:
            try:
                raw_questions = next(questions_page)
            except StopIteration:
                break
            except requests.exceptions.HTTPError as e:
                # Continue with the next page if it is a 500 error
                if e.response.status_code == 500:
                    logger.exception(e)
                    logger.error("Problem getting Kitsune questions. " +
                                 "Loosing %i questions. Going to the next page.",
                                 KitsuneClient.ITEMS_PER_PAGE)
                    equestions += KitsuneClient.ITEMS_PER_PAGE
                    current_offset += KitsuneClient.ITEMS_PER_PAGE
                    questions_page = self.client.get_questions(current_offset)
                    continue
                else:
                    # If it is another error just propagate the exception
                    raise e

            try:
                questions_data = json.loads(raw_questions)
                tquestions = questions_data['count']
                questions = questions_data['results']
            except (ValueError, KeyError) as ex:
                logger.error(ex)
                cause = ("Bad JSON format for mozilla_questions: %s" % (raw_questions))
                raise ParseError(cause=cause)

            for question in questions:
                if drop_questions > 0:
                    # Remove extra questions due to page base retrieval
                    drop_questions -= 1
                    continue
                question['offset'] = current_offset
                current_offset += 1
                question['answers_data'] = []
                for raw_answers in self.client.get_question_answers(question['id']):
                    answers = json.loads(raw_answers)['results']
                    question['answers_data'] += answers
                yield question
                nquestions += 1

            logger.debug("Questions: %i/%i", nquestions + offset, tquestions)

        logger.info("Total number of questions: %i (%i total)", nquestions, tquestions)
        logger.info("Questions with errors dropped: %i", equestions)

    def metadata(self, item):
        """Kitsune metadata.

        This method takes items overrides `metadata` method to add extra
        information related to Kitsune (offset of the question).

        :param item: an item fetched by a backend
        """
        item = super().metadata(item)
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
        """Extracts the identifier from a Kitsune item."""

        return str(item['id'])

    @staticmethod
    def metadata_updated_on(item):
        """Extracts the update time from a Kitsune item.

        The timestamp is extracted from 'updated' field.
        This date is a UNIX timestamp but needs to be converted to
        a float value.

        :param item: item generated by the backend

        :returns: a UNIX timestamp
        """
        return float(str_to_datetime(item['updated']).timestamp())

    @staticmethod
    def metadata_category(item):
        """Extracts the category from a Kitsune item.

        This backend only generates one type of item which is
        'question'.
        """
        return 'question'

    def _init_client(self, from_archive=False):
        """Init client"""

        return KitsuneClient(self.url, self.archive, from_archive)


class KitsuneClient(HttpClient):
    """Kitsune API client.

    This class implements a simple client to retrieve questions and answers from
    a Kitsune site.

    :param url: URL of Kitsune (sample https://support.mozilla.org)
    :param archive: an archive to store/read fetched data
    :param from_archive: it tells whether to write/read the archive

    :raises HTTPError: when an error occurs doing the request
    """
    FIRST_PAGE = 1  # Initial page in Kitsune
    ITEMS_PER_PAGE = 20  # Items per page in Kitsune API

    def __init__(self, url, archive=None, from_archive=False):
        super().__init__(urijoin(url, '/api/2/'), archive=archive, from_archive=from_archive)

    def get_questions(self, offset=None):
        """Retrieve questions from older to newer updated starting offset"""

        page = KitsuneClient.FIRST_PAGE

        if offset:
            page += int(offset / KitsuneClient.ITEMS_PER_PAGE)

        while True:
            api_questions_url = urijoin(self.base_url, '/question') + '/'

            params = {
                "page": page,
                "ordering": "updated"
            }

            questions = self.fetch(api_questions_url, params)
            yield questions

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

    def fetch(self, url, params):
        """Return the textual content associated to the Response object"""

        logger.debug("Kitsune client calls API: %s params: %s",
                     url, str(params))

        response = super().fetch(url, payload=params)

        return response.text


class KitsuneCommand(BackendCommand):
    """Class to run Kitsune backend from the command line."""

    BACKEND = Kitsune

    @staticmethod
    def setup_cmd_parser():
        """Returns the Kitsune argument parser."""

        parser = BackendCommandArgumentParser(offset=True,
                                              archive=True)

        # Required arguments
        parser.parser.add_argument('url', nargs='?',
                                   default="https://support.mozilla.org",
                                   help="Kitsune URL (default: https://support.mozilla.org)")

        return parser
