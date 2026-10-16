"""Render film.html frame by frame.

  python3 render.py stills 3.0 15.5 ...   -> /tmp/still_<t>.jpg
  python3 render.py frames OUTDIR [FPS]   -> OUTDIR/000001.jpg ...
"""
import sys, os, time
from playwright.sync_api import sync_playwright

PORT = open('/tmp/filmport').read().strip()
URL = f'http://127.0.0.1:{PORT}/film.html'

def open_page(p):
    b = p.chromium.launch(args=['--no-sandbox', '--no-proxy-server', '--force-color-profile=srgb'])
    pg = b.new_page(viewport={'width': 1920, 'height': 1080}, device_scale_factor=1)
    errs = []
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(URL, wait_until='load', timeout=60000)
    info = pg.evaluate('window.filmReady')
    return b, pg, errs, info

mode = sys.argv[1]
with sync_playwright() as p:
    b, pg, errs, info = open_page(p)
    print('ready:', info, '| errors so far:', errs[:3], flush=True)
    if mode == 'stills':
        for t in sys.argv[2:]:
            pg.evaluate(f'window.renderAt({float(t)})')
            pg.screenshot(path=f'/tmp/still_{t}.jpg', type='jpeg', quality=90)
        print('stills done; errors:', errs[:5])
    else:
        out = sys.argv[2]; fps = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        os.makedirs(out, exist_ok=True)
        dur = pg.evaluate('window.FILM_DURATION'); n = int(round(dur * fps))
        t0 = time.time()
        for i in range(n):
            pg.evaluate(f'window.renderAt({i / fps})')
            pg.screenshot(path=f'{out}/{i+1:06d}.jpg', type='jpeg', quality=93)
            if i % 300 == 0:
                print(f'frame {i}/{n}  {time.time()-t0:.0f}s', flush=True)
        print(f'done {n} frames in {time.time()-t0:.0f}s; errors: {errs[:5]}', flush=True)
    b.close()
