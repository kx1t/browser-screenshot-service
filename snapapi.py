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


BASE_URL = os.environ.get('BASE_URL', 'https://globe.adsbexchange.com/')
# max seconds to wait for tile loading to go quiet (NOT a fixed sleep).
# Fast systems finish much sooner; this is the safe upper bound for slow ones.
LOAD_SLEEP_TIME = float(os.environ.get('LOAD_SLEEP_TIME', 15))
MAP_ARGS = os.environ.get('MAP_ARGS', 'zoom=11&hideSidebar&hideButtons&mapDim=0')
# comma-separated CSS selectors; the first one with a visible element wins.
# .ol-viewport = OpenLayers (tar1090/globe), #map_canvas = legacy tar1090,
# .leaflet-container = Leaflet builds, #map = generic fallback.
MAP_SELECTOR = os.environ.get('MAP_SELECTOR', '.ol-viewport,#map_canvas,.leaflet-container,#map')
SELECTOR_TIMEOUT = float(os.environ.get('SELECTOR_TIMEOUT', 20))
PAGE_LOAD_STRATEGY = os.environ.get('PAGE_LOAD_STRATEGY', 'eager')
PAGE_ZOOM = int(os.environ.get('PAGE_ZOOM', '100'))
DISABLE_SHM = bool(os.environ.get('DISABLE_SHM'))
DISABLE_VIZ = bool(os.environ.get('DISABLE_VIZ'))
MAXTIME = int(os.environ.get('MAXTIME', '30'))
CANVAS_SIZE = os.environ.get('CANVAS_SIZE', '1200x1600')
# extra bounded wait (seconds) for aircraft markers/data to populate AFTER the
# map is ready. tar1090 draws aircraft onto a canvas asynchronously; there is no
# DOM element to wait for, and the data may never arrive for a stale/off-map
# icao. This caps the wait so we always return a (map-only) screenshot.
AIRCRAFT_WAIT = float(os.environ.get('AIRCRAFT_WAIT', 8))
# the marker color to look for, as RRGGBB hex (matches MAP_ARGS monochromeMarkers).
# empty disables the pixel check and just waits AIRCRAFT_WAIT seconds.
MARKER_COLOR = os.environ.get('MARKER_COLOR', 'ff0000').lstrip('#')

async def snap_api(request):
  icao = request.path_params.get('icao', '')
  img = get_screenshot(icao)
  return Response(content=img, media_type='image/png')

async def favicon(request):
  return Response(content=one_by_one_pixel(), media_type='image/gif')

def safe_url(u):
  '''Just seeing if things are fully formed.'''
  u = re.sub(r'[\'"]', '', u)
  if not re.match('^http(s?)://', u):
    u = f"http://{u}"
  return u

def build_url(base, icao, map_args):
  '''Merge the base URL with our query params, even if base already has a query string.'''
  parts = urllib.parse.urlsplit(base)
  path = parts.path or '/'
  if not path.endswith('/'):
    path += '/'
  extra = f'icao={icao}' if icao else ''
  map_args = map_args.lstrip('?&')
  if map_args:
    extra = f'{extra}&{map_args}' if extra else map_args
  query = f'{parts.query}&{extra}' if (parts.query and extra) else (parts.query or extra)
  return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))

def one_by_one_pixel():
  #return base64.b64decode('R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==')
  return b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'

