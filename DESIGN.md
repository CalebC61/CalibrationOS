---
name: CalibrationOS
description: A mobile ADAS calibration crew's desk and public site. Gunsteel, safety orange, stencil lettering.
colors:
  gunsteel: "#2A2E37"
  gunsteel-deep: "#22262E"
  surface: "#343843"
  elevated: "#3E424F"
  input: "#404653"
  orange: "#FF5F1F"
  orange-ink: "#FF7E1E"
  orange-on-tint: "#FFD0B8"
  ink-on-orange: "#0A0A0A"
  text: "#F5F5F5"
  text-muted: "#B4B8C2"
  text-subtle: "#B1B6C0"
  status-route: "#C9D7EE"
  status-route-bg: "#243044"
  status-pass: "#D5E4C8"
  status-pass-bg: "#243028"
  status-hold: "#FFD0B8"
  status-hold-bg: "#3A2A22"
  status-brake: "#F3C7C0"
  status-brake-bg: "#3A2826"
  status-chalk: "#D5D8E0"
  status-chalk-bg: "#3A3E48"
typography:
  display:
    fontFamily: "Saira Stencil One, sans-serif"
    fontSize: "clamp(2.6rem, 4.6vw, 4.25rem)"
    fontWeight: 400
    lineHeight: 1.12
    letterSpacing: "0.02em"
  body:
    fontFamily: "DM Sans, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "0em"
  figure:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "1.35rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.03em"
rounded:
  stamp: "2px"
  control: "4px"
  panel: "6px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "48px"
components:
  button-primary:
    backgroundColor: "{colors.orange}"
    textColor: "{colors.ink-on-orange}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  status-stamp:
    backgroundColor: "{colors.status-pass-bg}"
    textColor: "{colors.status-pass}"
    rounded: "{rounded.stamp}"
    padding: "2px 7px"
---

## Overview

**Creative North Star: "The target and the work order."**

CalibrationOS is the desk and the public front of a two-person ADAS crew in Gilbert. The visitor is a shop owner or a technician in a bay, under fluorescent light, with a van outside. The page should feel like the board they set up for a camera and the sheet they write the job on.

Gunsteel is the ground. Orange is the safety vest and the only fill for a primary action. Headlines are the same stencil as the wordmark. Reading text is DM Sans. Clocks and money are mono. Status is five shop colors, not a UI kit.

This pass applies that world to the public home page, the owner Today board, and the shared header. Other screens still use the older card radius until a later pass.

**Key Characteristics:**
- One display face, Saira Stencil One, including the CALIBRATION OS mark
- Gunsteel surfaces with orange used as a fill, not as small gray-adjacent text
- Ruled sheets (a rate line, a job row) instead of repeated admin cards
- Status stamps with a light ink on a deep chip

## Colors

The ground is `#2A2E37`. Raised panels are `#343843`. The header rail is `#22262E`, one step darker, so the bar reads as a separate piece of steel.

Orange `#FF5F1F` is the button fill, the OS block, the focus ring, and the rule at the top of a sheet. Near-black `#0A0A0A` sits on that fill. Orange as small text on gunsteel uses `#FF7E1E` (`--accent-ink`). Text on an orange-tinted chip uses `#FFD0B8`.

**The Shop Status Rule.** Status never uses Tailwind blue, emerald, amber, or red. Five roles:
- Route (driving, east): `#C9D7EE` on `#243044`
- Pass (complete, paid): `#D5E4C8` on `#243028`
- Hold (on site, draft, mail held): `#FFD0B8` on `#3A2A22`
- Brake (cancelled, failed, at risk): `#F3C7C0` on `#3A2826`
- Chalk (booked, pending): `#D5D8E0` on `#3A3E48`

Muted text is `#B4B8C2`. Subtle text and placeholders are `#B1B6C0`, which clears 4.5:1 on the input fill.

## Typography

**The One Voice Rule.** Saira Stencil One is the only display face. Oswald is not loaded. DM Sans is the only text face. JetBrains Mono is for times, prices, and counts, not for labels.

Display headlines are uppercase, line-height 1.12, so the stencil cuts do not collide. The Today date is stencil. The clock on a job card is mono.

Body copy stays in sentence case. Do not put a small-caps label above a heading.

## Layout

Home opens with the headline and a calibration target in the same viewport. The target is drawn, not a screenshot of the product. Below that, each section is a ruled sheet: an orange 3px rule, then rows separated by hairlines. The steps, the price list, and the reasons to call share that sheet. The quotes are a single column. The close is a left-aligned band under another orange rule.

Today puts the date and the day controls on the left and one totals strip on the right. Jobs stack under the technician's name. The map stays under the list.

Public pages other than Home still use their previous card grids. They inherit the stencil headlines and the status colors.

## Elevation & Depth

Depth is a soft shadow offset downward, the way a clipboard sits on a bench: `0 10px 22px rgba(0, 0, 0, 0.28)`. Popovers use `0 18px 36px rgba(0, 0, 0, 0.36)`. No colored halo. An at-risk job is a brake-colored border, not a glow. The header is a solid rail, not a blurred glass bar.

## Shapes

Controls (buttons, inputs, the menu button) use 4px corners. Status stamps use 2px. Sheets are square at the corner and ruled at the top. The OS block in the wordmark stays at 2px.

## Components

Primary button: orange fill, near-black type, 4px radius. Ghost button: transparent, 1px steel border. Focus is a 2px orange outline.

The owner bar and the public header are sticky steel rails. The current item has a 2px orange underline. There is no pill behind the nav item.

A status stamp is 12px type, 2px radius, light ink, deep chip. It is not a fully rounded pill and not all-caps tracking.

The Home target is an inline SVG: a black and white checker, corner registration marks, and an orange center ring. It is an illustration of the tool, with a caption that says so.

## Do's and Don'ts

- Do keep gunsteel, `#FF5F1F`, and the stencil wordmark.
- Do draw status from the five shop colors.
- Do use mono for a time, a price, or a count.
- Do let a heading carry itself, without a kicker above it.
- Don't load Oswald or a second display family.
- Don't draw a fake product window, fake logos, or invented stats.
- Don't use a Tailwind blue, green, amber, or red for status.
- Don't put a colored glow on a card.
