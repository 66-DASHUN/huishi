# Huishi Luminous Home Design

## Objective

Refresh the complete public home experience around the bright sky-and-water visual language in the supplied `下载.mp4`. The result must keep the current navigation, authentication, pricing, workspace, and asset entry behavior while replacing the dark visual treatment with a luminous, cinematic one.

## Product Scene

A Chinese visual creator opens Huishi in a normal indoor workspace and should immediately feel the clarity, scale, and possibility of a sunlit imagined world, while still being able to identify the primary creation actions without studying the page.

## Visual Direction: Luminous Worldbuilding

The two full-viewport sections remain because the videos are the product's strongest proof. Interface chrome becomes a restrained overlay on the footage rather than a layer of dark glass placed over it.

- Hero footage: the supplied `C:\Users\dashun\Pictures\下载.mp4`, web-optimized without materially changing brightness, color, timing, or composition.
- Workflow footage: the supplied `F:\AI\AI漫剧\demo\心境\10.mp4`, stored locally and lazy-loaded.
- Palette: cloud white, daylight blue, deep ocean blue, and one restrained sunlight accent.
- Typography: preserve the existing Huishi display/body pairing to avoid an unrelated rebrand, but remove excessive synthetic italics, cramped tracking, and undersized labels.
- Surfaces: no default glass-card grid. Use localized translucent surfaces only where they protect readability or communicate interaction.

## Hero Section

The video is full bleed and remains visibly bright. A localized deep-blue gradient protects the left/lower text zone, with no black layer above 20% opacity across the center of the frame. The sun, cloud, and water highlights remain unobscured.

Desktop content is aligned to the lower-left safe area. It contains a concise product descriptor, the `绘世造镜` headline, supporting copy, primary workspace action, secondary pricing action, and a lightweight utility rail for the existing Prompt/Assets or authenticated Canvas/Prompts/Assets entries. The utility rail uses dividers and open layout rather than repeated cards.

Mobile content centers within the lower half with stable safe-area padding. Actions have at least 44px touch height and stack only when necessary. The next section remains hinted at below the primary content.

## Navigation

The navigation spans the top safe area as a quiet horizontal bar. The brand mark remains visible, desktop links retain their destinations, and authentication actions retain their behavior. It uses a low-opacity blue-white surface, a single subtle divider, and a visible keyboard focus ring. It does not use a large floating pill or decorative glass blur.

## Workflow Section

The local `10.mp4` footage is full bleed and object-fit cover. A small localized blue veil protects the headline and bottom information band without darkening the luminous figure and particles.

The heading and short narrative sit at the upper-left. The three current capabilities become a bottom information band with three columns separated by one-pixel dividers. Each item keeps its icon, title, supporting sentence, and concise English capability terms. The layout is a sequence of capabilities, not three floating cards.

On mobile the capability band becomes a vertically readable list over a stronger bottom-localized blue surface. The video remains the dominant visual signal.

## Authentication Modal

Login and registration behavior, fields, validation, CSRF handling, notices, and links remain unchanged. The modal adopts the daylight palette with a cloud-white form surface, deep-blue ink, blue focus rings, and a sunlight primary action. It uses no wide decorative shadow paired with a border and stays within a 12px card radius.

## Motion And Media

- Videos autoplay muted and inline when motion is allowed.
- Hero media loads immediately; workflow media loads as it approaches the viewport.
- Both videos have local JPEG posters with fixed aspect ratio to prevent layout shift.
- Video loop transitions may crossfade, but content is never hidden waiting for animation.
- `prefers-reduced-motion: reduce` disables entrance effects and smooth motion; poster imagery remains visible and readable.
- All hover effects also have focus-visible equivalents.

## Accessibility And Responsive Requirements

- Text and controls meet WCAG AA contrast in their worst visible video region.
- Body copy is at least 15px and compact labels are at least 12px on desktop, 14px for interactive mobile text.
- Every interactive target is at least 44x44px on touch layouts.
- No horizontal overflow at 375px, 768px, 1440px, or 1920px widths.
- DOM order follows visual reading order and all existing accessible names remain meaningful.
- The login/register dialog stays keyboard accessible and Escape-close behavior is preserved.

## Performance Constraints

- Hero MP4 target: at most 3.2 MB to preserve the existing home asset budget.
- Workflow MP4 target: at most 4.5 MB and loaded only near the second section.
- Each poster target: at most 180 KB.
- No new runtime UI dependency is introduced.
- Generated JS remains under 300 KB and generated CSS under 40 KB.

## Acceptance Criteria

1. `static/js/home.js` references only local hero and workflow media and contains no CloudFront workflow URL.
2. Browser inspection shows the supplied sky/ocean scene in the first viewport and the supplied ice-blue character scene in the workflow viewport.
3. The hero's central video area has no black overlay above 20% opacity and remains materially as bright as its poster.
4. The workflow section uses a divided information band rather than three same-sized glass cards.
5. Existing hero navigation, workspace, pricing, assets, login, and registration interactions still resolve correctly.
6. Desktop and mobile screenshots show no overlap, clipping, unreadable text, or horizontal scroll.
7. Reduced-motion mode removes entrance transitions and video autoplay without blanking either section.
8. Home asset checks, focused home tests, build verification, and the complete relevant test suite pass.

## Scope

This design covers the public home page and its authentication modal. It intentionally does not redesign the authenticated infinite canvas, asset manager, pricing page, or backend behavior.
