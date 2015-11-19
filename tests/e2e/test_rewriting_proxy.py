"""
Implements a test which starts an instance of the rewriting
proxy server, loads a set of URLs and verifies that the pages
were served correctly.
"""

from __future__ import print_function
from enum import Enum
from selenium import webdriver
import pytest
import requests
import sys
import threading


from pywb.framework.wsgi_wrappers import init_app
from pywb.webapp.pywb_init import create_wb_router
from wsgiref.simple_server import make_server


class Browsers:
    # Local browsers
    FIREFOX = 'local/firefox'
    CHROME = 'local/chrome'

    # Sauce Labs Desktop browsers
    SAUCE_CHROME = 'sauce/chrome'
    SAUCE_FIREFOX = 'sauce/firefox'
    SAUCE_SAFARI = 'sauce/safari'

    # Sauce Labs Windows Desktop browsers
    # (FIXME - Not currently working as they do
    #  not support loggingPrefs)
    SAUCE_IE = 'sauce/ie'
    SAUCE_EDGE = 'sauce/edge'

    # Sauce Labs mobile browsers
    # (FIXME - Not currently working)
    SAUCE_IPHONE = 'sauce/iphone'
    SAUCE_ANDROID = 'sauce/android'


# TODO - Read these from a config file
PROXY_PORT = 8090
SAUCE_USERNAME = '<insert username>'
SAUCE_ACCESS_KEY = '<insert access key>'


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
        # errors.
        #
        # FIXME - 'loggingPrefs' options are not currently
        # supported for Internet Explorer or Edge
        caps = {'loggingPrefs' : {'browser':'ALL'}}

        sauce_url = 'http://%s:%s@ondemand.saucelabs.com:80/wd/hub' % \
          (SAUCE_USERNAME, SAUCE_ACCESS_KEY)

        # see https://wiki.saucelabs.com/display/DOCS/Platform+Configurator
        # for Sauce Labs WebDriver configuration settings for various
        # platforms
        def start_sauce_browser(platform_caps):
            caps.update(platform_caps)
            self.browser = webdriver.Remote(
              desired_capabilities=caps,
              command_executor=sauce_url
            )

        if browser == Browsers.FIREFOX:
            caps.update({'browserName':'firefox'})
            self.browser = webdriver.Firefox(capabilities=caps)
        elif browser == Browsers.CHROME:
            caps.update({'browserName':'chrome'})
            self.browser = webdriver.Chrome(desired_capabilities=caps)
        elif browser == Browsers.SAUCE_SAFARI:
            start_sauce_browser({
                'browserName': 'safari',
                'platform': 'OS X 10.11',
            })
        elif browser == Browsers.SAUCE_FIREFOX:
            start_sauce_browser({'browserName':'firefox'})
        elif browser == Browsers.SAUCE_CHROME:
            start_sauce_browser({'browserName':'chrome'})
        elif browser == Browsers.SAUCE_IE:
            start_sauce_browser({'browserName':'internet explorer'})
        elif browser == Browsers.SAUCE_EDGE:
            start_sauce_browser({'browserName':'MicrosoftEdge'})
        elif browser == Browsers.SAUCE_IPHONE:
            start_sauce_browser({'browserName':'iPhone'})
        elif browser == Browsers.SAUCE_ANDROID:
            start_sauce_browser({'browserName':'android'})
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


@pytest.fixture(scope='module', params=[Browsers.FIREFOX, Browsers.CHROME])
def browser(request):
    proxy_server_url = 'http://localhost:%s/live' % PROXY_PORT
    browser = Browser(request.param, proxy_server_url)
    request.addfinalizer(browser.close)
    return browser


TEST_PAGES = ['http://example.com', 'http://www.bbc.com/news/world-europe-34866820']


@pytest.mark.parametrize('url', TEST_PAGES)
def test_load_pages(rewriting_proxy, browser, url):
    browser.fetch(url)
    browser.check_for_js_errors()
