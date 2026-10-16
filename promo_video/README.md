# WebCoder promo film

A 120-second, 1920x1080, 30 fps promotional video generated from code.
`film.html` is a deterministic renderer: `window.renderAt(t)` draws the frame at
time `t`, and nothing animates on its own. `render.py` steps `t` and screenshots
each frame; ffmpeg encodes the sequence.

The encoded result is committed as
`../docs/static/video/webcoder_promo_1080p.{mp4,webm}`; everything below rebuilds it.

Requirements: Python 3 with Playwright (Chromium), ffmpeg, and NumPy + SciPy for
the soundtrack.

## One scene's footage is not in this repository

`assets/clips/c22/` holds 552 JPEG frames (51 MB) of a screen recording of the
rebuilt deliverable being driven in a browser; it backs the live-app scene, S11
(98.5–114 s). It is excluded to keep the repository small, so a re-render
produces a blank panel for that scene — every other scene is complete. The frame
timings it is keyed to are in `assets/clips/c22_marks.json`, which *is* tracked.

## Re-render

```bash
cd promo_video
python3 -m http.server 5340 --bind 127.0.0.1 &      # any free port
echo 5340 > /tmp/filmport
python3 render.py stills 10.5 66 92                  # spot-check frames -> /tmp/still_*.jpg
python3 render.py frames /tmp/film_frames 30         # all 3600 frames, about 4 minutes
ffmpeg -framerate 30 -i /tmp/film_frames/%06d.jpg -c:v libopenh264 -b:v 7000k -g 60 \
       -pix_fmt yuv420p -movflags +faststart webcoder_promo_1080p.mp4
ffmpeg -framerate 30 -i /tmp/film_frames/%06d.jpg -c:v libvpx-vp9 -b:v 0 -crf 30 \
       -row-mt 1 -cpu-used 4 -g 60 -pix_fmt yuv420p webcoder_promo_1080p.webm
```

Scene timings live in the `T` table in `film.html`.

## Soundtrack

`score.py` builds the 120 s audio track from the same scene table, so every cue lands on
the frame that triggers it. The music bed is "Inspired" by Kevin MacLeod (incompetech.com,
CC BY 4.0, 120 bpm; `assets/music/Inspired.mp3` + `Inspired.json` metadata). At 120 bpm a
bar is 2 s, so every scene boundary is a bar line; the bed is spliced at bar boundaries
(`TRACKS['Inspired']['edl']`) so that the hats enter at the training curve (48 s), the densest
section carries the results (64 s), and the track's final chord lands on the title card (114 s).
On top, synthesised cues: typing while the request/code is written, one tick per checklist
item, a riser into +66.2 %, bells on +66.2 % / +21.3, an ascending run as the 24-site wall
fills, a chime as each live-app requirement lights up, and a short whoosh on each cut.
Two alternates that were auditioned (`Delightful D`, `Nowhere Land`) are kept in the table;
their mp3s are not in the repository, so only `Inspired` builds out of the box.

`score.py` reads a 48 kHz stereo wav, which is derived from the mp3 and not tracked — the
first command below creates it:

```bash
ffmpeg -i assets/music/Inspired.mp3 -ac 2 -ar 48000 assets/music/Inspired_120.wav
python3 score.py Inspired /tmp/Inspired_mix.wav             # also writes /tmp/Inspired_music.wav
# -2.4 dB brings the mix to -16 LUFS integrated (measure with -af ebur128 if the mix changes)
ffmpeg -i webcoder_promo_1080p.mp4 -i /tmp/Inspired_mix.wav -map 0:v -map 1:a -c:v copy \
       -af "volume=-2.4dB,alimiter=limit=0.94:attack=3:release=60" -c:a aac -b:a 192k \
       -movflags +faststart -shortest out.mp4
ffmpeg -i webcoder_promo_1080p.webm -i /tmp/Inspired_mix.wav -map 0:v -map 1:a -c:v copy \
       -af "volume=-2.4dB,alimiter=limit=0.94:attack=3:release=60" -c:a libopus -b:a 128k -shortest out.webm
```

## Where every number and picture comes from

Every figure quoted on screen was checked against the paper. Sources below are named as
they appear in the paper; the raw run artefacts they were extracted from are not part of
this repository.

| Scene | Source |
|---|---|
| Hook request | Figure 1 of the paper |
| Webdev-World editor | `src/App.jsx` of the agent's c22 deliverable |
| Webdev-World terminal | real `vite build` of that source |
| Webdev-World browser | c22 starting-repo screenshot, then the agent's round-5 full-page capture |
| Verifier, 27 items, RS 1.0 vs 0.6 | c22 `task.json` checklist; Section 4.4 case study |
| Credit assignment | **illustration** of the mechanism, labelled as such on screen |
| Context sizes | Section 4.1 setup |
| Anchor curve | run-63 anchor scores; step 19 excluded, as in the paper's figure |
| Webdev-Bench counts | Section 4.1 |
| Result bars | Table 1 |
| Ablation | Section 4.3 |
| wildapricot, 24-site wall | Vision2Web comparison, base vs. final run |
| Live app | Playwright driving the rebuilt c22 deliverable (footage not included, see above) |