@timeout_decorator.timeout(MAXTIME)
def get_screenshot(icao):
  '''Returns PNG as a binary. Doesn't serve arbitrary URLs because it'd be a security hole.'''

  start_t = time.time()
  icao = icao.upper()
  log.warning(time.strftime('%Y-%m-%d %H:%M:%S') + " hi.")
  ss = one_by_one_pixel()

  # either no ICAO or the correct length.
  if len(icao) and (len(icao) != 6 or not re.match('^[A-F\d]*$', icao)):
    log.error(f"bad ICAO: {icao}")
    return one_by_one_pixel()
  if not BASE_URL:
    log.error("BASE_URL is not set; refusing to browse an empty URL.")
    return one_by_one_pixel()
  _base = safe_url(BASE_URL)
  url = build_url(_base, icao, MAP_ARGS)
  log.info(f"pulling url: {url}")

  co = selenium.webdriver.chrome.options.Options()
  # headless=new: the legacy --headless renders black on modern Chrome (>=132)
  co.add_argument("--headless=new")
  co.add_argument("--no-sandbox")
  # kx1t adds per https://stackoverflow.com/questions/48450594/selenium-timed-out-receiving-message-from-renderer
  co.add_argument("--disable-infobars")
  co.add_argument("--disable-dev-shm-usage")
  co.add_argument("--disable-browser-side-navigation")
  # NOTE: do NOT pass --disable-gpu here. tar1090/globe renders aircraft markers
  # on a WebGL canvas; --disable-gpu kills WebGL in headless and the markers
  # never paint. SwiftShader gives us software WebGL instead.
  co.add_argument("--use-gl=swiftshader")
  co.add_argument("--enable-unsafe-swiftshader")
  # tar1090/globe sits behind Cloudflare. In headless Chrome the default
  # automation fingerprint triggers a Turnstile challenge and the app never
  # loads (no canvases, no aircraft). These flags make headless look like a
  # real browser; without them the map renders but no aircraft ever populate.
  co.add_argument("--disable-blink-features=AutomationControlled")
  co.add_experimental_option("excludeSwitches", ["enable-automation"])
  co.add_experimental_option("useAutomationExtension", False)
  co.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
  co.add_argument("--force-device-scale-factor=1")
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
    # Under CPU starvation, a renderer can go deaf for a long time. Without
    # explicit selenium-level timeouts, a single WebDriver command can block on
    # the chromedriver HTTP socket indefinitely, so timeout_decorator ends up
    # firing mid-command and leaving browser state wedged. Bound every command
    # so we fail fast and cleanly instead.
    browser.set_page_load_timeout(max(10, MAXTIME - 5))
    browser.set_script_timeout(max(10, MAXTIME - 5))
    browser.implicitly_wait(0)  # we do explicit waits; keep implicit at 0
    browser.get(url)

    # wait for the FIRST visible element matching any of MAP_SELECTOR, so we
    # don't burn the full timeout on a selector that doesn't exist in this UI
    # version. Do the whole scan in ONE round-trip: N find_elements + N
    # is_displayed() calls = N HTTP round-trips to chromedriver, each of which
    # can stall under load. A single execute_script is far more resilient.
    selectors = [s.strip() for s in MAP_SELECTOR.split(',') if s.strip()]
    find_visible_js = '''
      const sels = arguments[0];
      for (const sel of sels) {
        for (const e of document.querySelectorAll(sel)) {
          const r = e.getBoundingClientRect();
          const style = window.getComputedStyle(e);
          if (r.width > 0 && r.height > 0 &&
              style.visibility !== 'hidden' && style.display !== 'none') {
            return sel;
          }
        }
      }
      return null;
    '''
    # cap the selector wait so selector + tile-idle + screenshot fit in MAXTIME
    selector_deadline = time.time() + min(SELECTOR_TIMEOUT, max(5, MAXTIME - LOAD_SLEEP_TIME - 8))
    matched = None
    while time.time() < selector_deadline:
      try:
        matched = browser.execute_script(find_visible_js, selectors)
      except selenium.common.exceptions.WebDriverException:
        matched = None
      if matched:
        log.debug(f"selector matched: {matched}")
        log.debug("okay, got the basic canvas.")
        break
      time.sleep(0.5)
    if not matched:
      log.warning("WE'LL DO IT LIVE.")

    if PAGE_ZOOM and PAGE_ZOOM != 100:
      log.debug(f"zooming: {PAGE_ZOOM}")
      browser.execute_script(f"document.body.style.zoom='{PAGE_ZOOM}%'")

    # Instead of a blind fixed sleep, wait until MAP TILE requests go quiet,
    # capped at LOAD_SLEEP_TIME. We instrument fetch/XHR and count only
    # tile-like requests (images/tiles), because tar1090 streams data-plane
    # updates continuously and counting ALL requests would never go quiet.
    remaining_budget = start_t + MAXTIME - time.time()
    idle_deadline = time.time() + max(0, min(LOAD_SLEEP_TIME, remaining_budget - 6))
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

    # Wait for aircraft markers to populate. tar1090 draws aircraft onto a
    # canvas asynchronously; there is no DOM element to wait for. If a
    # MARKER_COLOR is configured, poll the map canvases for pixels of that
    # color (markers); otherwise just wait AIRCRAFT_WAIT seconds. This wait is
    # bounded and non-fatal: a stale/off-map icao yields a map-only screenshot.
    marker_deadline = time.time() + min(AIRCRAFT_WAIT, max(0, start_t + MAXTIME - time.time() - 3))
    if MARKER_COLOR and len(MARKER_COLOR) == 6:
      tr = int(MARKER_COLOR[0:2], 16)
      tg = int(MARKER_COLOR[2:4], 16)
      tb = int(MARKER_COLOR[4:6], 16)
      marker_js = f'''
        let hits = 0;
        for (const c of document.querySelectorAll('canvas')) {{
          try {{
            const ctx = c.getContext('2d');
            if (!ctx) continue;
            const d = ctx.getImageData(0, 0, c.width, c.height).data;
            for (let i = 0; i < d.length; i += 4*311) {{
              if (Math.abs(d[i]-{tr})<48 && Math.abs(d[i+1]-{tg})<48 &&
                  Math.abs(d[i+2]-{tb})<48 && d[i+3]>200) hits++;
            }}
          }} catch(e) {{}}
        }}
        return hits;
      '''
      while time.time() < marker_deadline:
        try:
          if (browser.execute_script(marker_js) or 0) > 20:
            log.debug("aircraft markers detected on canvas.")
            break
        except selenium.common.exceptions.WebDriverException:
          break
        time.sleep(0.5)
    else:
      # no marker color configured; bounded blind wait for data to draw.
      time.sleep(max(0, marker_deadline - time.time()))

    # brief settle so already-loaded tiles/markers finish painting
    time.sleep(float(os.environ.get('SETTLE_TIME', 0.5)))
    ss = browser.get_screenshot_as_png()

  delta_t = time.time() - start_t
  log.debug(f"elapsed time: {delta_t:.2f}sec")

  return ss

routes = [
  Route('/snap', snap_api),
  Route('/snap/{icao}', snap_api),
  Route('/favicon.ico', favicon),
]

app = Starlette(routes=routes)

if __name__ == '__main__':
  uvicorn.run(app, host='0.0.0.0', port=5042, log_level='warning')
