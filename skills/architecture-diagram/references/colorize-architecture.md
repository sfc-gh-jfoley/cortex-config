# Colorize Script Template

Full template for the Excalidraw post-processing colorize script. Copy and customize the `SUBGRAPH_COLORS`, `NODE_COLORS`, and optional alignment phases for each new diagram.

## Minimal Template

```javascript
#!/usr/bin/env node
import fs from "fs";
import path from "path";
import crypto from "crypto";
import puppeteer from "puppeteer";

const inputFile = process.argv[2] || "<name>-mermaid.excalidraw";
const outputFile = process.argv[3] || inputFile.replace(/\.excalidraw$/, "-color.excalidraw");
const ICONS_DIR = path.resolve(import.meta.dirname, "../icons");

const scene = JSON.parse(fs.readFileSync(inputFile, "utf-8"));
if (!scene.files) scene.files = {};

// --- COLORS (customize per diagram) ---
const SF_BLUE = "#29B5E8";
const SF_DARK = "#11567F";
const TEAL = "#148C8C";
const PURPLE = "#7048e8";
const GREEN = "#2f9e44";
const ORANGE = "#e8590c";
const RED = "#e03131";

const LIGHT_BLUE = "#d0ebff";
const LIGHT_TEAL = "#c3fae8";
const LIGHT_PURPLE = "#e5dbff";
const LIGHT_GREEN = "#d3f9d8";
const LIGHT_ORANGE = "#fff4e6";
const LIGHT_RED = "#ffe3e3";
const LIGHT_GRAY = "#f1f3f5";
const SNOW_BG = "#e7f5ff";

// --- CONSTANTS ---
const ICON_SIZE = 84;
const ICON_PAD_TOP = 10;
const ICON_GAP_BELOW = 6;
const NODE_PAD_H = 20;
const NODE_PAD_V = 12;
const WIDTH_SAFETY = 1.25;
const SUBGRAPH_PAD = 40;
const SUBGRAPH_TITLE_H = 40;

// --- CUSTOMIZE THESE ---
const SUBGRAPH_COLORS = [
  // { match: (l) => labelContains(l, "keyword"), bg: LIGHT_BLUE, stroke: SF_BLUE },
];

const NODE_COLORS = [
  // { match: (l) => labelContains(l, "keyword"), bg: "#ffffff", stroke: SF_BLUE, icon: "icon.png" },
  // icon: null for nodes without icons
];
```

## Core Utility Functions

These are required in every colorize script:

```javascript
function elById(id) {
  return scene.elements.find(e => e.id === id);
}

function getLabel(rect) {
  const bound = rect.boundElements?.filter(b => b.type === "text") || [];
  if (!bound.length) return "";
  return elById(bound[0].id)?.text || "";
}

function getBoundText(rect) {
  const bound = rect.boundElements?.filter(b => b.type === "text") || [];
  if (!bound.length) return null;
  return elById(bound[0].id);
}

function labelContains(label, ...terms) {
  const norm = s => s.toLowerCase().replace(/\\n/g, "").replace(/\n/g, "").replace(/\s+/g, "");
  const l = norm(label);
  return terms.some(t => l.includes(norm(t)));
}

function embedIcon(iconFilename) {
  if (!iconFilename) return null;
  if (fileIdCache[iconFilename]) return fileIdCache[iconFilename];
  const iconPath = path.join(ICONS_DIR, iconFilename);
  if (!fs.existsSync(iconPath)) { console.warn(`Icon not found: ${iconPath}`); return null; }
  const buf = fs.readFileSync(iconPath);
  const dataUrl = `data:image/png;base64,${buf.toString("base64")}`;
  const fileId = crypto.randomUUID();
  scene.files[fileId] = { mimeType: "image/png", id: fileId, dataURL: dataUrl, created: Date.now(), lastRetrieved: Date.now() };
  fileIdCache[iconFilename] = fileId;
  return fileId;
}

function makeId() { return crypto.randomBytes(10).toString("base64url"); }
```

## Text Measurement Function

Uses Puppeteer with Helvetica (system font, no CDN needed):

