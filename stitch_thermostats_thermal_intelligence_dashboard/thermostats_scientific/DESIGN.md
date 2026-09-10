---
name: ThermoStats Scientific
colors:
  surface: '#faf8ff'
  surface-dim: '#d2d9f4'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f3ff'
  surface-container: '#eaedff'
  surface-container-high: '#e2e7ff'
  surface-container-highest: '#dae2fd'
  on-surface: '#131b2e'
  on-surface-variant: '#434655'
  inverse-surface: '#283044'
  inverse-on-surface: '#eef0ff'
  outline: '#737686'
  outline-variant: '#c3c6d7'
  surface-tint: '#0053db'
  primary: '#004ac6'
  on-primary: '#ffffff'
  primary-container: '#2563eb'
  on-primary-container: '#eeefff'
  inverse-primary: '#b4c5ff'
  secondary: '#505f76'
  on-secondary: '#ffffff'
  secondary-container: '#d0e1fb'
  on-secondary-container: '#54647a'
  tertiary: '#006329'
  on-tertiary: '#ffffff'
  tertiary-container: '#007f36'
  on-tertiary-container: '#c7ffca'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b4c5ff'
  on-primary-fixed: '#00174b'
  on-primary-fixed-variant: '#003ea8'
  secondary-fixed: '#d3e4fe'
  secondary-fixed-dim: '#b7c8e1'
  on-secondary-fixed: '#0b1c30'
  on-secondary-fixed-variant: '#38485d'
  tertiary-fixed: '#7ffc97'
  tertiary-fixed-dim: '#62df7d'
  on-tertiary-fixed: '#002109'
  on-tertiary-fixed-variant: '#005320'
  background: '#faf8ff'
  on-background: '#131b2e'
  surface-variant: '#dae2fd'
typography:
  display-metric:
    fontFamily: Inter
    fontSize: 36px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: -0.005em
  body-lg:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 22px
  body-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  data-mono:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: 0.01em
  label-caps:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.06em
  label-compact:
    fontFamily: Inter
    fontSize: 10px
    fontWeight: '700'
    lineHeight: 12px
    letterSpacing: 0.08em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  space-2xs: 2px
  space-xs: 4px
  space-sm: 8px
  space-md: 12px
  space-base: 16px
  space-lg: 20px
  space-xl: 24px
  space-2xl: 32px
  panel-gap: 16px
  panel-padding-compact: 12px
  panel-padding-standard: 16px
  screen-margin: 20px
---

## Brand & Style

This design system delivers the rigor, composure, and clarity of a high-grade laboratory apparatus or mission-critical monitoring terminal. Designed specifically for environmental analysts, geophysicists, and emergency dispatch responders, the interface prioritizes high-density data legibility over decorative flourish. Every pixel serves an operational function: reducing cognitive overhead, clarifying temporal and spatial anomalies, and enabling split-second operational decisions under stress.

The aesthetic philosophy draws from Swiss modernism, aviation telemetry, and specialized technical workstations (such as financial or seismic consoles). Visual noise is eliminated. Surfaces are cool, calm, and grounded in near-white tones, allowing color to be deployed purely as a calibrated metric of severity, certainty, and classification.

## Colors

Color is strictly functional and semantic; decorative color fills are forbidden. The application operates in a bright, hyper-legible light theme to maintain high contrast in varying ambient light conditions (e.g., field tents, incident command mobile units, sunlit control rooms).

### Base Canvas & Structure
- **Canvas / App Background**: `#f6f7f9` provides a cool, low-fatigue backdrop that recedes behind active instruments.
- **Card & Panel Surfaces**: Pure `#ffffff` creates sharp visual separation between distinct modules.
- **Dividers & Structural Rules**: `#e3e6ea` ensures razor-thin containment without visual clutter. For inputs and interactive boundaries, `#cbd5e1` is used.
- **Primary Text**: `#0f172a` (Slate 900) ensures maximum contrast for small data points.
- **Muted Text / Metadata**: `#64748b` (Slate 500) separates supplementary readings from primary signals.

### Telemetry & Hazard Semantics
- **High Alert / Industrial Risk**: `#dc2626` (Red 600)
- **Medium Alert / Watch**: `#f59e0b` (Amber 500)
- **Low Alert / Advisory**: `#2563eb` (Blue 600)
- **Volcanic / Geothermal Activity**: `#7c3aed` (Purple 600)
- **Confirmed Ground Truth / Validated**: `#16a34a` (Green 600)
- **Large Fire Anomaly**: `#b91c1c` (Dark Red 700)
- **Moderate Fire Anomaly**: `#ea580c` (Orange 600)
- **Small Fire Anomaly**: `#eab308` (Yellow 500)
- **Unconfirmed / Inactive / Neutral**: `#64748b` (Slate 500)

## Typography

The type system is powered universally by **Inter** (or system fallback sans-serif), tuned for scientific precision. Crucially, the CSS rule `font-feature-settings: "tnum" 1, "cv05" 1` must be applied globally. Tabular figures (`tnum`) guarantee that rapidly updating live telemetry, coordinates, and temperature readouts do not cause layout jank or misaligned columns.

- **Scale & Density**: Type sizes are intentionally calibrated downward (13px standard body, 11px uppercase labels) to facilitate dense multi-column analytical panels.
- **Hierarchy**: Distinction is maintained through font weight (400, 500, 600, 700) and strict casing rules (uppercase tracking for metadata keys, regular sentence case for narrative summaries).
- **Numbers & Units**: Units of measure (e.g., `°C`, `MW`, `hPa`, `km/h`) sit immediately adjacent to tabular numerals in `body-sm` weight 500, muted with `#64748b`.

