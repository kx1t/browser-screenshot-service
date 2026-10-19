#!/usr/bin/env python3

# starlette+uvicorn replace responder so all deps are available via apt.
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route
import uvicorn

# yes, recursive is needed. it isn't all imported by default.
import selenium
import selenium.webdriver
import selenium.webdriver.support.wait
import selenium.webdriver.support.expected_conditions as EC
import time
import sys
import os
import re
import logging
import urllib.parse
import timeout_decorator

logging.basicConfig(level=logging.CRITICAL, format='%(message)s')
log = logging.getLogger(__file__)
log.propagate = True
log.setLevel(logging.DEBUG) # notset, debug, info, warning, error, critical


BASE_URL = os.environ.get('BASE_URL', '')
# max seconds to wait for tile loading to go quiet (NOT a fixed sleep).
# Fast systems finish much sooner; this is the safe upper bound for slow ones.
LOAD_SLEEP_TIME = float(os.environ.get('LOAD_SLEEP_TIME', 15))
MAP_ARGS = os.environ.get('MAP_ARGS', '')
# comma-separated CSS selectors; the first one with a visible element wins.
# .ol-viewport = OpenLayers (current tar1090/AIS-catcher), #map_canvas = legacy,
# .leaflet-container = Leaflet builds, #map = generic fallback.
MAP_SELECTOR = os.environ.get('MAP_SELECTOR', '.ol-viewport,#map_canvas,.leaflet-container,#map')
SELECTOR_TIMEOUT = float(os.environ.get('SELECTOR_TIMEOUT', 20))
PAGE_LOAD_STRATEGY = os.environ.get('PAGE_LOAD_STRATEGY', 'eager')
PAGE_ZOOM = int(os.environ.get('PAGE_ZOOM', '100'))
DISABLE_SHM = bool(os.environ.get('DISABLE_SHM'))
DISABLE_VIZ = bool(os.environ.get('DISABLE_VIZ'))
MAXTIME = int(os.environ.get('MAXTIME', '30'))
CANVAS_SIZE = os.environ.get('CANVAS_SIZE', '1200x1600')

async def snap_api(request):
  mmsi = request.path_params.get('mmsi', '')
  img = get_screenshot(mmsi)
  return Response(content=img, media_type='image/png')

async def favicon(request):
  return Response(content=one_by_one_pixel(), media_type='image/gif')

def safe_url(u):
  '''Just seeing if things are fully formed.'''
  u = re.sub(r'[\'"]', '', u)
  if not re.match('^http(s?)://', u):
    u = f"http://{u}"
  return u

def build_url(base, mmsi, map_args):
  '''Merge the base URL with our query params, even if base already has a query string.'''
  parts = urllib.parse.urlsplit(base)
  path = parts.path or '/'
  if not path.endswith('/'):
    path += '/'
  extra = f'mmsi={mmsi}&welcome=false'
  map_args = map_args.lstrip('?&')
  if map_args:
    extra = f'{extra}&{map_args}'
  query = f'{parts.query}&{extra}' if parts.query else extra
  return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))

def one_by_one_pixel():
  #return base64.b64decode('R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==')
  return b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'

