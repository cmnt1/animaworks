# Battle artwork

Generated for AnimaWorks with the built-in `image_gen` tool on 2026-09-13. These are original fantasy pixel-art assets, not extracted game assets. Final PNGs are checked into this directory; no generated-image cache paths are required at runtime.

- `moonlit-ruins.png`: 1536×1024 background.
- `combatants.png`: 1254×1254 RGBA atlas with real transparent alpha, four columns × two rows. Top: spellblade, scholar, engineer, healer (left-facing). Bottom: slime, winged eye, golem, dragon. The renderer computes a tight source rectangle inside each cell and draws with nearest-neighbor sampling. The canvas edges and gaps between cells are transparent.

## Background prompt

```text
Use case: stylized-concept. Asset type: pixel art game battle background for a real-time AnimaWorks task battle page inspired by 16-bit Japanese RPG battles. Create an ORIGINAL panoramic 1536x1024 raster pixel-art environment: moonlit ancient aqueduct and mossy stone terrace, teal mountains and dark cypress silhouettes, enormous pale turquoise moon, subtle warm gold lights in distant ruins, rich dark navy night sky. Bottom 55 percent is a broad empty side-view stone battlefield platform, darkest at the bottom; leave it unobstructed for enemy sprites on the left and small heroes on the right. Crisp large visible square pixels, limited SNES-era palette, detailed atmospheric layered landscape, no anti-aliased painting, no blur. No characters, no monsters, no text, no menus, no borders. Premium beautiful game art, dramatic but quiet and readable. This is a reusable BACKGROUND asset only.
```

## Combatant atlas prompt

```text
A TRANSPARENT BACKGROUND PNG pixel-art sprite atlas. Eight small, fully isolated sprites arranged in a precise FOUR COLUMNS by TWO ROWS grid. Very wide empty transparent margins between every sprite, 50% of the canvas is EMPTY transparent space. Each sprite is much smaller than its cell, occupies only 60% of cell width maximum. Fully visible bodies and weapons. Top row, from left to right: silver-haired teal cloaked sword hero facing left; violet hooded staff mage facing left; auburn ponytail bronze armor hammer engineer facing left; white and emerald robed orb healer facing left. Bottom row: teal horned slime facing right; violet winged eye facing right; mossy stone golem with yellow crystal facing right; crimson small dragon facing right. Original 16-bit Japanese fantasy RPG sprites, crisp square pixel clusters, dark outlines, limited jewel palette, expressive battle-ready poses. All four characters and all four monsters must remain separate from each other, with absolutely no touching. No rendered background, no scenery, no text, no shadows, no checkerboard, no grid lines. Actual transparent alpha background. One square PNG.
```

## Personal battle sheets

Generated with the built-in `image_gen` tool, using each Anima's existing `avatar_fullbody.png` as an identity reference. New files are saved separately as `animas/<name>/assets/battle_sheet_v1.png` under the runtime data directory. The original portrait, Pixel sheet, and other assets remain untouched. Exact character-specific prompts, reference hashes, and pose order are recorded alongside each sheet in `battle_sheet_v1.json`. These private runtime files are intentionally outside Git.

Reusable final prompt specification (append the character's observed hair, eyes, signature colors, accessories, and chosen fantasy weapon):

```text
Transparent background PNG. Create a 16-bit pixel-art BATTLE SPRITE SHEET, 4 columns × 2 rows, eight small full-body versions of ONE character. Reference image is identity only, do not reproduce portrait format. Square 1024×1024 atlas: centers at (128,256),(384,256),(640,256),(896,256),(128,768),(384,768),(640,768),(896,768). Each sprite including weapon fits inside 180×250 pixels, generous empty transparent gaps. Facing LEFT. Row1: ready, guarding, casting, slashing. Row2: thrusting, jumping strike, recoiling hurt, victory. Consistent scale and costume, chunky visible pixels, SNES palette, dark outline. Genuine transparent alpha background. No labels, borders, scenery, floor or shadow. Character: [reference-derived identity and weapon].
```

Actual generated outputs are 1254×1254 RGBA. The renderer identifies the eight dominant alpha islands so pose bounds need not align exactly to grid cells. Source PNGs remain unchanged; decoded pose textures exist only in browser memory.
