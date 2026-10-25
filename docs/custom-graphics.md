# Custom graphics

A fresh checkout works with Agent Fort's original procedural graphics. Your own custom PNGs override them automatically:

- `public/dwarves.png`: a character sheet with 16×16 cells. The current renderer uses the first six characters from the first row, scales them with nearest-neighbor sampling, and animates the bottom three pixel rows while walking.
- `public/geology.png`: optional 32×32 terrain tiles in the reference-image layout used by this project. The renderer's `texture()` calls specify source coordinates; change those coordinates for another atlas. This is not a generic drop-in Dwarf Fortress graphics-pack importer.

Copy your files into those paths, then tap **Update**. Both files are ignored by Git. Missing sheets use the original built-in fallback rather than preventing the app or PWA cache from loading.

The initial local installation used images supplied by its owner, including a Vettlingr geology reference. Those files are intentionally not part of the public distribution. Obtain assets from their authors and follow the applicable terms; the MIT license does not grant rights to optional third-party images.
