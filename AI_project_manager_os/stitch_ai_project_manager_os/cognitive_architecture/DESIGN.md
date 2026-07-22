---
name: Cognitive Architecture
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#434654'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#747686'
  outline-variant: '#c4c5d7'
  surface-tint: '#1d52d8'
  primary: '#0848d0'
  on-primary: '#ffffff'
  primary-container: '#3563e9'
  on-primary-container: '#f0f1ff'
  inverse-primary: '#b6c4ff'
  secondary: '#6346c7'
  on-secondary: '#ffffff'
  secondary-container: '#977cff'
  on-secondary-container: '#2d0086'
  tertiary: '#4d566b'
  on-tertiary: '#ffffff'
  tertiary-container: '#656e84'
  on-tertiary-container: '#eff1ff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dce1ff'
  primary-fixed-dim: '#b6c4ff'
  on-primary-fixed: '#00164f'
  on-primary-fixed-variant: '#003ab1'
  secondary-fixed: '#e7deff'
  secondary-fixed-dim: '#ccbeff'
  on-secondary-fixed: '#1e0060'
  on-secondary-fixed-variant: '#4b2aae'
  tertiary-fixed: '#d9e2fc'
  tertiary-fixed-dim: '#bdc6e0'
  on-tertiary-fixed: '#121b2e'
  on-tertiary-fixed-variant: '#3e475b'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  display-lg:
    fontFamily: Manrope
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
    letterSpacing: -0.02em
  display-lg-mobile:
    fontFamily: Manrope
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 36px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Manrope
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-sm:
    fontFamily: Manrope
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  2xl: 48px
  container-max: 1440px
  gutter: 24px
---

## Brand & Style

The design system is built for a high-stakes professional environment where data density and clarity are paramount. The brand personality is **Intelligent, Calm, and Structured**. It aims to reduce cognitive load by using a highly organized visual hierarchy that feels precise rather than overwhelming.

The design style is **Corporate Modern with a "Glass-Precise" touch**. It utilizes a clean, systematic approach characterized by:
- **Logical Grouping:** Information is housed in distinct white panels against a warm, neutral background to define workspaces clearly.
- **Purposeful Color:** Color is never decorative; it is a functional tool used to denote status, AI-driven insights, and system health.
- **Refined Interaction:** Hover states and transitions are subtle, reinforcing a sense of stability and professional reliability.
- **Focus on Clarity:** High contrast ratios and generous whitespace within components ensure that the "AI" aspect feels like an assistive partner rather than a black-box complexity.

## Colors

This color palette is designed for prolonged professional use, prioritizing legibility and accessibility (WCAG 2.2 AA).

- **Core Palette:** The Deep Navy (#172033) provides a strong structural anchor for navigation, while Cobalt Blue (#3563E9) acts as the primary action color. Violet (#7357D8) is reserved exclusively for AI-augmented features and recommendations.
- **Semantic System:** Status colors follow a "traffic light plus" model. Emerald, Amber, and Red are calibrated for high visibility against both white and off-white backgrounds.
- **Neutral Scale:** Use Slate shades for typography. 
    - **Slate 900 (#0F172A):** Primary headings and black text.
    - **Slate 600 (#475569):** Body text and secondary labels.
    - **Slate 400 (#94A3B8):** Icons and placeholder text.
    - **Slate 200 (#E2E8F0):** Standard borders and dividers.

## Typography

The system utilizes a dual-font strategy. **Manrope** is used for headings to provide a modern, professional, and slightly geometric character. **Inter** is used for all UI elements, body text, and data-heavy tables due to its exceptional legibility and neutral tone.

- **Scale:** A tight modular scale is used to maintain high data density without sacrificing readability.
- **Hierarchy:** Use font weight (Semi-bold/600) rather than color alone to distinguish between primary and secondary information.
- **Labels:** Small labels (11px-12px) should always be in Inter with slightly increased letter spacing for clarity in badges and metadata.

## Layout & Spacing

The design system follows a strict **8px spacing grid**. All margins, paddings, and component heights should be multiples of 8px (or 4px for fine-grained internal component spacing).

- **Grid System:** A 12-column fluid grid is used for the main content area.
- **Desktop (1280px+):** 24px gutters, 32px side margins.
- **Tablet (768px - 1279px):** 16px gutters, 24px side margins. Content reflows to 1 or 2 columns depending on component complexity.
- **Mobile (<767px):** 16px side margins. Navigation collapses into a bottom bar or a simplified hamburger menu.
- **Density:** Components use "Compact-Comfortable" density. Lists and tables should maintain a row height of 40px to 48px to allow for touch targets while maximizing information display.

## Elevation & Depth

This design system avoids heavy shadows, opting instead for **Tonal Layers and Low-Contrast Outlines** to define hierarchy.

- **Level 0 (Background):** #F7F8FA. The canvas.
- **Level 1 (Panels/Cards):** #FFFFFF. Fixed borders (1px, Slate 200). Use a very soft ambient shadow for subtle lift: `0px 1px 3px rgba(0, 0, 0, 0.05)`.
- **Level 2 (Dropdowns/Modals):** #FFFFFF. More pronounced shadow to indicate focus: `0px 10px 15px -3px rgba(0, 0, 0, 0.1)`.
- **Navigation:** The deep navy sidebar is treated as a high-contrast anchor, requiring no shadow as the color value provides sufficient depth against the light background.

## Shapes

The shape language is **Structured and Friendly**. A standard 10px-12px radius is used for all primary containers and cards.

- **Buttons & Inputs:** 8px radius (Soft) to maintain a professional, clickable appearance.
- **Cards & Panels:** 12px radius (Rounded) to soften the large layout structures.
- **Badges/Chips:** Full pill-shaped radius (3rem) to distinguish them clearly from interactive buttons.
- **Focus States:** 2px solid Cobalt Blue offset by 2px white space for high-visibility accessibility.

## Components

### Buttons
- **Primary:** Cobalt Blue background, White text. High-contrast hover (darker blue).
- **Secondary:** White background, Slate 200 border, Slate 900 text.
- **AI Action:** Violet background with a subtle "sparkle" line icon prefix.

### Status Badges (Project Health)
Small, pill-shaped, using a light tinted background (10% opacity) with a 100% opacity text color:
- **On track:** Emerald.
- **At risk:** Amber.
- **Delayed:** Red.
- **Insufficient data:** Slate.

### Plan Lifecycle Badges
Use outlined styles with Semi-bold text to differentiate from Health badges:
- **Idea/Draft:** Slate outline.
- **Under Review:** Violet outline (AI involvement).
- **Approved/Active:** Cobalt outline.

### Cards
- **Milestone Cards:** Include a vertical progress line on the left. High contrast title, subtext for "Days Remaining."
- **Recommendation Cards:** Distinctive Violet border (left-side) or top-accent. Include an "Accuracy Score" chip in the top right.
- **Task Cards:** Clean, checkbox-aligned left. Metadata (Due date, Owner) aligned to bottom-right in `label-sm`.

### Input Fields
- Height: 40px.
- Border: 1px Slate 200.
- Active state: 1px Cobalt Blue border with a 3px soft blue glow.
- Labels: Always positioned above the field in `label-md`.

### Evidence Chips
Small, grey-scale chips (Slate 100 background) used to link to data sources or "Proof" within AI recommendations. They should include a "link" or "document" icon.