# Pixel Workspace asset contract

Pixel Workspace is a generic renderer. Fleet names, organizations, layouts, and
private character art are runtime data and must not be committed here.

## Character sheets

Each sheet is a transparent PNG with four 64×64 frames per row
(256×640 overall). Rows are fixed:

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
`GET /api/animas/<name>/assets/pixel_sheet.png`. When it is unavailable, every
role uses the bundled `sample_01.png` placeholder.

The `chars` section of `assets/manifest.json` declares `file`, `frameW`,
`frameH`, and each animation's `row`, `frames`, and `fps`.

## Scene

`assets/scene.json` contains dimensions and placement rules only. The browser
uses the `{name, company}` entries from `GET /api/animas` to create company
zones, desk grids, a central `human` desk, meeting areas, and shared props.
Each generated desk uses the bundled 64px desk and chair sprites. Laptop or
desktop PC type and zero to two small props are assigned deterministically from
the anima name.

For seated bust-up characters, render the desk first, the character over it,
then the centered rear-view PC and tabletop props. Align the character's
bottom-edge hands with the tabletop and omit the chair while seated. An
animation can set `deskFront: true` in the manifest to draw the desk after the
character; the bundled `success` row uses this for its raised-hand pose.
Walking characters retain normal y-sort behavior.

A deployment can supply a complete scene at:

`GET /api/workspace/pixel/scene`

The endpoint reads `workspace_pixel/scene.json` beside the configured anima
directory. A 200 response replaces generated layout; a 404 response keeps the
generated layout.

Deployments can also override any bundled asset by placing a file with the same
relative name under `workspace_pixel/assets/`. For example,
`workspace_pixel/assets/scene/desk64.png` replaces the bundled
`assets/scene/desk64.png`, and `workspace_pixel/assets/manifest.json` replaces the
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

Manifest scene entries declare files by stable functional keys. Status bubble
text (作業中 / 思考中 / …) is drawn programmatically with PixelMplus10; only
icon bubbles (`bubble_small_*`) and accent FX remain as sprites. Missing scene
or effect assets may use renderer placeholders, but missing character sheets
should normally use a bundled sample.

All pixel assets are rendered with nearest-neighbor sampling.
