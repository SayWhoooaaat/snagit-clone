# Annotator

A lightweight, Snagit-style **image annotation editor** for Linux. It does not
capture the screen — it edits images you bring in via **clipboard, file open, or
drag-and-drop**.

## Why this stack

Built on **Python + PySide6 (Qt 6)** using Qt's `QGraphicsView` scene-graph. Qt
Widgets is a decades-stable, long-term-supported API, and PySide6 is the official
Qt-for-Python binding. The scene graph provides object layering, z-order,
selection, transforms and a growable canvas out of the box, so the whole app is a
handful of small modules with no build step and no dependency treadmill.

## Run

```bash
./run.sh                # creates .venv on first run, then launches
# or, once the venv exists:
.venv/bin/python -m annotator
```

Install as a command instead:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
annotator
```

## Documents

You edit a **document** — a white page (default **200×200**) holding any number
of images and annotations with their z-order and transforms. **New** (`Ctrl+N`)
starts a fresh page; the page auto-grows to fit whatever you add.

Documents are saved in `~/.local/share/Annotator/library/` as `.snagdoc` files
(JSON: page size + every item, with images embedded as base64 PNG) plus a `.png`
thumbnail. The current document **auto-saves** as you work, so the filmstrip and
Library always show your recent *documents*, not raw clipboard frames. Click any
thumbnail to reopen that document fully editable.

## Features

**Canvas**
- Paste images (`Ctrl+V`), **Open** files, or drag-and-drop — each image is its
  own object on its own layer, added to the current document.
- Full z-order: **Front / Forward / Backward / Back**.
- Every object shows resize handles: **proportional corner resize** (hold
  `Shift` for free resize), a **rotate** handle, and **Flip H / Flip V**.
- The canvas **auto-expands** whenever an object is placed or dragged past its
  current bounds — nothing is ever clipped.
- **Resize the page**: drag any of the four dark corner grips. While you drag,
  a **dashed outline previews** the new size — the canvas, zoom and scroll stay
  completely still — and the new size is applied in one step when you release
  (then re-fit and centered). Shrinking below your content just crops it on
  export; the cropped part stays visible in the grey surround, so nothing is
  lost. Handy for reclaiming space after the page auto-grew.
- **Auto zoom-out**: when the page grows beyond the viewport the view zooms out
  so the whole page stays visible. Scrollbars only appear when you've zoomed in
  past the fit level.
- **Always centered**: after any auto-fit or canvas resize, the page is centered
  in the viewport.
- **Zoom controls** in the status bar: `Fit`, `−`, an editable percentage field
  (type a number and press Enter), and `+`. Also `Ctrl+0` (Fit),
  `Ctrl+=` / `Ctrl+-` (in/out), and `Ctrl`+mouse-wheel.

**Annotation tools**
- **Rectangle** and **Ellipse** (stroke + optional fill), **Line** and
  **Arrow** (endpoints on start, end or both; triangle / line (a
  perpendicular crossbar) / circle shapes, all scaling with the stroke
  width), **Text**, and **Callout** bubbles with a draggable pointer/tail
  (double-click to edit text inline).
- Line and Arrow create the same object with identical options — give a line
  arrowheads and it is effectively an arrow — but each item permanently
  remembers which of the two tools made it.
- The **Style panel** (right dock) is contextual: it shows only the settings
  that apply to the active tool or the current selection (fill for shapes,
  endpoints for lines/arrows, font for text, opacity for everything, images
  included). Every tool remembers its own style, and editing a selected item
  updates only its own tool's memory, so the next item you draw looks like
  the one you just tweaked and the presets never contaminate each other —
  give a line circle endpoints and every new line keeps them, while arrows
  stay exactly as you left them.
- **Undo / redo** for every document edit — drawing, moving, resizing,
  styling, deleting, page resizes (`Ctrl+Z`, `Ctrl+Shift+Z` / `Ctrl+Y`).

**Library / recents**
- A horizontal **filmstrip** of recent *documents* along the bottom.
- A **Library** button (`Ctrl+G`) opens a gallery of every saved document.
- Click a thumbnail to reopen that document.

**Output**
- **Export…** the flattened page to PNG (`Ctrl+E`), **Save to Library**
  (`Ctrl+S`, forces an immediate document save), or **Copy** the flattened page
  to the clipboard (`Ctrl+Shift+C`).

## Keyboard shortcuts

| Action | Key | Action | Key |
|---|---|---|---|
| New document | `Ctrl+N` | Bring to Front | `Ctrl+Shift+]` |
| Select | `V` | Forward | `Ctrl+]` |
| Rectangle | `R` | Backward | `Ctrl+[` |
| Ellipse | `O` | Send to Back | `Ctrl+Shift+[` |
| Line | `L` | Delete | `Delete` |
| Arrow | `A` | Paste | `Ctrl+V` |
| Text | `T` | Open | `Ctrl+O` |
| Callout | `C` | Library | `Ctrl+G` |
| Export | `Ctrl+E` | Save to Library | `Ctrl+S` |
| Undo | `Ctrl+Z` | Redo | `Ctrl+Shift+Z` / `Ctrl+Y` |

## Layout

```
annotator/
  model.py       Style dataclass + pen/brush helpers
  handles.py     resize / rotate / tail handle items
  items.py       image + annotation graphics objects (one transform model)
  canvas.py      QGraphicsView/Scene: import, auto-expand, tools, z-order, export
  properties.py  contextual style panel (one remembered style per tool)
  history.py     snapshot-based undo/redo over the document serialization
  library.py     on-disk storage, filmstrip, gallery
  mainwindow.py  toolbars, actions, wiring
  __main__.py    entry point (python -m annotator)
```