```javascript
async function measureTexts(texts) {
  const browser = await puppeteer.launch({ headless: true });
  const page = await browser.newPage();
  const html = `<!DOCTYPE html><html><head>
    <style>
      @font-face {
        font-family: 'Helvetica';
        src: local('Helvetica Neue'), local('Helvetica'), local('Arial');
        font-weight: normal; font-style: normal;
      }
      body { font-family: 'Helvetica', 'Arial', sans-serif; }
      .probe { font-family: 'Helvetica', 'Arial', sans-serif; font-size: 16px; position: absolute; visibility: hidden; }
    </style>
  </head><body>
    <span class="probe">Mmm</span>
    <canvas id="c" width="4000" height="2000"></canvas>
    <script>
      window.__measureTexts = function(items) {
        const canvas = document.getElementById('c');
        const ctx = canvas.getContext('2d');
        return items.map(({text, fontSize}) => {
          ctx.font = fontSize + 'px Helvetica, Arial, sans-serif';
          const lines = text.split('\\n');
          const lineHeight = fontSize * 1.25;
          let maxW = 0;
          for (const line of lines) {
            const m = ctx.measureText(line);
            if (m.width > maxW) maxW = m.width;
          }
          return { width: Math.ceil(maxW), height: Math.ceil(lines.length * lineHeight), lines: lines.length };
        });
      };
      document.fonts.ready.then(() => { window.__ready = true; });
    </script>
  </body></html>`;
  await page.setContent(html, { waitUntil: "networkidle0", timeout: 30000 });
  await page.waitForFunction("window.__ready === true", { timeout: 15000 });
  const results = await page.evaluate((items) => window.__measureTexts(items), texts);
  await browser.close();
  return results;
}
```

## Shift/Movement Functions

```javascript
function getAllDescendants(sgId) {
  const desc = new Set();
  const directKids = parentChildren.get(sgId) || [];
  for (const child of directKids) {
    desc.add(child.id);
    if (subgraphIds.has(child.id)) {
      for (const d of getAllDescendants(child.id)) desc.add(d);
    }
  }
  return desc;
}

function shiftSubtree(sgId, dx, dy) {
  const sg = elById(sgId);
  if (!sg) return;
  sg.x += dx; sg.y += dy;
  const txt = getBoundText(sg);
  if (txt) { txt.x += dx; txt.y += dy; }
  for (const cid of getAllDescendants(sgId)) {
    const cel = elById(cid);
    if (cel) { cel.x += dx; cel.y += dy; }
    const ctxt = getBoundText(cel);
    if (ctxt) { ctxt.x += dx; ctxt.y += dy; }
  }
}

function shiftNode(node, dx, dy) {
  node.x += dx; node.y += dy;
  const txt = getBoundText(node);
  if (txt) { txt.x += dx; txt.y += dy; }
}

function shiftElement(el, dx, dy) {
  if (subgraphIds.has(el.id)) shiftSubtree(el.id, dx, dy);
  else shiftNode(el, dx, dy);
}
```

## boxEdgePoint (Arrow Routing)

```javascript
function boxEdgePoint(rect, toX, toY) {
  const cx = rect.x + rect.width / 2;
  const cy = rect.y + rect.height / 2;
  const hw = rect.width / 2;
  const hh = rect.height / 2;
  const dx = toX - cx;
  const dy = toY - cy;
  if (dx === 0 && dy === 0) return { x: cx, y: cy + hh };
  const absDx = Math.abs(dx);
  const absDy = Math.abs(dy);
  let t;
  if (absDx * hh > absDy * hw) t = hw / absDx;
  else t = hh / absDy;
  return { x: cx + dx * t, y: cy + dy * t };
}
```

## rewrapSubgraph (Title-Width-Aware)

For complex diagrams with title wrapping, use this version that preserves minimum widths:

```javascript
const sgMinWidth = new Map();

function rewrapSubgraph(sg) {
  const children = parentChildren.get(sg.id) || [];
  if (!children.length) return;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const child of children) {
    minX = Math.min(minX, child.x);
    maxX = Math.max(maxX, child.x + child.width);
    minY = Math.min(minY, child.y);
    maxY = Math.max(maxY, child.y + child.height);
  }
  if (minX === Infinity) return;

  const titleH = sgMinWidth.has(sg.id)
    ? Math.max(SUBGRAPH_TITLE_H, sgMinWidth.get(sg.id).titleH || SUBGRAPH_TITLE_H)
    : SUBGRAPH_TITLE_H;
  const childrenW = (maxX - minX) + SUBGRAPH_PAD * 2;
  const minW = sgMinWidth.get(sg.id)?.width || 0;
  const finalW = Math.max(childrenW, minW);

  sg.x = minX - SUBGRAPH_PAD;
  sg.y = minY - SUBGRAPH_PAD - titleH;
  sg.width = finalW;
  sg.height = (maxY - minY) + SUBGRAPH_PAD * 2 + titleH;
  if (finalW > childrenW) sg.x -= (finalW - childrenW) / 2;

  const txt = getBoundText(sg);
  if (txt) {
    txt.x = sg.x + SUBGRAPH_PAD;
    txt.y = sg.y + 8;
    txt.width = sg.width - SUBGRAPH_PAD * 2;
    txt.height = titleH - 8;
    txt.textAlign = "left";
    txt.verticalAlign = "top";
  }
}
```

