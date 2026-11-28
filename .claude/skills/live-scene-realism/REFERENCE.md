# Live scene realism: reference

## Realism checklist (look at the still at phone size, then at 100%)

1. **Desk contact.** Every product's foot sits on the desk top seen in the frame, not on the character's
   configured line. The report finds the desk edge (strongest colour step below 0.55 H, measured only in the
   outer 12% of the width on each side, away from the host) and warns when `character.json` `scene.desk_top` is
   more than 12 px off. Floating bottles in front of the body are this bug. Measured over the full width the
   detector locked onto the dark shirt meeting the arms (demo_host_02 live: 611 px found, desk at 649); it can
   still lock onto a shelf edge at the frame sides: confirm on the `_zones` image. Measure on the fork frame, not
   `face.png`.
2. **Scale against the head.** An adult head is about 23 cm crown to chin. Products in front of the host are
   closer to the camera, so they look 1.0-1.45x their real size against the head; back products 0.85-1.2x.
   A 25 cm six-pack drawn as tall as the head and a half looks like a prop.
3. **Size order.** The main product is the biggest unless it is really smaller; back products never outgrow it.
4. **Exposure.** A product's brightest pixels (p95 luma) should not beat the room around it by more than 20:
   studio product photos are lit separately and glow. Lower `layout.brightness` (FR-006 allows it).
   A dark bottle being darker than the room is normal and not flagged.
5. **Light colour.** White parts of the product vs neutral parts of the room above the desk (R-B difference). Over
   12 shows a cool photo in a warm room. FR-006 bans recolouring, so the fix is a photo shot under similar light.
6. **Camera softness.** The live avatar is a soft video frame; a crisp product photo looks pasted. Interior
   sharpness (Laplacian variance) over the room ring around it should be 0.4-2.5. Mild blur (0.5-1 px) fixes it.
7. **Edges.** A hard cut-out edge outlines the product. Share of soft alpha along the rim under 0.15 is flagged.
8. **Contact shadow.** A dark, tight shadow right under the foot and a soft wide one; no gap between foot and shadow.
9. **Hands and body.** Real hosts show their hands and part of the body; products covering the whole torso look
   staged. The report prints how much of the hands zone and of the frame the products cover.
10. **Props.** The riser and the price sticker should look like real props: the riser on the desk, the sticker small
    enough not to cover the product's bottles, labels or cap.
11. **Perspective.** The camera looks slightly down at the desk; tops of round products and the riser show as flat
    ellipses. A product photo shot from far above or below will not fit.

## Report metrics (`<out>.json`)

| Field | Meaning | Flag |
| --- | --- | --- |
| `character_desk_top_px`, `detected_desk_edge_px` | configured vs seen desk edge | differ > 12 px |
| `height_px`, `scale_vs_head` | drawn height; scale against the head, needs `--head-px`, `--real-cm` | outside the front/back range |
| `foot_vs_desk_edge_px` | foot y minus the seen desk edge (negative floats) | foot above the edge |
| `p95_luma`, `room_p95_luma` | brightest product pixels vs a 14 px ring of the host frame around it | product > room + 20 |
| `warm_diff` | product neutral R-B minus room neutral R-B | abs > 12 |
| `sharpness_ratio` | product interior vs room ring Laplacian variance | outside 0.4-2.5 |
| `soft_edge_share` | share of rim pixels with soft alpha | < 0.15 |
| `overlaps`, `hands_zone_covered`, `products_share_of_frame` | layout facts, judged by eye | product overlap |

All thresholds are heuristics measured on the demo frame (2026-11-23), not rules. Change them in
`scripts/realism_report.py` when a scene proves them wrong.

## Background metrics (`--background-frames`, 014)

Each `PATH[=LABEL]` set is a folder of frames or one image; the result is under `background` in `<out>.json`.
Masks, `desk_top_px` and the original room come from `assets/avatars/<id>/background/` (`--background-dir`).

