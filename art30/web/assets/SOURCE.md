# Bundled asset

`manrope-latin.woff2` — Manrope, variable weight 400–800, the `latin` subset Google Fonts
serves for Manrope v20.

- Upstream project: Manrope by Mikhail Sharanda, <https://github.com/sharanda/manrope>
- Fetched 2026-08-30 from the URL in the `@font-face` block of
  `https://fonts.googleapis.com/css2?family=Manrope:wght@400..800&display=swap`
- Licence: SIL Open Font License 1.1, `OFL.txt` beside this file. Redistribution as part of a
  larger work is permitted; the licence and copyright notice travel with the file.
- sha256: see below.

The page never requests it over the network. `art30/web/inline_assets.py` writes it into
`art30/web/index.html` as a `data:` URI between the `font:begin` and `font:end` markers, and
`--check` fails a test when the two disagree.

`e310b55a7fd9677f5e3555e6c6c4d064fa1f1d24393f0ddbe217cea12a8c432f`  manrope-latin.woff2
