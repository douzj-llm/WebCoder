# WebCoder

Project page and promotional-film sources for

**WebCoder: Scaling General Frontend Development with Artifact-Grounded Agentic
Reinforcement Learning**
Zijun Dou\*, Zhen Yang\*, Xijun Liu, Dongzhuoran Zhou, Aohan Zeng, Jie Tang
*\*Core contributors.*

Project page: *(enable GitHub Pages — see below)*

## What is here

```
docs/            the project page. Served by GitHub Pages; no build step, no dependencies.
promo_video/     the 2-minute promotional film, generated from code rather than edited.
```

Both are standalone. Open `docs/index.html` in a browser and the page works; see
[promo_video/README.md](promo_video/README.md) to re-render the film.

## The project page

A single static page: `docs/index.html` plus `docs/static/`.

```
docs/index.html                       the whole page
docs/.nojekyll                        tell GitHub Pages to serve files as-is
docs/static/css/style.css             light + dark theme, layout, results table
docs/static/js/main.js                theme toggle, figure lightbox, BibTeX copy
docs/static/images/*.webp             figures, rendered from the manuscript sources
docs/static/pdf/webcoder_paper.pdf    the paper, downsampled to 1.9 MB for the web
docs/static/video/webcoder_promo_1080p.{mp4,webm}   the film, built from promo_video/
```

Preview it locally:

```bash
python3 -m http.server 8000 --directory docs
# then open http://127.0.0.1:8000/
```

### Deploying to GitHub Pages

In the repository, go to **Settings → Pages**, set *Source* to **Deploy from a
branch**, branch `main`, folder **`/docs`**, and save. The page appears at
`https://<owner>.github.io/WebCoder/` within a minute or two.

The `/docs` folder is the publishing root on purpose, so that `promo_video/` and
this README are not served as part of the site.

### Design notes

Colours, surfaces and ink roles come from a validated palette: the accent is
`#2a78d6` on light and `#3987e5` on dark, both checked for contrast and
colour-vision separation against their own surface. Dark mode follows the OS by
default and the toggle overrides it, remembered in `localStorage`.

In the results table, best and second best are never carried by colour alone:
best is bold *and* accent-coloured, second best is underlined.

### Regenerating the figures and the web PDF

The images are rendered from the paper's LaTeX sources. Point `PAPER` at your
checkout of the manuscript, then for one figure:

```bash
PAPER=/path/to/manuscript
pdftoppm -f 1 -l 1 -r 170 -png -singlefile "$PAPER/figs/<name>.pdf" /tmp/<name>
cwebp -q 88 -metadata none /tmp/<name>.png -o docs/static/images/<name>.webp
```

and to refresh the web copy of the paper after recompiling it:

```bash
gs -sDEVICE=pdfwrite -dPDFSETTINGS=/ebook -dColorImageResolution=144 \
   -dGrayImageResolution=144 -dDetectDuplicateImages=true \
   -dNOPAUSE -dQUIET -dBATCH \
   -sOutputFile=docs/static/pdf/webcoder_paper.pdf "$PAPER/arxiv_preprint.pdf"
```

## Still to fill in

Three placeholders in `docs/index.html`, each marked with a `TODO` comment:

1. **Link buttons.** Code, Model and Webdev-Bench carry `class="btn pending"`
   and `href="#"`. Replace the `href`, then delete ` pending` from the class so
   the button renders as active.
2. **BibTeX.** The `journal` field reads `arXiv preprint arXiv:XXXX.XXXXX`.
3. **Social preview.** `og:url` is unset and `og:image` points at a relative
   path; both want the live absolute URL for link previews to render.

## Credits

* Soundtrack: "Inspired" by Kevin MacLeod ([incompetech.com](https://incompetech.com)),
  licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
* Typeface in the film: [Inter](https://rsms.me/inter/) by Rasmus Andersson,
  SIL Open Font License 1.1.
* Everything else is released under the [MIT License](LICENSE).

## Citation

```bibtex
@article{dou2026webcoder,
  title   = {WebCoder: Scaling General Frontend Development with Artifact-Grounded Agentic Reinforcement Learning},
  author  = {Dou, Zijun and Yang, Zhen and Liu, Xijun and Zhou, Dongzhuoran and Zeng, Aohan and Tang, Jie},
  journal = {arXiv preprint arXiv:XXXX.XXXXX},
  year    = {2026}
}
```
