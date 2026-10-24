#!/usr/bin/env python3
"""English Full Results fragment for the manuscript appendix.

Reads wb_full.json produced by wb_full_results.py and emits LaTeX tables.
The output uses the paper macros \\rankbest/\\ranksecond/\\ModelName.

Usage: python3 gen_full_results_en.py [--input data/wb_full.json] [--out full_results_en.tex]
"""
import argparse, json, os
B = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME={'Claude Opus 4.8':'Claude-Opus-4.8','GPT-5.4':'GPT-5.4','GPT-5':'GPT-5','Gemini-3-Pro-Preview':'Gemini-3-Pro','Gemini-3-Flash-Preview':'Gemini-3-Flash','Seed-1.8':'Seed-1.8',
 'Kimi-K2.5':'Kimi-K2.5','MiMo-V2.5':'MiMo-V2.5','Step-3.7-Flash':'Step-3.7-Flash','Qwen3.8-27B (base)':'Qwen3.8-27B','Qwen3.5-397B-A17B':'Qwen3.5-397B-A17B','Qwen3.5-122B-A10B':'Qwen3.5-122B-A10B',
 'Qwen3-VL-32B':'Qwen3-VL-32B-Instruct','Qwen3-VL-8B':'Qwen3-VL-8B-Instruct','WebCoder-27B':'\\textbf{\\ModelName{}-27B}'}
GROUPS=[('Proprietary Models',['Claude Opus 4.8','GPT-5.4','GPT-5','Gemini-3-Pro-Preview','Gemini-3-Flash-Preview','Seed-1.8']),
        ('Open-Source Models',['Kimi-K2.5','MiMo-V2.5','Step-3.7-Flash','Qwen3.8-27B (base)','Qwen3.5-397B-A17B','Qwen3.5-122B-A10B','Qwen3-VL-32B','Qwen3-VL-8B']),(None,['WebCoder-27B'])]
ap = argparse.ArgumentParser()
ap.add_argument("--input", default=f'{B}/data/wb_full.json')
ap.add_argument("--out", default=f'{B}/full_results_en.tex')
_a = ap.parse_args()
W = json.load(open(_a.input))
L=W['lines']
from decimal import Decimal,ROUND_HALF_UP
def p1(x): return '--' if x is None else str(Decimal(str(x*100)).quantize(Decimal('0.1'),rounding=ROUND_HALF_UP))
def pct(x): return p1(x)+'\\%'
def ranked(vals):
    xs=sorted({float(p1(v)) for v in vals.values() if v is not None},reverse=True); out={}
    for n,v in vals.items():
        t=p1(v)
        if v is not None:
            r=float(p1(v))
            if xs and r==xs[0]: t=f'\\rankbest{{{t}}}'
            elif len(xs)>1 and r==xs[1]: t=f'\\ranksecond{{{t}}}'
        out[n]=t
    return out
def grouped_rows(rowfn,ncol):
    out=[]
    for title,members in GROUPS:
        if title: out.append(f'    \\rowcolor{{gray!12}}\\multicolumn{{{ncol}}}{{c}}{{\\textit{{\\textbf{{{title}}}}}}} \\\\')
        else: out.append('    \\midrule')
        out+=['    '+rowfn(n) for n in members]
    return out
