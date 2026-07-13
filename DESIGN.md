---
name: Pulse Sentinel
colors:
  surface: '#0b141c'
  surface-dim: '#0b141c'
  surface-bright: '#313a43'
  surface-container-lowest: '#060f16'
  surface-container-low: '#141c24'
  surface-container: '#182028'
  surface-container-high: '#222b33'
  surface-container-highest: '#2d363e'
  on-surface: '#dae3ee'
  on-surface-variant: '#bdc8d0'
  inverse-surface: '#dae3ee'
  inverse-on-surface: '#29313a'
  outline: '#879299'
  outline-variant: '#3e484e'
  surface-tint: '#6fd2ff'
  primary: '#6fd2ff'
  on-primary: '#003547'
  primary-container: '#16a9da'
  on-primary-container: '#00394d'
  inverse-primary: '#006686'
  secondary: '#c3c6cf'
  on-secondary: '#2d3137'
  secondary-container: '#454950'
  on-secondary-container: '#b5b8c1'
  tertiary: '#ffba49'
  on-tertiary: '#442b00'
  tertiary-container: '#d38f00'
  on-tertiary-container: '#492f00'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#c0e8ff'
  primary-fixed-dim: '#6fd2ff'
  on-primary-fixed: '#001f2b'
  on-primary-fixed-variant: '#004d66'
  secondary-fixed: '#dfe2eb'
  secondary-fixed-dim: '#c3c6cf'
  on-secondary-fixed: '#181c22'
  on-secondary-fixed-variant: '#43474e'
  tertiary-fixed: '#ffddb1'
  tertiary-fixed-dim: '#ffba49'
  on-tertiary-fixed: '#291800'
  on-tertiary-fixed-variant: '#624000'
  background: '#0b141c'
  on-background: '#dae3ee'
  surface-variant: '#2d363e'
typography:
  display-metrics:
    fontFamily: JetBrains Mono
    fontSize: 48px
    fontWeight: '700'
    lineHeight: '1.1'
    letterSpacing: -0.05em
  headline-lg:
    fontFamily: Geist
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
  headline-md:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-mono:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.02em
  headline-lg-mobile:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  gutter: 20px
  margin-mobile: 16px
  margin-desktop: 32px
  container-max: 1600px
---

## Brand & Style
The design system is engineered for high-stakes infrastructure monitoring, evoking the atmosphere of a futuristic Network Operations Center (NOC). It prioritizes rapid information synthesis, technical precision, and a sense of "active surveillance." The aesthetic is a fusion of **Glassmorphism** and **Corporate Modernity**, utilizing deep, layered transparency to maintain a lightweight feel despite high data density. The target audience—DevOps engineers and security analysts—expects a UI that feels like a sophisticated tool, where every pixel serves a functional purpose. The emotional response is one of calm control amidst high-velocity data.

## Colors
The palette is rooted in a "Deep Space" dark mode. The base background is a near-black charcoal, while surfaces use a semi-transparent slate to create depth.
- **Primary (Cyan/Teal):** Used for "Active" states, progress bars, and primary actions. It represents the "pulse" of the system.
- **Secondary (Slate):** Forms the structural foundation and inactive states.
- **Warning/Alert (Amber & Red):** Reserved strictly for "Days to Exhaustion" thresholds and security vulnerabilities.
- **Data Visualization:** Use high-vibrancy gradients of the primary color to indicate velocity and flow.

## Typography
The system employs a tri-font strategy to balance character and utility. 
- **Geist** provides a sharp, technical edge for headings.
- **Inter** ensures maximum legibility for body text and descriptive content.
- **JetBrains Mono** is the workhorse for all telemetry, code snippets, and "Days to Exhaustion" counters, lending a programmatic feel to the data. 

All tabular data and numerical metrics must use tabular figures (monospaced) to prevent UI jitter during real-time updates.

## Layout & Spacing
The layout utilizes a **Modular Grid** system. On desktop, a 12-column grid is standard, but content is largely organized into a "Bento Box" style layout of variable-height cards.
- **Density:** High. Use compact padding (12px–16px) within components to maximize the visible data on a single screen.
- **Responsive:** On mobile, the 12-column grid collapses to a 1-column stack. Metrics like "Usage Velocity" transition from horizontal sparklines to simplified vertical gauges.
- **Alignment:** All elements must snap to a 4px baseline grid to maintain the "engineered" precision of a technical dashboard.

## Elevation & Depth
Depth is communicated through **Glassmorphism** rather than traditional drop shadows.
- **Tiers:** Level 0 is the background. Level 1 cards use a `backdrop-filter: blur(12px)` with a 1px solid border at 10% opacity white.
- **Active State:** Focused or "Alert" cards increase border opacity and add a subtle outer glow using the primary cyan or warning amber.
- **Overlays:** Modals and tooltips use a higher blur (20px) and a slightly darker tint to isolate them from the complex background data.

## Shapes
The design system uses a **Soft (0.25rem)** roundedness approach. This maintains a crisp, professional "instrument panel" look while avoiding the harshness of 90-degree angles. 
- Cards and containers: `4px` (rounded-sm).
- Status pills and small buttons: `2px` or `4px` depending on size.
- Avoid fully rounded "pill" shapes for buttons to maintain the serious, high-tech aesthetic.

## Components
- **Metrics Cards:** The core component. Must feature a "primary value" (e.g., 4.2 days), a "velocity indicator" (sparkline), and a "threshold status" (cyan/amber/red).
- **Glass Buttons:** Subtle slate backgrounds with cyan borders. On hover, the border glow intensifies.
- **Telemetry Lists:** High-density rows with monospaced timestamps. Every third row should have a subtle zebra-stripe at 2% opacity for horizontal tracking.
- **Usage Gauges:** Semi-circular or linear progress bars using a "glow" effect for the filled portion.
- **System Badges:** Small, monospaced labels used for tagging microservices or regions, featuring a low-opacity background tint of the status color.
- **Activity Heatmaps:** Grid-based visualization (GitHub style) showing system load or security events over time.