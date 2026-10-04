# Huishi Sea Video Cleanup Design

## Goal

The homepage must present exactly two pure-sea video backgrounds: one for the hero and one for the workflow section. No person, luminous human outline, crystal tower, or portal sequence may remain. The navigation keeps the circular `绘` mark but removes the adjacent `绘世` wordmark.

## Approved Media Treatment

- Re-encode the current 15.08-second hero source using only `[0, 8.7)` seconds. This Claude-reviewed cutoff ends before the crystal tips first appear at 9.0 seconds and leaves a safety margin for unobserved frames.
- Publish the result as `static/media/shouyeshipin-sea.mp4` so browsers cannot reuse the old person-containing asset.
- Keep `static/media/huishi-workflow.mp4` unchanged because sampled frames confirm its full 10.05 seconds are pure sea.
- Preserve the existing requestAnimationFrame fade-out, reset, and fade-in loop. Do not add CSS video transitions or overlays.

## Interface Scope

- Change the hero video constant to the new sea-only filename.
- Remove the `home-brand-name` span from the brand link.
- Keep the circular mark, accessible home label, navigation links, layout, typography, theme behavior, and all non-home surfaces unchanged.
- Bump the homepage asset version in `templates/home.html` to invalidate compiled JavaScript caches.

## Verification

- Regression tests assert the new media reference, the absence of the brand-name span, and the exact video digest.
- Asset budget checks cover the new file and stop requiring the removed filename.
- FFprobe verifies an approximately 8.7-second H.264 MP4 with no audio.
- Browser checks sample the new hero throughout playback, verify two video elements, confirm the removed wordmark is absent, and capture desktop/mobile screenshots without console errors.

