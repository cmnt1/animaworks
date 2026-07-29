# Pixel Workspace asset contract

Pixel Workspace is a generic renderer. Fleet names, organizations, layouts, and
private character art are runtime data and must not be committed here.

## Character sheets

Each sheet is a transparent PNG with four 96×96 frames per row
(384×960 overall). Rows are fixed:

| Row | State |
| ---: | --- |
| 0 | idle |
| 1 | working |
| 2 | thinking |
| 3 | talking / reporting |
| 4 | walk down |
| 5 | walk up |
| 6 | walk side |
| 7 | sleeping |
| 8 | success |
| 9 | error |

At startup the renderer probes
`GET /api/animas/<name>/assets/pixel_sheet.png`. When it is unavailable, the
anima name is hashed to one of `sample_01.png` through `sample_06.png`.
`human.png` and the two customer sheets are reserved generic roles.

The `chars` section of `assets/manifest.json` declares `file`, `frameW`,
`frameH`, and each animation's `row`, `frames`, and `fps`.

## Scene

`assets/scene.json` contains dimensions and placement rules only. The browser
uses the `{name, company}` entries from `GET /api/animas` to create company
zones, desk grids, a central `human` desk, meeting areas, and shared props.
Desk items use `item_01.png` through `item_14.png` in deterministic desk order.

A deployment can supply a complete scene at:

`GET /api/workspace/pixel/scene`

The endpoint reads `workspace_pixel/scene.json` beside the configured anima
directory. A 200 response replaces generated layout; a 404 response keeps the
generated layout.

Deployments can also override any bundled asset by placing a file with the same
relative name under `workspace_pixel/assets/`. For example,
`workspace_pixel/assets/scene/desk.png` replaces the bundled
`assets/scene/desk.png`, and `workspace_pixel/assets/manifest.json` replaces the
bundled manifest. The renderer requests runtime files first and falls back to
the bundled copy when no override exists.

Full scene objects contain:

- `canvas`: logical width, height, and tile size
- `human_id`: normally `human`
- `zones`: labeled floor rectangles
- `desks`: IDs mapped to tile, company, and optional item
- `props`: sprite placement and optional `under`, `kind`, and company metadata
- `walk.cross_company_via`: shared routing waypoint
- `lighting`: day and night settings

## Effects and scene assets

Manifest scene entries declare files by stable functional keys. Status bubbles
use the fixed rows in `fx/bubbles.png`; the same state must always resolve to
the same manifest key. Missing scene or effect assets may use renderer
placeholders, but missing character sheets should normally use a bundled sample.

All pixel assets are rendered with nearest-neighbor sampling.