O=W['overall']
def avg4(o): return (o['RS']+o['VS']+o['FS']+o['IS'])/4
R={k:ranked({n:O[n][k] for n in L}) for k in ('RS','VS','FS','IS')}; R['Avg']=ranked({n:avg4(O[n]) for n in L})
R3={d:ranked({n:O[n]['item3'].get(d) for n in L}) for d in ('functional','coverage','interaction','visual')}
def row1(n): return ' & '.join([NAME[n],R['RS'][n],R['VS'][n],R['FS'][n],R['IS'][n],R['Avg'][n],pct(O[n]['DSR'])]+[R3[d][n] for d in ('functional','coverage','interaction','visual')])+' \\\\'
t1=r'''\begin{table}[t]
    \centering
    \small
    \renewcommand{\arraystretch}{1.15}
    \setlength{\tabcolsep}{5pt}
    \caption{\textbf{Full Webdev-Bench results.} The left six columns follow the metrics and ordering of Table~\ref{tab:main_results}; the right four columns give the item-level grade-3 rate, i.e., the fraction of checklist items of each dimension graded $3$ at terminal acceptance (items of undelivered tasks count as grade $0$). Best in bold, second best underlined.}
    \label{tab:full-wb}
    \resizebox{\linewidth}{!}{
    \begin{tabular}{lcccccc|cccc}
    \toprule
    \multirow{2}{*}{\textbf{Model}} & \multicolumn{6}{c|}{\textbf{Webdev-Bench}} & \multicolumn{4}{c}{\textbf{Item grade-3 rate}} \\
    \cmidrule(lr){2-7}\cmidrule(lr){8-11}
    & \textbf{RS} & \textbf{VS} & \textbf{FS} & \textbf{IS} & \textit{Avg} & \textit{DSR} & Functional & Coverage & Interaction & Visual \\
    \midrule
'''+'\n'.join(grouped_rows(row1,11))+r'''
    \bottomrule
    \end{tabular}}
\end{table}'''
keys=['brownfield','replicate','prd']; labels=[f'Brownfield ($n$={len(W["types"]["brownfield"])})',f'Replication ($n$={len(W["types"]["replicate"])})',f'Text-to-project ($n$={len(W["types"]["prd"])})']
M=('RS','VS','FS','IS'); RK={k:{m:ranked({n:W['by_type'][k][n][m] for n in L}) for m in M} for k in keys}
def row2(n): return ' & '.join([NAME[n]]+[RK[k][m][n] for k in keys for m in M])+' \\\\'
t2=r'''\begin{table}[t]
    \centering
    \small
    \renewcommand{\arraystretch}{1.15}
    \setlength{\tabcolsep}{4pt}
    \caption{\textbf{Webdev-Bench results by task starting point.} Tasks start from an existing repository (brownfield), a reference screenshot (replication), or a textual specification (text-to-project); each cell is the mean over the tasks of that type, with undelivered tasks counted as $0$. Best in bold, second best underlined.}
    \label{tab:full-wb-type}
    \resizebox{\linewidth}{!}{
    \begin{tabular}{lcccccccccccc}
    \toprule
    \multirow{2}{*}{\textbf{Model}} & '''+' & '.join(f'\\multicolumn{{4}}{{c}}{{\\textbf{{{l}}}}}' for l in labels)+r''' \\
    \cmidrule(lr){2-5}\cmidrule(lr){6-9}\cmidrule(lr){10-13}
    & '''+' & '.join(['\\textbf{RS}','\\textbf{VS}','\\textbf{FS}','\\textbf{IS}']*3)+r''' \\
    \midrule
'''+'\n'.join(grouped_rows(row2,13))+r'''
    \bottomrule
    \end{tabular}}
\end{table}'''
wc=O['WebCoder-27B']; bs=O['Qwen3.8-27B (base)']; bt=W['by_type']
text=r'''\section{Full Results}
\label{app:full-results}

Table~\ref{tab:full-wb} reports the complete Webdev-Bench metrics of every evaluated model, using the same models, ordering, and scoring as Table~\ref{tab:main_results}. The four right-hand columns give the item-level grade-3 rate per requirement dimension, which is unaffected by the conjunctive rule and shows the absolute degree of completion: \ModelName{} reaches '''+f"{wc['item3']['interaction']*100:.0f}"+r'''\% on interaction items, the highest of all models, and '''+f"{wc['item3']['functional']*100:.0f}"+r'''\% on functional items, against '''+f"{bs['item3']['interaction']*100:.0f}"+r'''\% and '''+f"{bs['item3']['functional']*100:.0f}"+r'''\% for the base model.

Table~\ref{tab:full-wb-type} splits the results by task starting point. The gains of \ModelName{} over the base model concentrate on text-to-project tasks (RS '''+f"{bt['prd']['WebCoder-27B']['RS']*100:.1f}"+r''' versus '''+f"{bt['prd']['Qwen3.8-27B (base)']['RS']*100:.1f}"+r''', with Claude-Opus-4.8 at '''+f"{bt['prd']['Claude Opus 4.8']['RS']*100:.1f}"+r''') and on replication tasks (RS '''+f"{bt['replicate']['WebCoder-27B']['RS']*100:.1f}"+r''' versus '''+f"{bt['replicate']['Qwen3.8-27B (base)']['RS']*100:.1f}"+r'''); on text-to-project tasks \ModelName{} has the highest value in all four metrics.

'''+t1+'\n\n'+t2+'\n'
open(_a.out,'w').write(text); print('written',len(text))
