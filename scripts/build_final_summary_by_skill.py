#!/usr/bin/env python3
"""
One combined HTML: 4 tables (one per harness x model combo), one row per skill,
reporting mean +- std of pass_rate over the 10 requirements (batches), for
none / one / delta. Reads the canonical per-cell CSVs produced by
build_final_results.py -> results/final_results/summary_by_skill.html
"""
import csv, html, math, os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

CONFIGS = [
    ("codex__gpt-5.4-mini", "codex × gpt-5.4-mini"),
    ("codex__Kimi-K2.6",    "codex × Kimi-K2.6"),
    ("claude__Kimi-K2.6",   "claude-code × Kimi-K2.6"),
    ("claude__haiku-4-5",   "claude-code × haiku-4.5"),
]

def mstd(xs):
    """mean, population std (over available batches)."""
    if not xs:
        return None, None
    m = sum(xs) / len(xs)
    v = sum((x - m) ** 2 for x in xs) / len(xs)
    return m, math.sqrt(v)

def cell(m, s, n):
    if m is None:
        return '<td class="na">N/A</td>'
    note = f'<span class=n>({n})</span>' if n < 10 else ''
    return f'<td>{m:.1f} <span class=pm>±{s:.1f}</span>{note}</td>'

def dcell(dn, do):
    if dn is None or do is None:
        return '<td class="na">–</td>'
    d = do - dn
    col = "#1a7a1a" if d > 0.5 else ("#b02020" if d < -0.5 else "#667")
    return f'<td style="color:{col};font-weight:600">{"+" if d > 0 else ""}{d:.1f}</td>'

def build():
    sections = []
    for label, title in CONFIGS:
        per = defaultdict(lambda: {"none": [], "one": []})
        for r in list(csv.reader(open(f"results/final_results/{label}_cells.csv")))[1:]:
            skill, _b, n, o, _d = r
            if n: per[skill]["none"].append(float(n))
            if o: per[skill]["one"].append(float(o))
        rows = []
        alln = []; allo = []
        for skill in sorted(per):
            mn, sn = mstd(per[skill]["none"])
            mo, so = mstd(per[skill]["one"])
            alln += per[skill]["none"]; allo += per[skill]["one"]
            rows.append(
                f'<tr><td class=sk>{html.escape(skill)}</td>'
                f'{cell(mn, sn, len(per[skill]["none"]))}'
                f'{cell(mo, so, len(per[skill]["one"]))}'
                f'{dcell(mn, mo)}</tr>'
            )
        gn = sum(alln) / len(alln); go = sum(allo) / len(allo)
        gd = go - gn
        col = "#4caf50" if gd > 0 else "#e57373"
        sections.append(f"""
<section>
<h2 id="{label}">{title}</h2>
<div class=gm>none <b>{gn:.1f}%</b></div><div class=gm>one <b>{go:.1f}%</b></div>
<div class=gm>Δ <b style="color:{col}">{"+" if gd > 0 else ""}{gd:.1f}pp</b></div>
<table><thead><tr><th>skill</th><th>none (mean ± std)</th><th>one (mean ± std)</th><th>Δ mean (pp)</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</section>""")
    nav = ' · '.join(f'<a href="#{lab}">{t}</a>' for lab, t in CONFIGS)
    page = f"""<!doctype html><html><head><meta charset=utf-8>
<title>SWE-Skills-Bench — per-skill summary (mean ± std over 10 requirements)</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0f1115;color:#e6e6e6;margin:0}}
.wrap{{max-width:1000px;margin:0 auto;padding:28px}}
h1{{font-size:22px;margin:0 0 4px}} .sub{{color:#9aa;font-size:13px;margin-bottom:8px;line-height:1.5}}
.nav{{font-size:13px;margin-bottom:24px}} .nav a{{color:#7fa8e0;text-decoration:none;margin-right:4px}}
h2{{font-size:18px;margin:36px 0 10px;border-top:1px solid #2a3345;padding-top:22px}}
.gm{{display:inline-block;background:#1b2130;border:1px solid #2a3345;border-radius:8px;padding:8px 14px;margin:0 8px 14px 0;font-size:13px}}
.gm b{{font-size:16px}}
table{{border-collapse:collapse;width:100%;font-size:12.5px}}
th,td{{padding:3px 10px;text-align:center;border-bottom:1px solid #222}}
th{{position:sticky;top:0;background:#1b2130;z-index:1}}
td.sk{{text-align:left;color:#cdd;white-space:nowrap}}
.pm{{color:#889;font-size:11px}} .n{{color:#c90;font-size:10px;margin-left:3px}}
td.na{{color:#556}} tr:hover td{{background:#1a2233}}
</style></head><body><div class=wrap>
<h1>SWE-Skills-Bench — per-skill summary</h1>
<div class=sub>4 harness × model combos · one row per skill · cells = mean ± std of pass_rate (%) over the 10
requirements (population std; orange (n) marks skills with fewer than 10 scored requirements — residual
one-mode-flake N/A cells). Δ = one − none mean. Canonical data: latest eval report per cell
(2026-07-23 env-fix re-runs included). Per-requirement detail: <a href="index.html" style="color:#7fa8e0">index.html</a>.</div>
<div class=nav>{nav}</div>
{''.join(sections)}
</div></body></html>"""
    out = "results/final_results/summary_by_skill.html"
    open(out, "w").write(page)
    print(f"wrote {out}")

if __name__ == "__main__":
    build()
