"""
Implements a test which starts an instance of the rewriting
proxy server, loads a set of URLs and verifies that the pages
were served correctly.
"""

from __future__ import print_function
from enum import Enum
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
import pytest
import requests
import sys
import threading


from pywb.framework.wsgi_wrappers import init_app
from pywb.webapp.pywb_init import create_wb_router
from wsgiref.simple_server import make_server


class Browsers(Enum):
    Firefox = 1
    Chrome = 2


PROXY_PORT = 8091


class RewritingProxyServer:
    def __init__(self, port):
        self.port = PROXY_PORT
        config = dict(proxyhostport=None,
                      framed_replay=False,
                      enable_auto_colls=False,
                      collections={'live':'$liveweb'})
        app = init_app(create_wb_router, load_yaml=False, config=config)

        self.server = make_server('', self.port, app)
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.start()
        
    def shutdown(self):
        self.server.shutdown()
        self.server_thread.join()


# Returns true if an error message reported by a browser
# should be ignored when checking for JavaScript errors
def _should_ignore_console_error(msg):
    IGNORED_ERRORS = [
      # Chrome requests $HOST/favicon.ico for each page it fetches
      # and logs an error if not found
      'favicon.ico'
    ]
    for ignore_pattern in IGNORED_ERRORS:
        if ignore_pattern in msg:
            return True
    return False


class Browser:
    def __init__(self, browser, proxy_url):
        self.proxy_url = proxy_url

        # enable browser logging so that we can capture JS
        # errors
        caps = {'loggingPrefs' : {'browser':'ALL'}}

        if browser == Browsers.Firefox:
            caps.update(DesiredCapabilities.FIREFOX)
            self.browser = webdriver.Firefox(capabilities=caps)
        elif browser == Browsers.Chrome:
            caps.update(DesiredCapabilities.CHROME)
            self.browser = webdriver.Chrome(desired_capabilities=caps)
        else:
            raise Exception('Unsupported browser')

        # flush the log on startup.
        # Firefox for example logs a large number of debug and info
        # messages on startup
        for entry in self.browser.get_log('browser'):
            pass

    def close(self):
        self.browser.close()

    def check_for_js_errors(self):
        """ Checks whether the browser reported any JavaScript errors. """
        errors = [entry['message'] for entry in self.browser.get_log('browser')
                  if entry['level'] == 'SEVERE']
        errors = filter(lambda error: not _should_ignore_console_error(error), errors)

        if len(errors) > 0:
            pytest.fail('; '.join(errors))

    def fetch(self, url):
        self.browser.get('%s/%s' % (self.proxy_url, url))


@pytest.fixture(scope='module')
def rewriting_proxy(request):
    server = RewritingProxyServer(PROXY_PORT)
    request.addfinalizer(server.shutdown)
    return server


@pytest.fixture(scope='module', params=[Browsers.Firefox, Browsers.Chrome])
def browser(request):
    browser = Browser(request.param, 'http://localhost:%s/live' % PROXY_PORT)
    request.addfinalizer(browser.close)
    return browser


TEST_PAGES = ['http://example.com', 'https://github.com']


@pytest.mark.parametrize('url', TEST_PAGES)
def test_load_pages(rewriting_proxy, browser, url):
    browser.fetch(url)
    browser.check_for_js_errors()
