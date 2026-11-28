---
name: live-scene-realism
description: Measure and tune the live scene (feature 013 `showcase`/`realistic` layouts) so the products on the desk look like a real shop live - desk contact, real-world scale against the host's head, light, camera softness, sticker and riser - with a metrics report and side-by-side variants. Use when the live frame or scene looks fake, products look pasted, floating, too big or too bright, or the user asks to make the live layout look real.
---

# Live scene realism

Tune by measuring, one change per variant, and judge by eye on a contact sheet. The scripts never write to the
scene or the code: they render stills to `out/realism/` (gitignored) with temporary overrides.

## Quick start

```bash
S=.claude/skills/live-scene-realism/scripts
export PYTHONIOENCODING=utf-8
F=vendor/livetalking/data/avatars/demo_host_02__ultralight_musetalk/full_imgs/00000000.png  # the streamed frame
R="--content data/products/coca.docx --host-frame $F --head-px 165,335 --real-cm loc-6-chai-coca-cola-355ml=25"
uv run python $S/realism_report.py --out out/realism/base $R
uv run python $S/realism_report.py --out out/realism/v1 $R --layout brightness=0.9
uv run python $S/contact_sheet.py out/realism/sheet.png out/realism/base.png=before out/realism/v1.png="brightness 0.9"
```

Always pass `--content` (the demo data file), or the default cosmetics catalog is used. Always pass `--host-frame`
with a frame of the fork avatar that goes live: the character's `face.png` is only the still preview and can be a
different shot (demo_host_02: desk edge 727 px on `face.png`, 645 px live). `--head-px crown,chin` is
measured once on that frame (832 px high); `--real-cm` takes real product heights from the product data or
the pack; skip both and the scale check is skipped.

## Workflow

Copy this checklist and tick it as you go:

```
- [ ] 1. Baseline: report for no highlight and for each product (`--highlight ID`); view PNG + _zones.png
- [ ] 2. Diagnose: read the flags, then the REFERENCE.md checklist by eye; list the 2-3 worst problems
- [ ] 3. Variants: one change each (`--desk-top`, `--layout`, `--const`, `--soften`, `--feather`); contact sheet; view it
- [ ] 4. Repeat 3 at most ~5 rounds; stop when the flags are gone or the change no longer shows at phone size
- [ ] 5. Check `/host` in Chrome with the fork running (without it `/host` shows the face.png still)
- [ ] 6. Apply (see "Applying"), run the checks, show the user a before/after sheet, update progress/
```

Report flags are heuristics (thresholds in REFERENCE.md). A flag the eye disagrees with is noted, not chased.

## Background behind the host (014)

When tuning the scene for a new customer or a new character, also measure the background:

```bash
L=vendor/livetalking/data/avatars/<id>__<model>/full_imgs
uv run python $S/realism_report.py --out out/realism/bg $R   --background-frames $L=loop out/realism/host_off.png=goc out/realism/host_shop.png=ke_hang
```

```
- [ ] a. Loop frames: no `leak` flag; open each `_leak_loop_*.png` (red = old room kept by the hair/shoulders)
- [ ] b. Background off (`goc`, the original room): no flag at all, or the tool is misreading this character
- [ ] c. Each background style from `/host` (capture cropped to the video frame): no "sharper than the person",
         luma and colour within the thresholds; compare the styles on `bg_backgrounds.png`
- [ ] d. A leak: rerun `uv run python -m ai_live.avatar background-prepare <id>` (014 quickstart), review the masks, then measure again
```

## Shopee app overlay (014 FR-019, ADR-085)

On a phone, the Shopee app covers the top (title, shop row), side chips, the pinned product card, the reward widgets,
the comments and the chat bar, and crops the frame's sides. The report's `Shopee app` lines and `shopee_overlay` in
`<out>.json` give what each hides; `_zones.png` tints the zones pink and darkens the cropped strips.

- The AI label must be hidden 0% (constraint 2) on Shopee: set `AI_LABEL_POSITION=shopee-top` for OBS output (the Meet
  demo default `top-center` sits under the app title, which is fine on Meet, ADR-090).
- A product more than 10% under the UI or past the crop is flagged; in `showcase` set `layout.avoid_app_overlay`
  (ADR-087) to shrink the cluster's depth above the comments and chat bar, or narrow it, or accept a hidden foot.
- `--phone-aspect` tries another screen shape; the zones come from one 9:20 screenshot (TODO in `shopee_overlay.py`).

## Knobs

| Knob | Where | How to try it |
| --- | --- | --- |
| Desk line under the products | `assets/avatars/<id>/character.json` `scene.desk_top` | `--desk-top 0.78` |
| Layout params (`mode`, `riser`, `sticker`, `avoid_app_overlay`, `brightness`, `max_slots`, `cards`, `stock`, `price_tags`, `promo_banner`) | `assets/scenes/<id>/scene.json` `layout` | `--layout riser=false brightness=0.9` |
| Sizes, sticker, shadows, dim | constants in `src/ai_live/scene/layout.py`, `render.py` | `--const SHOWCASE_MAIN_HEIGHT=0.28` |
| Camera softness, edge feather | `CAMERA_BLUR_PX`, `CAMERA_FEATHER_PX` in `render.py` (FR-029) | `--const CAMERA_BLUR_PX=1.0`; `--soften`/`--feather` add on top |
| Room light match (gray-world) | experiment only | `--harmonize 0.7` (changes hue: see FR-006) |

Change sizes as a set: when the main product shrinks, `SHOWCASE_BACK` must shrink too, or the back products end
up bigger than the main one. Size from real heights: target px = real_cm x (head_px / 23 cm) x 1.0-1.45 for
front products, 0.85-1.2 for back ones.

## Applying

- `scene.json` and `character.json` are local, gitignored config: tune them directly, then restart the app
  (the scene loads at start-up) and recheck `/host`.
- A code constant or a new effect (blur, feather, sizing rule) changes 013 behaviour: edit
  `specs/013-realistic-desk-products/spec.md` first, add an ADR in `docs/DECISIONS.md`, a task in `tasks.md`,
  tests, then `uv run pytest` and `uv run ruff check . && uv run ruff format --check .`.

## Rules

- The AI label stays visible; no variant may cover it, the face (chin up) or the frame edge.
- 013 FR-006: brightness may change a little, colour (hue), text, labels and shape of a product may not.
  `--harmonize` is for diagnosis only.
- Realistic size is also a Shopee rule (nothing misleading): never make a product look bigger than it is.
- Never commit stills, product photos or the host frame; `out/` and `assets/` are gitignored.

## Reference

Checklist, metric meanings, thresholds and the knob map: [REFERENCE.md](REFERENCE.md).
