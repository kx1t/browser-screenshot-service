# browser-screenshot-service
web browser screenshot as a service! Designed for the [mikenye ADSB decoding](https://mikenye.gitbook.io/ads-b/) world.

# execution example

    docker run -p 5042:5042 \
      -e MAP_ARGS='zoom=11&hideSidebar&hideButtons&mapDim=0.3' \
      -e BASE_URL='https://ramonk.net/tar1090/' -it tedder42/browser-screenshot-service:latest

    curl http://localhost:5042/snap/a9b67c

Fix the URL, make sure the ICAO actually exists, use upper or lower case. Some of the environment vars were listed to show what might be put in there.

There's a bit of sanity testing against the ICAO code in the URL. Enter something invalid and it'll return a 1x1 pixel.

These are the environment variables that are supported:
| Variable | Values | Description |
|---|---|---|
| BASE_URL | The base URL of your `tar1090` instance. Default: https://globe.adsbexchange.com/ | This determines the base URL of the location where the `screenshot` container will browse to get the image. Point it at the application root. Query strings are now merged correctly, so an existing `?foo=bar` in BASE_URL won't break the URL, but map-specific settings preferably belong in MAP_ARGS. |
| LOAD_SLEEP_TIME | Positive integer values. Default = 15 | Maximum seconds to wait for map tile loading to go quiet before taking the screenshot. This is a cap, not a fixed sleep: on fast systems the screenshot fires as soon as tiles stop loading (often 3–8s), while slow systems (Pi 3/4) get up to this many seconds. Increase if screenshots show incompletely rendered pages; decrease only if you're sure your hardware renders faster. |
| IDLE_QUIET_PERIOD | Seconds. Default: `1.0` | How long the network must be quiet (no new tile requests) before the page is considered rendered. |
| SETTLE_TIME | Seconds. Default: `0.5` | Brief fixed delay after tiles finish loading, so they finish painting before the screenshot. |
| MAP_ARGS |  Default: `zoom=11&hideSidebar&hideButtons&mapDim=0` Example/recommended value: `zoom=11.5&hideSidebar&hideButtons&mapDim=0.2&monochromeMarkers=ff0000&outlineColor=505050&iconScale=1.5&enableLabels&extendedLabels=2&trackLabels` | Arguments passed to the `tar1090` URL. |
| MAP_SELECTOR | Comma-separated CSS selectors. Default: `.ol-viewport,#map_canvas,.leaflet-container,#map` | The container waits for the first visible element matching any of these selectors before rendering. `.ol-viewport` works for current OpenLayers-based tar1090 and AIS-catcher interfaces; `#map_canvas` covers legacy versions. Override if your interface uses a different map element. |
| SELECTOR_TIMEOUT | Positive number. Default: `20` | Maximum seconds to wait for one of the MAP_SELECTOR elements to become visible. If none appears, the screenshot is still taken after this timeout. |
| PAGE_LOAD_STRATEGY | `eager` / `normal` / `none`. Default: `eager` | Chrome page load strategy. `eager` returns control at DOMContentLoaded instead of waiting for all map tile requests, which speeds up screenshot generation; the MAP_SELECTOR wait still ensures the map is present. |
| PAGE_ZOOM | Positive integer between `1` and `100`. Default: `100` | Browser page zoom |
| DISABLE_SHM | `true` / `false`. Default: `false` | Disable use of Shared Memory |
| DISABLE_VIZ | `true` / `false`. Default: `false` | Disable the internal browser's visual display |
| MAXTIME | Positive integer values. Default = 30 | Maximum time in seconds the container will wait to render a screenshot before giving up completely. If the container often shows time-out logs, increase this value. |
| CANVAS_SIZE | `width`x`height`. Default: 1200x1600 | Size (`width`x`height` in pixels) of the rendered screenshot |
