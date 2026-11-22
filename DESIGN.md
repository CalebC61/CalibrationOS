# Desert Workshop — Style C preview

This file describes the visual world on this preview branch. It is not the
production brand. `CLAUDE.md` on `main` still specifies gunsteel and `#FF5F1F`.
Do not merge this branch as the live theme.

## Scene

A one-man mobile ADAS shop in Gilbert, working in Phoenix Valley sun. The
page should feel like a trusted trade counter: plaster, a stamp, a paper
job ticket. It should not feel like a software startup.

## Palette

| Role | Hex | Use |
|---|---|---|
| Sand | `#E8D7C0` | Page ground |
| Bone | `#F7F1E6` | Cards, inputs, text on rust and on night |
| Rust | `#A33E1E` | Buttons, the OS stamp, the header rule |
| Rust ink | `#8C3014` | Small accent text on sand or bone |
| Saguaro | `#132E24` | Body text and the active nav anchor |
| Desert night | `#1A2E28` | Public footer |
| Line | `#D4C2A6` | Card borders |

Bone on rust is about 5.7:1. Saguaro on bone is about 12.9:1. Saguaro on sand
is about 10.3:1. Muted text `#3C5348` stays above 5.9:1 on both grounds.

## Type

- Display: Zilla Slab, 600 and 700. Shop sign, board times, prices.
- Body: Atkinson Hyperlegible, 400 and 700. Field screens in sunlight.
- Data: JetBrains Mono only for job numbers and score counts.

## Shape and motion

Cards use an 8px radius and a warm offset shadow. Controls use 6px. Status
labels are stamps: uppercase slab, 2px radius, a border plus an inset rule.
Buttons scale to 0.98 on press over 140ms with `cubic-bezier(0.23, 1, 0.32, 1)`.
Hover lifts are limited to fine pointers. The home photograph is the one
entrance; reduced motion removes it. A fixed multiply grain suggests paper
and does not catch clicks.

## Photograph

`frontend/public/marketing/sonoran-day.jpg` is Saguaro National Park West,
Arizona. Photo by dconvertini, CC BY-SA 2.0, via Wikimedia Commons. The home
footer credits it. It is a stand-in for valley light, not a photo of the shop.