| Field | Frames | Meaning | Flag |
| --- | --- | --- | --- |
| `leak_px`, `leak_blob_px` | loop frames (`full_imgs`, byte-equal crc32 to a mask) | R12: kept pixels near the edge whose colour bin is > 4x likelier in the old room than in the person; largest 8-connected blob | blob > 150 px: `leak: ...` |
| `leak_marked` | flagged and worst loop frame | new background green, leak pixels red | |
| `sharpness_ratio` | `/host` captures | Laplacian variance background / person | > max(1.0, 1.1 x the original room's ratio): "background sharper than the person" (nền sắc hơn người) |
| `luma_diff` | `/host` captures | (background - person luma) minus the same in `preview_frame.png` | abs > 20: brighter / darker |
| `warm_diff` | `/host` captures | (background - person R-B, unclipped pixels) minus the same in the original room | abs > 12: warmer / cooler |
| `regions_px`, `reference` | all | stable regions: person (alpha >= 128) or room (alpha 0) in every mask, shrunk 4 px, above the desk, minus products and the AI label | |

- The leak index is a numpy port of `ailive_ext/background_prep.leak_map` (cv2 chamfer distance and fixed-point Lab
  bins reproduced): on demo_host_02 all 81 loop frames give the same numbers as the fork (2026-11-25; 10 flagged,
  max blob 214 px, as in `manifest.json`).
- `/host` captures have no mask of their own (the AI label and the products change the bytes), so they get only
  sharpness, light and colour. Crop the capture to the video frame: a capture whose aspect differs from the manifest
  by more than 2% is `skipped`.
- `cannot measure`: the person region is flat (a mask or a blank capture passed by mistake); `warm_diff` is `null`
  when a region is almost all clipped (> 250).
- The original-room frame (background off) must give no leak and no flags: run it once per new character to make
  sure the tool does not report a false leak.
- TODO: thresholds 150 px / 20 luma / 12 R-B / 1.1x are from research R12 and the 013 product checks, not yet
  measured on real `/host` frames with a new background. Re-check them on the T048 GPU run and adjust here.

## Shopee overlay metrics (`shopee_overlay` in `<out>.json`, 014 FR-019)

| Key | Meaning | Flag |
| --- | --- | --- |
| `shown_box` | the frame part a phone shows (aspect fill; ~53 px cut on each side of 480x832) | |
| `label.share`, `label.zones` | share of the estimated AI label box hidden by a zone or the crop | > 0 (`OVERLAY_LABEL_MAX`) |
| `products.<id>.covered_share` | share of the product mask under a zone | > 0.10 (`OVERLAY_PRODUCT_MAX`) |
| `products.<id>.cropped_share` | share of the product mask outside `shown_box` | > 0.10 |

Zones (fractions of a 9:20 screen, `src/ai_live/scene/shopee_overlay.py`): `header` y 0-11.5%, `badges_left`,
`pinned_product`, `rewards_right`, `comments` y 83-91%, `chat_bar` y 93-98.5%.
- TODO: measured on one screenshot (2026-11-25); check on a test live or a real phone whether the app crops
  (aspect fill) or letterboxes, and re-measure if the app's layout changes.
- The 0.10 product threshold is a heuristic: a hidden foot under the comments may be acceptable to the eye.

## Knob map

| Knob | Effect | Note |
| --- | --- | --- |
| `character.json` `scene.desk_top` | where every foot stands | match the seen desk edge |
| `character.json` `scene.hands_zone` | `realistic` keeps it clear; `showcase` ignores it | |
| `layout.mode` | `showcase` (centre product + back ones), `realistic`, `rows` (009) | |
| `layout.brightness` | product exposure, 0.8-1.05 | FR-006 |
| `layout.riser`, `layout.sticker` | white round riser, price sticker | price text from the data file only |
| `SHOWCASE_MAIN_HEIGHT`, `SHOWCASE_MAIN_MIN_HEIGHT` | main product height, x H | FR-025 range |
| `SHOWCASE_BACK` | (side, height x H, depth) per back product | shrink with the main one |
| `STICKER_PX` | sticker diameter on an 832 px frame | |
| `REALISTIC_DIM`, `HIGHLIGHT_*` | dim of non-highlighted products, highlight glow and growth | FR-022 |
| `CONTACT_SHADOW_*`, `SOFT_SHADOW_*` | the two shadow layers | FR-005 |
| `CAMERA_BLUR_PX`, `CAMERA_FEATHER_PX` | product blur and inward edge fade, px on 832 | FR-029; `rows` untouched |

## Script options (`realism_report.py`)

`--scene`, `--content`, `--host-frame` (default the character's `face.png`; pass a `/host` screenshot to check the
lip-sync frame), `--highlight ID`, `--desk-top F`, `--layout k=v ...`, `--const NAME=python-literal ...`,
`--head-px crown,chin`, `--real-cm id=cm ...`, `--harmonize K`, `--soften px`, `--feather px`.
Outputs `<out>.png`, `<out>_zones.png` (forbidden zones, desk line, boxes, Shopee app zones) and `<out>.json`.
`--background-frames PATH[=LABEL] ...` adds the background metrics, `<out>_leak_<label>_<frame>.png` and the
side-by-side sheet `<out>_backgrounds.png`; `--background-dir` overrides `assets/avatars/<AVATAR_ID>/background`.
`--phone-aspect F` (default 0.45, a 9:20 phone) sets the screen shape for the Shopee overlay zones.
