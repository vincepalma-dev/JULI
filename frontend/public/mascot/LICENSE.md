# Juli mascot art: licence

The Juli mascot art in this repository is original work, drawn as vector
shapes for JULI. It is released under the same MIT License as the rest of the
repository (see `LICENSE` at the repository root).

Copyright (c) 2026 vincepalma-dev

It covers:

- `frontend/src/components/JuliFigure.vue`, `JuliOutfit.vue` and
  `JuliMascot.vue`: Juli as an SVG drawing that CSS animates, with a pose for
  every state, her outfits and accessories, and her idle styles
- `frontend/public/mascot/stills/juli-<state>.png`: one 256×256 px still per
  state; `juli-idle.png` is the page icon
- `frontend/public/mascot/sprites/juli-<state>-16f.webp`: the earlier 16-frame
  sprite strips, no longer shown
- `frontend/art/mascot/juli-<state>.svg`: the earlier layered vector sources

States: idle, waiting, done, stopped, error, planner, coder, coder-thinking,
coder-typing, reviewer, tester, docs, devops, security, analyst, discussion
and follow-up. The outfits, accessories and idle styles are listed in
`frontend/src/mascot.js`.
