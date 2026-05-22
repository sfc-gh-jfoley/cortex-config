# Hi-Res Icon Extraction from Snowflake Brand Template

One-time workflow for extracting new icons not already in the `icons/` library.

## Source

The official Snowflake brand template Google Slides file: **"SNOWFLAKE TEMPLATE JANUARY 2026"**. Find via Snowflake Intelligence or Glean.

## Steps

### 1. Download as PPTX

In Google Slides: File > Download > Microsoft PowerPoint (.pptx)

### 2. Unzip and find icon slides

```bash
unzip -o deck.pptx -d deck_extracted/
# Icons are in slide XML files under ppt/slides/
```

### 3. Extract OOXML shapes → SVG

Use `render_hires_icons.py` (in `excalidraw-prototypes/`):

- Parses `custGeom` (FREEFORM) and `grpSp` (GROUP) shapes from slide XML
- Converts OOXML path data (moveTo, lnTo, cubicBezTo, close) → SVG `<path>` elements
- Handles `schemeClr` via theme lookup (accent1=#29B5E8, accent2=#11567F, etc.)
- Computes tight bounding box, applies group transforms
- Filters out text label shapes (#11567F navy background rectangles)

### 4. Convert SVG → hi-res PNG

Use `svg-to-png.mjs` (in `excalidraw-prototypes/`):

```bash
node svg-to-png.mjs icons-svg/*.svg
```

- Uses Puppeteer with `deviceScaleFactor=4` for 1024px output from 256px SVGs
- Batch converts all SVGs in the specified directory

## Output

Place resulting PNGs in the `icons/` directory. Use descriptive names matching the pattern: `snowflake-<feature>.png`, `ref-<object>.png`, `cat-<category>.png`.

## Tips

- Use 400-1024px source icons for crisp rendering at any export scale
- Prefer vector extraction (this workflow) over screenshot cropping
- Icons with transparent backgrounds embed cleanly in Excalidraw
