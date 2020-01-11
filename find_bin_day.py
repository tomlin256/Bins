import requests
from bs4 import BeautifulSoup
from collections import namedtuple

SITE_BASE_URL = "https://www.guildford.gov.uk/bincollectiondays"
FORM_SERVER_URL = "https://www.guildford.gov.uk/apiserver/formsservice/http/processsubmission"

GuildfordBinsSession = namedtuple("binsession",
                                  ("session", "sessionId", "pageSessionId", "nonce"))


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

    def get_session_info(self):

        s = requests.Session()
        r = s.get(SITE_BASE_URL)
        if not r.status_code == 200:
            raise RuntimeError("failed to request session info")

        soup = BeautifulSoup(r.text, "html.parser")
        pageSessionId = self._get_form_input(soup, PAGESESSIONID)
        sessionId = self._get_form_input(soup, SESSIONID)
        nonce = self._get_form_input(soup, NONCE)

        form = soup.find("form", attrs={'id': 'FINDBINCOLLECTIONDAYS_FORM'})
        print(f"{form.attrs['action']}")

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

    def find_addresses(self, session, post_code):

        form_data = self._get_form_data(session, "Find address")
        form_data[self._get_field_name(ADDRESSSEARCH_POSTCODE)] = post_code

        url = self._get_form_url(session)
        print(url)
        r = session.session.post(url, data=form_data)
        if not r.status_code == 200:
            raise RuntimeError(f"failed to find addresses for post code {post_code}")

        soup = BeautifulSoup(r.text, "html.parser")
        address_selector = soup.find("select",
            attrs={"name": self._get_field_name(ADDRESSSEARCH_ADDRESSLIST)})

        form = soup.find("form", attrs={'id': 'FINDBINCOLLECTIONDAYS_FORM'})
        print(f"{form.attrs['action']}")
        for i in form.find_all('input'):
            print(i)

        nonce = self._get_form_input(soup, NONCE)
        new_session = GuildfordBinsSession(session.session, session.sessionId,
                                           session.pageSessionId, nonce)

        options = address_selector.find_all("option")

        addresses = dict((o.text.split(',', 1)[0].strip(), o["value"])
                         for o in options)

        return new_session, addresses

    def find_dates(self, session, post_code, address_key):

        form_data = self._get_form_data(session, "Find out bin collection day")
        form_data[self._get_field_name(ADDRESSSEARCH_POSTCODE)] = post_code
        form_data[self._get_field_name(ADDRESSSEARCH_ADDRESSLIST)] = address_key
        form_data[self._get_field_name(ADDRESSSEARCH_NOADDRESSFOUND)] = "false"

        s = session.session

        url = self._get_form_url(session)
        print(url)
        r = s.post(url, data=form_data)
        if not r.status_code == 200:
            raise RuntimeError(f"failed to find dates address {address_key}")

        with open("dates.html", "w") as f:
            f.write(r.text)


def main():

    page = BinWebPage()
    session = page.get_session_info()
    session, addresses = page.find_addresses(session, "GU1 3LN")
    print(f"found {len(addresses)} addresses, will test {addresses['26']}")
    dates = page.find_dates(session, "GU1 3LN", addresses["26"])



if __name__ == "__main__":
    main()