Populate `sgMinWidth` after Phase 2.75 title wrapping:
```javascript
for (const { sg, txt } of sgTitleEls) {
  const titleLines = (txt.text || "").split("\n").length;
  if (titleLines > 1) {
    const fontSize = txt.fontSize || 16;
    const lineHeight = fontSize * 1.25;
    const titleH = titleLines * lineHeight + 12;
    sgMinWidth.set(sg.id, { width: sg.width, titleH });
  } else {
    sgMinWidth.set(sg.id, { width: sg.width, titleH: SUBGRAPH_TITLE_H });
  }
}
```

## Phase 2.76: Root-Level Gap Enforcement

Must run AFTER title wrapping:

```javascript
const ROOT_H_GAP = 100;
const rootByX = [...rootSubgraphs].sort((a, b) => a.x - b.x);
for (let pass = 0; pass < 3; pass++) {
  rootByX.sort((a, b) => a.x - b.x);
  for (let i = 0; i < rootByX.length - 1; i++) {
    const left = rootByX[i];
    const right = rootByX[i + 1];
    const leftRight = left.x + left.width;
    const gap = right.x - leftRight;
    if (gap < ROOT_H_GAP) {
      const push = ROOT_H_GAP - gap;
      shiftElement(right, push, 0);
      for (let k = i + 2; k < rootByX.length; k++) shiftElement(rootByX[k], push, 0);
    }
  }
  for (const sg of subgraphList) rewrapSubgraph(sg);
}
```

## Excalidraw Image Element Template

For creating icon image elements in Phase 2.7:

```javascript
{
  id: makeId(),
  type: "image",
  x: rect.x + (rect.width / 2) - (ICON_SIZE / 2),
  y: rect.y + ICON_PAD_TOP,
  width: ICON_SIZE,
  height: ICON_SIZE,
  angle: 0,
  strokeColor: "transparent",
  backgroundColor: "transparent",
  fillStyle: "solid",
  strokeWidth: 0,
  strokeStyle: "solid",
  roughness: 0,
  opacity: 100,
  groupIds: rect.groupIds || [],
  frameId: rect.frameId || null,
  index: rect.index,
  roundness: null,
  seed: Math.floor(Math.random() * 2e9),
  version: 1,
  versionNonce: Math.floor(Math.random() * 2e9),
  isDeleted: false,
  boundElements: null,
  updated: Date.now(),
  link: null,
  locked: false,
  status: "saved",
  fileId,
  scale: [1, 1],
  crop: null,
}
```

## Post-Phase 4: Font & Roughness Override (Google Slides Fix)

Add this AFTER Phase 4 and BEFORE `fs.writeFileSync`. This ensures all text uses clean sans-serif font (not Excalidraw's hand-drawn Virgil) and removes the hand-drawn wobble from shapes:

```javascript
scene.appState.viewBackgroundColor = "#ffffff";

for (const el of scene.elements) {
  if (el.type === "text") {
    el.fontFamily = 3;
  }
}

for (const el of scene.elements) {
  if (el.type === "rectangle" || el.type === "arrow" || el.type === "line") {
    el.roughness = 0;
  }
}

fs.writeFileSync(outputFile, JSON.stringify(scene, null, 2));
```

**Why this matters:** Excalidraw's default font is Virgil (fontFamily=5), a hand-drawn style. When wide diagrams (~4:1 aspect ratio) are scaled down to fit a 16:9 Google Slide, the hand-drawn strokes become blurry and illegible. Helvetica (fontFamily=3) renders crisply at any scale. Setting roughness=0 removes the hand-drawn wobble from rectangle and arrow strokes.

**Excalidraw fontFamily values:**
| Value | Font | Use |
|-------|------|-----|
| 1 | Hand-drawn (legacy) | Avoid |
| 2 | Normal | Rarely used |
| 3 | Helvetica/sans-serif | Recommended for presentations |
| 5 | Virgil (hand-drawn) | Default from Mermaid conversion — avoid for Slides |