@timeout_decorator.timeout(MAXTIME)
def get_screenshot(mmsi):
  '''Returns PNG as a binary. Doesn't serve arbitrary URLs because it'd be a security hole.'''

  start_t = time.time()
  mmsi = mmsi.upper()
  log.warning(time.strftime('%Y-%m-%d %H:%M:%S') + " hi.")
  ss = one_by_one_pixel()

  # either no mmsi or the correct length.
  if len(mmsi) and (len(mmsi) < 6 or len(mmsi) > 10 or not re.match('^[0-9]*$', mmsi)):
    log.error(f"bad mmsi: {mmsi}")
    return one_by_one_pixel()
  if not BASE_URL:
    log.error("BASE_URL is not set; refusing to browse an empty URL.")
    return one_by_one_pixel()
  _base = safe_url(BASE_URL)
  url = build_url(_base, mmsi, MAP_ARGS)
  log.info(f"pulling url: {url}")

  co = selenium.webdriver.chrome.options.Options()
  #co.add_argument("--delay 5")
  # headless=new: the legacy --headless renders black on modern Chrome (>=132)
  co.add_argument("--headless=new")
  co.add_argument("--no-sandbox")
  # kx1t adds per https://stackoverflow.com/questions/48450594/selenium-timed-out-receiving-message-from-renderer
  co.add_argument("--disable-infobars")
  co.add_argument("--disable-dev-shm-usage")
  co.add_argument("--disable-browser-side-navigation")
  co.add_argument("--disable-gpu")
  #co.add_argument("--incognito")

  # 'eager' returns from browser.get() at DOMContentLoaded instead of waiting for
  # every tile/script request. Our explicit selector wait below handles readiness.
  if PAGE_LOAD_STRATEGY in ('normal', 'eager', 'none'):
    co.page_load_strategy = PAGE_LOAD_STRATEGY

  # thrash on the filesystem, better than the page crashing
  # https://stackoverflow.com/a/53970825/659298
  if DISABLE_SHM:
    log.debug("disabling dev-shm-usage")
    co.add_argument("--disable-dev-shm-usage")
  if DISABLE_VIZ:
    log.debug("disabling VizDisplay")
    co.add_argument("--disable-features=VizDisplayCompositor")
  # note: chromium wants '--window-size=w,h' (leading dashes, comma separator);
  # the bare 'window-size=WxH' form is silently ignored.
  co.add_argument(f'--window-size={CANVAS_SIZE.replace("x", ",")}')
  with selenium.webdriver.Chrome(options=co) as browser:
    browser.get(url)

    # https://www.selenium.dev/selenium/docs/api/py/webdriver_support/selenium.webdriver.support.expected_conditions.html
    # https://www.selenium.dev/selenium/docs/api/py/webdriver_support/selenium.webdriver.support.wait.html
    # second argument to WebDriverWait = timeout in seconds
    # wait for the FIRST visible element matching any of MAP_SELECTOR, so we don't
    # burn the full timeout on a selector that doesn't exist in this UI version.
    selectors = [s.strip() for s in MAP_SELECTOR.split(',') if s.strip()]
    def any_visible(browser):
      for sel in selectors:
        try:
          for e in browser.find_elements(selenium.webdriver.common.by.By.CSS_SELECTOR, sel):
            if e.is_displayed():
              log.debug(f"selector matched: {sel}")
              return e
        except selenium.common.exceptions.WebDriverException:
          continue
      return False
    try:
      elem0 = selenium.webdriver.support.wait.WebDriverWait(browser, SELECTOR_TIMEOUT).until(any_visible)
      log.debug("okay, got the basic canvas.")
    except selenium.common.exceptions.TimeoutException as ex:
      log.warning("WE'LL DO IT LIVE.")

    # this doesn't work. but it's an idea.
    #cond = EC.presence_of_all_elements_located( (selenium.webdriver.common.by.By.CSS_SELECTOR, "#iconLayer") )
    #elem1 = selenium.webdriver.support.wait.WebDriverWait(browser, 5).until(cond)
    #log.debug("got the markers.")

    #cond = EC.all_of(*conditions)

    if PAGE_ZOOM and PAGE_ZOOM != 100:
      log.debug(f"zooming: {PAGE_ZOOM}")
      browser.execute_script(f"document.body.style.zoom='{PAGE_ZOOM}%'")

    # Instead of a blind fixed sleep, wait until MAP TILE requests go quiet,
    # capped at LOAD_SLEEP_TIME. We instrument fetch/XHR and count only
    # tile-like requests (images/tiles), because both tar1090 and AIS-catcher
    # stream data-plane updates continuously (aircraft.json polling, WebSockets)
    # and counting ALL requests would never go quiet on tar1090.
    idle_deadline = time.time() + LOAD_SLEEP_TIME
    quiet_period = float(os.environ.get('IDLE_QUIET_PERIOD', 1.0))
    setup_js = r'''
      window.__snapTileActive = 0;
      window.__snapTileLast = performance.now();
      const tileRe = /(tile|\.png$|\.jpg$|\.jpeg$|\.webp$|openstreetmap|arcgis|cartodb|stamen|opentopomap|basemap)/i;
      const track = (url) => {
        try { url = String(url); } catch(e) { return false; }
        return tileRe.test(url);
      };
      const bump = () => { window.__snapTileLast = performance.now(); };
      const ofetch = window.fetch;
      window.fetch = function(...a) {
        const isTile = a[0] && track(a[0].url || a[0]);
        if (isTile) { window.__snapTileActive++; }
        return ofetch.apply(this, a).finally(() => { if (isTile) { window.__snapTileActive--; bump(); } });
      };
      const oopen = XMLHttpRequest.prototype.open;
      XMLHttpRequest.prototype.open = function(m, u, ...rest) {
        if (u && track(u)) {
          window.__snapTileActive++;
          this.addEventListener('loadend', () => { window.__snapTileActive--; bump(); });
        }
        return oopen.call(this, m, u, ...rest);
      };
      return true;
    '''
    poll_js = '''
      return {
        active: window.__snapTileActive || 0,
        quietMs: performance.now() - (window.__snapTileLast || 0)
      };
    '''
    try:
      browser.execute_script(setup_js)
    except selenium.common.exceptions.WebDriverException:
      pass  # page not ready for injection; the cap still bounds us
    while time.time() < idle_deadline:
      try:
        st = browser.execute_script(poll_js) or {}
      except selenium.common.exceptions.WebDriverException:
        break  # page navigating or context gone; don't spin
      active = st.get('active', 0)
      quiet_ms = st.get('quietMs', 0)
      if active <= 0 and quiet_ms >= quiet_period * 1000:
        log.debug(f"tiles idle after {LOAD_SLEEP_TIME - (idle_deadline - time.time()):.1f}s")
        break
      time.sleep(0.25)
    # brief settle so already-loaded tiles finish painting
    time.sleep(float(os.environ.get('SETTLE_TIME', 0.5)))
    ss = browser.get_screenshot_as_png()

  delta_t = time.time() - start_t
  log.debug(f"elapsed time: {delta_t:.2f}sec")

  return ss

routes = [
  Route('/snap', snap_api),
  Route('/snap/{mmsi}', snap_api),
  Route('/favicon.ico', favicon),
]

app = Starlette(routes=routes)

if __name__ == '__main__':
  uvicorn.run(app, host='0.0.0.0', port=5042, log_level='warning')
