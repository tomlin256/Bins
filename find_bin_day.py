#!/usr/bin/env python
import argparse
import datetime
import logging
import os
import os.path
import pickle
from collections import namedtuple
from pathlib import Path

import requests

from bs4 import BeautifulSoup
from contexttimer import timer

HOST_URL = "https://www.guildford.gov.uk"
SITE_BASE_URL = f"{HOST_URL}/bincollectiondays"
FORM_SERVER_URL = f"{HOST_URL}/apiserver/formsservice/http/processsubmission"
FINDBINCOLLECTIONDAYS = "FINDBINCOLLECTIONDAYS"
PAGESESSIONID = "PAGESESSIONID"
SESSIONID = "SESSIONID"
NONCE = "NONCE"
PAGENAME = "PAGENAME"
VARIABLES = "VARIABLES"
FORMACTION_NEXT = "FORMACTION_NEXT"
PAGEINSTANCE = "PAGEINSTANCE"
ADDRESSSEARCH = "ADDRESSSEARCH"
ADDRESSSEARCH_POSTCODE = "ADDRESSSEARCH_POSTCODE"
ADDRESSSEARCH_ADDRESSLIST = "ADDRESSSEARCH_ADDRESSLIST"
ADDRESSSEARCH_NOADDRESSFOUND = "ADDRESSSEARCH_NOADDRESSFOUND"
ADDRESSSEARCH_PICKADDRESSLAYOUT = "ADDRESSSEARCH_PICKADDRESSLAYOUT"
ADDRESSSEARCH_SEARCHRESULTSCOND = "ADDRESSSEARCH_SEARCHRESULTSCONDITIONAL"
BINROUNDTABLE = "FINDBINCOLLECTIONDAYS_FINDCOLLECTIONDAY_BINROUNDTABLEHTML"

GuildfordBinsSession = namedtuple("binsession",
                                  ("session", "sessionId",
                                   "pageSessionId", "nonce"))


class BinPostCodeCacheFile(object):

    def __init__(self, cache_path, post_code):
        self.file_path = f"{cache_path}/{post_code}"
        self.content = self.read()

    def read(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, "rb") as f:
                content = pickle.load(f)
        else:
            content = {}
        return content

    def write(self):
        with open(self.file_path, "wb") as f:
            pickle.dump(self.content, f)

    def set_content(self, content):
        self.content = content

    def get(self, house_number):
        return self.content.get(house_number)


class BinPageCache(object):

    def __init__(self):
        self.cache_path = f"{Path.home()}/.bin_days"
        if not os.path.exists(self.cache_path):
            os.mkdir(self.cache_path)
        self._pages = {}

    def _get_page(self, post_code):
        if post_code not in self._pages:
            self._pages[post_code] = BinPostCodeCacheFile(self.cache_path,
                                                          post_code)
        return self._pages[post_code]

    def get_address_key(self, post_code, house_number):
        return self._get_page(post_code).get(house_number)

    def set_address_keys(self, post_code, keys):
        page = self._get_page(post_code)
        page.set_content(keys)
        page.write()


class NoCacheCache(object):

    def get_address_key(self, post_code, house_number):
        return None

    def set_address_keys(self, post_code, keys):
        pass