## Layout & Spacing

The layout philosophy balances Bloomberg-terminal density inside panels with generous, disciplined breathing room between modular surface containers.

### Modular Grid Structure
- **Global Layout**: A fluid, multi-pane workbench layout that fits the viewport (100vh dashboard paradigm), with panes resizable or collapsible according to monitoring focus.
- **Panel Gaps**: Standard `16px` (`1rem`) uniform spacing between cards prevents visual bleed and anchors each modular component as an isolated sensor surface.
- **Internal Density**: Inside panels, a tight 4px baseline sub-grid operates. Data rows use a compact `28px` to `32px` vertical height to allow comparison of 20+ records without scroll.
- **Responsive Adaptations**:
  - **Desktop (>1440px)**: 4-column multi-panel layouts (Map/GIS center, feeds left/right, timeline bottom).
  - **Laptop (1024px–1439px)**: 3-column arrangement; feeds collapse to tabbed or drawer states.
  - **Tablet/Mobile (<1023px)**: Single-column scrollable stack with persistent global warning banner and floating telemetry drawer.

## Elevation & Depth

Depth is established strictly through **low-contrast outlines, surface luminosity, and subtle ambient occlusion**, rejecting heavy skeuomorphic drops.

- **Base Cards**: Positioned on `#f6f7f9`, panels use pure white `#ffffff` with a crisp `1px solid #e3e6ea` border. No heavy drop shadow is applied—surfaces rely on boundary contrast and an ultra-subtle ambient shadow: `box-shadow: 0 1px 2px 0 rgba(15, 23, 42, 0.04)`.
- **Hover & Focus States**: Interactive rows and actionable cards do not lift in z-space. Instead, the border shifts to `#cbd5e1` and background shifts to `#f8fafc`.
- **Modals & Overlays (Calibration, Diagnostics, Detail Inspectors)**:
  - Elevation level 2: Border `1px solid #cbd5e1`, supported by `box-shadow: 0 10px 15px -3px rgba(15, 23, 42, 0.08), 0 4px 6px -4px rgba(15, 23, 42, 0.04)`.
- **Tooltips & Popovers**: Pure `#0f172a` dark tooltip ground with `#ffffff` text, ensuring high-contrast popover readings over maps and graphs without spatial ambiguity.

## Shapes

The geometric signature combines a defined 10px corner radius on major modular surfaces with sharper, precision-engineered geometry for internal controls.

- **Primary Cards & Sensor Panels**: Fixed at `10px` (`border-radius: 10px`). This provides an intentional, calibrated soften that distinguishes modern analytical dashboards from legacy sharp-edge desktop software.
- **Inputs, Segmented Controls, & Action Buttons**: Set to `6px`. Tighter rounding conveys precise, mechanical reliability.
- **Status Pills & Telemetry Chips**: Set to full pill `9999px` to distinguish status indicators instantly from clickable buttons and square data panels.
- **Left Accent Borders**: High-priority alert cards feature a flat, non-radiused or internally-masked `4px` left edge stripe communicating severity without breaking the outer 10px perimeter.

## Components

### Status Pills & Anomaly Badges
- **Dimensions & Typography**: Height `20px`, padding `0 8px`, `label-compact` typography (10px or 11px uppercase, font-weight 700, letter-spacing `0.08em`).
- **Styling**: Subtle tinted background (10-15% opacity of semantic hue) paired with a solid 1px border and high-contrast text matching the semantic token.
  - *Example (High Alert)*: Background `rgba(220, 38, 38, 0.10)`, border `rgba(220, 38, 38, 0.25)`, text `#dc2626`.
  - *Pill Dot*: Optional 5px circular indicator preceding text.

### Telemetry & Event Cards (Left Accent Border)
- **Structure**: White panel (`#ffffff`), `1px solid #e3e6ea`, `border-radius: 10px`, with a dedicated `4px solid [semantic-color]` left border.
- **Layout**: Header displaying uppercase source/sensor ID on the left with relative timestamp on the right in tabular format. Main metric rendered in `headline-md` or `display-metric` accompanied by inline units and confidence metrics.

### Buttons
- **Primary Operational**: Height `32px`, background `#0f172a`, text `#ffffff`, radius `6px`, font-size `12px`, font-weight `600`. Hover `#1e293b`.
- **Secondary / Action**: Height `32px`, background `#ffffff`, border `1px solid #cbd5e1`, text `#0f172a`. Hover background `#f8fafc`.
- **Destructive / Emergency Override**: Height `32px`, background `#dc2626`, text `#ffffff`. Hover `#b91c1c`.

### Inputs & Filter Bars
- **Style**: Height `32px`, font-size `12px`, tabular digits, background `#ffffff`, border `1px solid #cbd5e1`, radius `6px`, inner padding `0 10px`.
- **Focus**: `border-color: #2563eb`, `outline: 2px solid rgba(37, 99, 235, 0.15)`.

### Data Tables & Sensor Feeds
- **Row Height**: Dense `32px` standard row, `28px` compact row.
- **Borders**: Bottom rule `1px solid #f1f5f9`.
- **Header**: Background `#f8fafc`, text uppercase `11px` `#64748b`, font-weight 600, border-bottom `1px solid #e3e6ea`.
- **Cell Alignment**: Text left-aligned; all numeric values right-aligned with tabular figures enabled.

### Checkboxes & Toggle Switches
- **Checkboxes**: 14px × 14px, radius `3px`, border `1px solid #cbd5e1`. Checked state: background `#0f172a` with white checkmark.
- **Toggle Switches**: Compact width 28px, height 16px, pill shape, thumb 12px with zero shadow. Active track `#2563eb`.