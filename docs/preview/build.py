"""Build the UI preview.

template.html  — the page (our code: CSS, markup, Three.js scene, scripted negotiation)
land.b64       — 11,795 Fibonacci-lattice land points (lon/lat × 100, int16) precomputed
                 against the Natural Earth 110m land mask, so the page needs no network
                 for geometry
index.html     — standalone page: open it directly in a browser
orbit-preview.html — the same page without the <html>/<head> skeleton, for hosts that wrap it
"""
import pathlib

here = pathlib.Path(__file__).parent
page = (here / "template.html").read_text().replace("__LAND__", (here / "land.b64").read_text().strip())

(here / "orbit-preview.html").write_text(page)
(here / "index.html").write_text(
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n</head>\n<body>\n'
    + page + "\n</body>\n</html>\n"
)
print("built index.html and orbit-preview.html")