class BinWebPage(object):
    """ For querying bin collection days """

    def __init__(self, cache_provider):
        self.cache_provider = cache_provider

    def _get_name(self, field):
        return f"{FINDBINCOLLECTIONDAYS}_{field}"

    def _get_form_url(self, session):
        return f"{FORM_SERVER_URL}?pageSessionId={session.pageSessionId}&" \
               f"fsid={session.sessionId}&fsn={session.nonce}"

    def _get_form_input(self, soup, field):
        field_name = self._get_name(field)
        i = soup.find("input", attrs={'name': field_name})
        if not i:
            raise ValueError(f"didnt find field with name {field_name}")
        return i['value']

    def _get_session_info_from_soup(self, request_session, soup):
        pageSessionId = self._get_form_input(soup, PAGESESSIONID)
        sessionId = self._get_form_input(soup, SESSIONID)
        nonce = self._get_form_input(soup, NONCE)

        return GuildfordBinsSession(request_session, sessionId,
                                    pageSessionId, nonce)

    def _get_form_data(self, session, form_action_next):
        form_data = {
            self._get_name(SESSIONID): session.sessionId,
            self._get_name(PAGESESSIONID): session.pageSessionId,
            self._get_name(NONCE): session.nonce,
            self._get_name(PAGENAME): ADDRESSSEARCH,
            self._get_name(PAGEINSTANCE): "1",
            self._get_name(VARIABLES): "",
            self._get_name(FORMACTION_NEXT): form_action_next,
        }
        return form_data

    @timer(logger=logging.getLogger())
    def _create_new_session(self):
        """ new initial request to get session ids and http session """

        logging.info("creating new session")

        s = requests.Session()
        r = s.get(SITE_BASE_URL)
        if not r.status_code == 200:
            raise RuntimeError("failed to request session info")

        soup = BeautifulSoup(r.text, "html.parser")
        session = self._get_session_info_from_soup(s, soup)
        return session

    @timer(logger=logging.getLogger())
    def _find_addresses(self, session, post_code):
        """ post post_code in address search page """

        form_data = self._get_form_data(session, "Find address")
        form_data[self._get_name(ADDRESSSEARCH_POSTCODE)] = post_code

        url = self._get_form_url(session)
        r = session.session.post(url, data=form_data)
        if not r.status_code == 200:
            raise RuntimeError(f"failed to find addresses for post "
                               "code {post_code}")

        soup = BeautifulSoup(r.text, "html.parser")
        address_selector = soup.find("select",
                                     attrs={"name":
                                            self._get_name(
                                                ADDRESSSEARCH_ADDRESSLIST)})

        new_session = self._get_session_info_from_soup(session.session, soup)

        options = address_selector.find_all("option")

        # address text is in the form "NUMBER, {FLAT X}, STREET NAME"
        addresses = dict((o.text.split(',', 1)[0].strip(), o["value"])
                         for o in options)

        return new_session, addresses

    @timer(logger=logging.getLogger())
    def _find_dates(self, session, post_code, address_key):
        """ select and post house number to get collection dates """

        address_list = ['', address_key]

        form_data = self._get_form_data(session, "Find out bin collection day")
        form_data[self._get_name(VARIABLES)] = "e30="
        form_data[self._get_name(ADDRESSSEARCH_POSTCODE)] = post_code
        form_data[self._get_name(ADDRESSSEARCH_ADDRESSLIST)] = address_list
        form_data[self._get_name(ADDRESSSEARCH_NOADDRESSFOUND)] = "false"
        form_data[self._get_name(ADDRESSSEARCH_PICKADDRESSLAYOUT)] = "true"
        form_data[self._get_name(ADDRESSSEARCH_SEARCHRESULTSCOND)] = "false"

        url = self._get_form_url(session)
        r = session.session.post(url, data=form_data)
        if not r.status_code == 200:
            raise RuntimeError(f"failed to request dates for {address_key}")

        soup = BeautifulSoup(r.text, "html.parser")
        new_session = self._get_session_info_from_soup(session.session, soup)

        div = soup.find("div", attrs={"id": BINROUNDTABLE})
        table_rows = div.find_all("tr")

        collection_dates = {}
        headings = None
        for row in table_rows:
            if not headings:
                # type, freq, last, next
                headings = [td.contents for td in row.find_all("th")]
            else:
                (type_,), (_,), (_,), (next,) = [td.contents for
                                                 td in row.find_all("td")]
                next_date = datetime.datetime.strptime(next, "%A %d %B")

                today = datetime.date.today()
                if next_date.month < today.month:
                    year = today.year+1
                else:
                    year = today.year

                next_date = next_date.replace(year=year)
                collection_dates[type_] = next_date.date()

        return new_session, collection_dates

    def find_dates(self, post_code, house_number):
        """ query form server to find next collection dates """

        session = self._create_new_session()

        key = self.cache_provider.get_address_key(post_code, house_number)
        if not key:
            session, addresses = self._find_addresses(session, post_code)
            key = addresses[house_number]
            self.cache_provider.set_address_keys(post_code, addresses)
            logging.info(f"{post_code} not found in cache. "
                         f"added {len(addresses)}")
        else:
            logging.info(f"found {key} for {house_number} "
                         f"{post_code} in cache")

        session, dates = self._find_dates(session, post_code, key)

        return dates


def main():

    logging.basicConfig(format="%(levelname)s %(asctime)s %(message)s",
                        level=logging.INFO)

    parser = argparse.ArgumentParser(description='Query bin days')
    parser.add_argument('postcode')
    parser.add_argument('house')
    args = parser.parse_args()

    post_code = args.postcode
    house_number = args.house

    cache = BinPageCache()
    page = BinWebPage(cache)
    dates = page.find_dates(post_code, house_number)

    print(f"dates for {house_number} {post_code} are {dates}")


if __name__ == "__main__":
    main()
