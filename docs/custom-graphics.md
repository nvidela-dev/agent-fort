# Included and custom graphics

The default tilesheets are included in this repository and in release source downloads:

- `public/dwarves.png`: the supplied 16×16 character sheet. The renderer uses the first six characters from the first row, scales them with nearest-neighbor sampling, and animates the bottom three pixel rows while walking.
- `public/geology.png`: the supplied Vettlingr geology reference. Terrain regions are sampled as 32×32 cells using the coordinates in `texture()` calls in `public/app.js`.

To use another sheet, replace the PNGs and adjust those source coordinates to match your atlas, then update the app. This is not a generic Dwarf Fortress graphics-pack importer. The original procedural dwarf/terrain renderer is used if a PNG is unavailable.

The bundled PNGs are third-party assets and are excluded from the project's MIT license. See [attribution](../public/ASSETS.md). The MIT license applies to Agent Fort's code and original fallback artwork, not to the bundled PNGs.
