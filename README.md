# WebCoder

Project page and promotional-film sources for

**WebCoder: Scaling General Frontend Development with Artifact-Grounded Agentic
Reinforcement Learning**
Zijun Dou\*, Zhen Yang\*, Xijun Liu, Dongzhuoran Zhou, Aohan Zeng, Jie Tang
*\*Core contributors.*

Project page: <https://douzj-llm.github.io/WebCoder/>
Paper: [arXiv:2610.23104](https://arxiv.org/abs/2610.23104)

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
docs/static/pdf/webcoder_paper.pdf    the paper, the full-resolution arXiv build
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

### Regenerating the figures and the PDF

The images are rendered from the paper's LaTeX sources. Point `PAPER` at your
checkout of the manuscript, then for one figure:

```bash
PAPER=/path/to/manuscript
pdftoppm -f 1 -l 1 -r 170 -png -singlefile "$PAPER/figs/<name>.pdf" /tmp/<name>
cwebp -q 88 -metadata none /tmp/<name>.png -o docs/static/images/<name>.webp
```

The paper itself is served at full resolution; after recompiling, copy the new
build over `docs/static/pdf/webcoder_paper.pdf`.

## Reference images

Nine of the 40 tasks are of `replicate` type and need a reference design image. Those
images are not redistributed with the dataset because their rights have not been cleared;
the dataset card says so and points researchers to the authors.

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
  journal = {arXiv preprint arXiv:2610.23104},
  year    = {2026}
}
```
