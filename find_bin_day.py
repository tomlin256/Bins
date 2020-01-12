import requests
from bs4 import BeautifulSoup
from collections import namedtuple
import datetime

SITE_BASE_URL = "https://www.guildford.gov.uk/bincollectiondays"
FORM_SERVER_URL = "https://www.guildford.gov.uk/apiserver/formsservice/http/processsubmission"
FINDBINCOLLECTIONDAYS = "FINDBINCOLLECTIONDAYS"
PAGESESSIONID = "PAGESESSIONID"
SESSIONID = "SESSIONID"
NONCE = "NONCE"
PAGENAME = "PAGENAME"
ADDRESSSEARCH = "ADDRESSSEARCH"
ADDRESSSEARCH_POSTCODE = "ADDRESSSEARCH_POSTCODE"
VARIABLES = "VARIABLES"
FORMACTION_NEXT = "FORMACTION_NEXT"
PAGEINSTANCE = "PAGEINSTANCE"
ADDRESSSEARCH_ADDRESSLIST = "ADDRESSSEARCH_ADDRESSLIST"
ADDRESSSEARCH_NOADDRESSFOUND = "ADDRESSSEARCH_NOADDRESSFOUND"
ADDRESSSEARCH_PICKADDRESSLAYOUT = "ADDRESSSEARCH_PICKADDRESSLAYOUT"
ADDRESSSEARCH_SEARCHRESULTSCONDITIONAL = "ADDRESSSEARCH_SEARCHRESULTSCONDITIONAL"
BINROUNDTABLE = "FINDBINCOLLECTIONDAYS_FINDCOLLECTIONDAY_BINROUNDTABLEHTML"

GuildfordBinsSession = namedtuple("binsession",
                                  ("session", "sessionId", "pageSessionId", "nonce"))


class BinWebPage(object):

    def _get_field_name(self, field):
        return f"{FINDBINCOLLECTIONDAYS}_{field}"

    def _get_form_url(self, session):
        return f"{FORM_SERVER_URL}?pageSessionId={session.pageSessionId}&fsid={session.sessionId}&fsn={session.nonce}"

    def _get_form_input(self, soup, field):
        field_name = self._get_field_name(field)
        i = soup.find("input",
                      attrs={'name': field_name})
        if not i:
            raise ValueError(f"didnt find field with name {field_name}")
        return i['value']

    def _get_session_info(self):

        s = requests.Session()
        r = s.get(SITE_BASE_URL)
        if not r.status_code == 200:
            raise RuntimeError("failed to request session info")

        soup = BeautifulSoup(r.text, "html.parser")
        pageSessionId = self._get_form_input(soup, PAGESESSIONID)
        sessionId = self._get_form_input(soup, SESSIONID)
        nonce = self._get_form_input(soup, NONCE)

        return GuildfordBinsSession(s, sessionId, pageSessionId, nonce)

    def _get_form_data(self, session, form_action_next):
        form_data = {
            self._get_field_name(SESSIONID): session.sessionId,
            self._get_field_name(PAGESESSIONID): session.pageSessionId,
            self._get_field_name(NONCE): session.nonce,
            self._get_field_name(PAGENAME): ADDRESSSEARCH,
            self._get_field_name(PAGEINSTANCE): "1",
            self._get_field_name(VARIABLES): "",
            self._get_field_name(FORMACTION_NEXT): form_action_next,
        }
        return form_data

    def _find_addresses(self, session, post_code):

        form_data = self._get_form_data(session, "Find address")
        form_data[self._get_field_name(ADDRESSSEARCH_POSTCODE)] = post_code

        url = self._get_form_url(session)
        r = session.session.post(url, data=form_data)
        if not r.status_code == 200:
            raise RuntimeError(f"failed to find addresses for post code {post_code}")

        soup = BeautifulSoup(r.text, "html.parser")
        address_selector = soup.find("select",
            attrs={"name": self._get_field_name(ADDRESSSEARCH_ADDRESSLIST)})

        nonce = self._get_form_input(soup, NONCE)
        new_session = GuildfordBinsSession(session.session, session.sessionId,
                                           session.pageSessionId, nonce)

        options = address_selector.find_all("option")

        addresses = dict((o.text.split(',', 1)[0].strip(), o["value"])
                         for o in options)

        return new_session, addresses

    def _find_dates(self, session, post_code, address_key):

        form_data = self._get_form_data(session, "Find out bin collection day")
        form_data[self._get_field_name(VARIABLES)] = "e30="
        form_data[self._get_field_name(ADDRESSSEARCH_POSTCODE)] = post_code
        form_data[self._get_field_name(ADDRESSSEARCH_ADDRESSLIST)] = [ '', address_key ]
        form_data[self._get_field_name(ADDRESSSEARCH_NOADDRESSFOUND)] = "false"
        form_data[self._get_field_name(ADDRESSSEARCH_PICKADDRESSLAYOUT)] = "true"
        form_data[self._get_field_name(ADDRESSSEARCH_SEARCHRESULTSCONDITIONAL)] = "false"

        s = session.session

        url = self._get_form_url(session)
        r = s.post(url, data=form_data)
        if not r.status_code == 200:
            raise RuntimeError(f"failed to request dates for {address_key}")

        soup = BeautifulSoup(r.text, "html.parser")
        div = soup.find("div", attrs={"id": "FINDBINCOLLECTIONDAYS_FINDCOLLECTIONDAY_BINROUNDTABLEHTML"})
        table_rows = div.find_all("tr")

        collection_dates = {}
        headings = None
        for row in table_rows:
            if not headings:
                headings = [td.contents for td in row.find_all("th")]
            else:
                (type_,), (freq,), (last,), (next,) = [td.contents for td in row.find_all("td")]
                next_date = datetime.datetime.strptime(next, "%A %d %B")
                next_date = next_date.replace(year=datetime.date.today().year)
                collection_dates[type_] = next_date
        return collection_dates

    def find_dates(self, post_code, house_number):
        session = self._get_session_info()
        session, addresses = self._find_addresses(session, post_code)
        dates = self._find_dates(session, post_code, addresses[house_number])
        return dates


def main():

    post_code = "GU1 3LN"
    house_number = "26"

    page = BinWebPage()
    dates = page.find_dates(post_code, house_number)

    print(f"dates for {house_number} {post_code} are {dates}")


if __name__ == "__main__":
    main()
