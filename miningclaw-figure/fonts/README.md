# Vendored Fonts for Paper Renderer

This directory holds the `.ttf` font files required by the `nature_paper` profile
when rendering with `vl-convert`.

## Why vendored fonts?

`vl-convert` renders SVG/PDF/PNG via an embedded Vega/Vega-Lite JS engine
(Rust + Deno).  It cannot access system fonts automatically.  You must either:

1. **Vendor the .ttf files here** and register them at render time (recommended —
   fully reproducible across machines and CI), or
2. Rely on vl-convert's built-in font fallback (DejaVu Sans), which does not
   match the Nature paper aesthetic.

## Required fonts

| File | Purpose | Source |
|------|---------|--------|
| `Inter-Regular.ttf` | Primary body / axis label font | [rsms/inter](https://github.com/rsms/inter/releases) |
| `Inter-Bold.ttf` | Chart titles | same release |
| `LiberationSans-Regular.ttf` | Fallback for Inter (metrically compatible with Arial) | [liberation-fonts](https://github.com/liberationfonts/liberation-fonts/releases) |
| `LiberationSans-Bold.ttf` | Bold fallback | same release |

Drop the `.ttf` files into this directory (`$SK/fonts/`).
Do **not** commit binary font files to the main repository without explicit
approval — add `*.ttf` to `.gitignore` and distribute via a separate assets
package or CI artifact.

## Registering fonts with vl-convert

In your render script (or in `render_paper.render_paper`), register the font
directory before the first `vegalite_to_svg` call:

```python
import vl_convert as vlc
import pathlib

FONTS_DIR = pathlib.Path(__file__).parent / "fonts"

# Register all .ttf files in the fonts/ directory
for ttf in FONTS_DIR.glob("*.ttf"):
    vlc.register_font_directory(str(FONTS_DIR))
    break  # register_font_directory takes the directory, not individual files
```

Or, if vl-convert exposes a font-directory path option directly:

```python
vlc.vegalite_to_svg(spec_json, vl_version="v5.20", font_dir=str(FONTS_DIR))
```

Check the installed vl-convert version's API — the exact call signature varies
by release.

## Pinning versions for determinism (I10)

The paper render output (SVG/PDF/PNG) is deterministic only when both the
**vl-convert wheel version** and its **bundled Vega / Vega-Lite JS** are pinned.
Add the following to `requirements-paper.txt` (separate from core deps):

```
# Paper render path — pin for deterministic SVG/PDF/PNG output
vl-convert-python==1.7.0     # pin exact version; update via ADR
```

When upgrading vl-convert, regenerate golden SVG fixtures using
`normalize_svg()` (see `render_paper.py`) and commit the new baselines.

## Security note

Only drop `.ttf` files from trusted, verified sources (official project releases
with checksums).  Font files can contain embedded data; treat them as untrusted
binaries from the perspective of your supply-chain policy.

## Pure-compile tests do not need fonts

The `figure_spec_to_vegalite()` function is pure Python and produces a
Vega-Lite JSON dict.  All unit tests for the compile step (including the
`test_compiles_to_vegalite_with_sort_disabled` and `test_89mm_width_applied`
tests in `tests/test_render_paper.py`) run without any font files or vl-convert
installation.
