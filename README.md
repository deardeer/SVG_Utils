# SVG Path Player — Vectorization Comparison Viewer

A small local tool for visually comparing SVG vectorization results (e.g. **LayerVec** vs **VISTA**) against the original raster image. It plays back each SVG path in drawing order so you can see how a vectorization method builds up an image, step by step, side by side with another method.

![status](https://img.shields.io/badge/status-local%20tool-blue)

## Features

- Side-by-side view: original image + two SVG renderings
- Path-by-path animated playback with adjustable speed (0.5×, 1×, 2×, Max)
- Combined progress slider to scrub through the drawing order
- Toggle overlay of anchor points and control (Bézier) points
- Per-panel zoom in / out / reset
- Image picker populated automatically from your dataset folder

## Project layout

```
SVG_Utils/
├── app.py                  # Flask backend: lists images & serves dataset files
├── svg_path_player.html    # Frontend viewer — open this in your browser
├── requirements.txt
└── data/                    # Your dataset (not included in this repo)
    ├── animals100_median/   # Original images (.jpg / .jpeg / .png)
    ├── LayerVec/             # SVG results from method A
    ├── VISTA/                # SVG results from method B
    └── VISTA_clean/          # SVG results from method A (cleaned variant)
```

`data/` is **not** part of this repository — it's your own dataset. The backend expects each SVG to share the same base filename as its source image (just a different extension), e.g. `cat.jpg` ↔ `cat.svg`.

## Setup

### 1. Clone the repo

```bash
git clone <your-repo-url>
cd SVG_Utils
```

### 2. Install dependencies

Requires Python 3.8+.

```bash
pip install -r requirements.txt
```

### 3. Link your dataset

Create a `data` folder in the project root, or symlink an existing folder of yours:

```bash
ln -s /path/to/your/dataset ./data
```

It should contain the subfolders listed in [Project layout](#project-layout). At minimum you need:

- `data/animals100_median/` — the original images used to populate the image picker
- one or more folders of matching SVGs (e.g. `LayerVec/`, `VISTA/`, `VISTA_clean/`)

If your folder names differ, update the routes in `app.py` and the path constants in `svg_path_player.html` (see [Configuration](#configuration)).

### 4. Start the backend

```bash
python app.py
```

This starts a Flask server at `http://localhost:5002` which lists available images and serves files from `data/`.

### 5. Open the viewer

Open `svg_path_player.html` directly in your browser (double-click works — CORS is enabled for `file://` pages). With the Flask server running, the page will:

1. Fetch the list of images from `data/animals100_median/`
2. Let you pick one from the **Select Image** dropdown
3. Load the matching SVGs from the two comparison folders and display them alongside the original image

## Using the player

| Control | Description |
|---|---|
| **Select Image** | Choose an image; loads the original + both SVGs |
| **🔄 Refresh List** | Re-fetch the image list from the backend |
| **▶ Play / ⏸ Pause / ↺ Reset** | Animate the drawing order of both SVGs in sync |
| **Speed** (0.5× / 1× / 2× / Max) | Controls playback speed |
| **Progress slider** | Scrub to any path index manually |
| **🔵 Show/Hide Control Points** | Overlay anchor points (circles) and Bézier control points (squares) on each path |
| **🔍 Zoom In / Out / ⟲ Reset** (per panel) | Zoom each SVG panel independently |

## Configuration

- **Backend port / dataset folders**: edit the routes near the top of `app.py` (`get_image_list`, `serve_image`, `serve_layervec`, `serve_vista`, `serve_vista_clean`) to match your folder names, and change the port in the final `app.run(...)` call if `5002` is in use.
- **Frontend paths**: near the top of the `<script>` block in `svg_path_player.html`, update:
  ```js
  const FLASK_API_URL = 'http://localhost:5002';
  const IMAGES_PATH   = BASE_PATH + 'animals100_median/';
  const LAYERVEC_PATH = BASE_PATH + 'VISTA_clean/'; // left panel
  const VISTA_PATH    = BASE_PATH + 'VISTA/';       // right panel
  ```

## Notes

- The Flask server runs with `debug=True` and CORS enabled for all origins — intended for local use only, not for deployment.
- Supported image formats for the picker: `.jpg`, `.jpeg`, `.png`.
