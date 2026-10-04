# Huishi UI Corrections Design

## Scope

This pass changes four surfaces only: workspace settings menu, canvas bottom controls, admin configuration pages, and homepage media files.

## Workspace Settings

- Reduce the menu from 228px to 176px.
- Keep account, recharge, admin and logout as first-level commands.
- Render Theme as a first-level disclosure row with the current preference on the right.
- Expanding Theme reveals three indented options: Light, Dark and System.
- Preserve `data-theme-option`, `aria-pressed`, local storage and iframe theme synchronization.

## Canvas Controls

- Keep the zoom HUD and main toolbar in one bottom Rail.
- At wide desktop widths, center the main toolbar against the full available canvas section and pin the zoom HUD to the Rail's left edge.
- At medium widths, keep a collision-free two-column layout.
- Move low-frequency commands into a More popover so the visible toolbar is shorter.
- Use neutral toolbar hover/active colors and a neutral range accent. Canvas selection outlines may retain their semantic selection color.
- Because the toolbar lives inside the flexing canvas section, opening Agent naturally recenters it in the remaining canvas; closing Agent recenters it in the full canvas.

## Admin Configuration

- Remove Configuration Overview from navigation and from `config_nav_sections()`.
- `/admin/config` redirects to `/admin/config/settings`.
- The Configuration Center parent link points to System Configuration.
- Keep System Configuration, Billing Rules and Package Description as the only child entries.
- Add complete `.admin-console-page` scoped layout rules for the three pages instead of restoring the legacy `console-page` body class.
- Preserve permissions, CSRF, update forms, delete confirmations and audit behavior.

## Homepage Media

- Deploy `D:\AI\huishiv2\static\media\shouyeshipin.mp4` as `/static/media/shouyeshipin-home.mp4`.
- Deploy `C:\Users\dashun\Pictures\下载.mp4` as `/static/media/huishi-workflow.mp4`.
- Keep the existing `FadingVideo` rAF loop and poster fallback.
- Update asset budgets to reflect the explicitly requested source files.

## Acceptance

- Settings panel width is no more than 180px and Theme is collapsed by default.
- Main toolbar center matches the canvas section center on wide desktop with Agent both open and closed.
- Main toolbar uses no blue active surface or blue range accent.
- `/admin/config` redirects to System Configuration and no visible Configuration Overview label remains.
- All three configuration pages have stable headers, forms and cards in light and dark themes.
- Deployed media SHA-256 hashes match the two user-provided source files.

