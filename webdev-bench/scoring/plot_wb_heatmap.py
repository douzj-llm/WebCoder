#!/usr/bin/env python3
"""RS heat-map figure (models x tasks) for WebDev-Bench.

Reads wb_full.json from wb_full_results.py. The original figure imported a
private house style module; here a small inline style keeps it self-contained.

Usage: python3 plot_wb_heatmap.py [--input data/wb_full.json] [--out figs/fig_wb_heatmap.pdf]
"""
import argparse, json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch

plt.rcParams.update({"font.size": 7, "axes.linewidth": 0.6,
                     "pdf.fonttype": 42, "ps.fonttype": 42})

ap = argparse.ArgumentParser()
ap.add_argument("--input", default=os.path.join("data", "wb_full.json"))
ap.add_argument("--out", default=os.path.join("figs", "fig_wb_heatmap.pdf"))
a = ap.parse_args()
D = json.load(open(a.input))
lines = D['lines']; tasks = sorted(D['tasks'], key=lambda t: -D['mean_rs'][t])
M = np.array([[D['rs_matrix'][l][t] for t in tasks] for l in lines])
cmap = LinearSegmentedColormap.from_list('rs', ['#f7f7f7', '#9fbbd6', '#1f4e79'])
f, ax = plt.subplots(figsize=(6.8, 3.9))
im = ax.imshow(M, cmap=cmap, vmin=0, vmax=1, aspect='auto', interpolation='none')
ax.set_yticks(range(len(lines)), lines, fontsize=6.5)
ax.set_xticks(range(len(tasks)), tasks, fontsize=5.2, rotation=90)
ax.tick_params(length=0)
for s in ax.spines.values(): s.set_visible(False)
# task-type strip
tc = {'brownfield': '#c0504d', 'replicate': '#e0a030', 'prd': '#7fa1c3'}
for j, t in enumerate(tasks):
    ax.add_patch(plt.Rectangle((j - 0.5, len(lines) - 0.5 + 0.15), 1, 0.35,
                               color=tc[D['task_type'][t]], clip_on=False))
ax.set_ylim(len(lines) - 0.5 + 0.6, -0.5)
# tertile separators (cut positions follow the tier sizes in wb_full.json)
cut1 = len(D['tiers']['easy']); cut2 = cut1 + len(D['tiers']['medium'])
for cut in (cut1, cut2): ax.axvline(cut - 0.5, color='white', lw=1.4)
ax.text(cut1 / 2 - 0.5, -0.9, 'easy', ha='center', fontsize=7, color='#5b6b7c')
ax.text((cut1 + cut2) / 2 - 0.5, -0.9, 'medium', ha='center', fontsize=7, color='#5b6b7c')
ax.text((cut2 + len(tasks)) / 2 - 0.5, -0.9, 'hard', ha='center', fontsize=7, color='#5b6b7c')
ax.legend(handles=[Patch(color=v, label=k) for k, v in tc.items()],
          loc='lower left', bbox_to_anchor=(0.0, 1.06), ncol=3, fontsize=6.5,
          handlelength=1.0, frameon=False)
cb = f.colorbar(im, ax=ax, fraction=0.02, pad=0.01)
cb.ax.tick_params(labelsize=6); cb.set_label('RS$_t$', fontsize=7)
os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
f.savefig(a.out, bbox_inches='tight'); print('heatmap', a.out)
