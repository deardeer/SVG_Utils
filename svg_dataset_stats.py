#!/usr/bin/env python3
"""
Compute statistics over a folder of SVG files: path counts, structural
complexity, color usage, and "quality" indicators (tiny/duplicate/overlapping
paths). Prints a summary report with ASCII histograms to the terminal, and
optionally writes a per-file CSV, a self-contained HTML report with SVG
charts, and/or a matplotlib histogram grid.

Usage:
    python svg_dataset_stats.py /path/to/svgs
    python svg_dataset_stats.py /path/to/svgs -r --csv stats.csv --html stats.html --plot stats.png
"""

import argparse
import csv
import html
import math
import os
import re
import statistics as stats
import xml.etree.ElementTree as ET

COORD_RE = re.compile(r'-?\d*\.?\d+(?:[eE][-+]?\d+)?')
CMD_RE = re.compile(r'[MLHVCSQTAZmlhvcsqtaz]')
CURVE_CMDS = set('cqsta')  # cubic, quadratic, smooth-cubic, smooth-quad, arc
LENGTH_RE = re.compile(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?')


def local_name(tag):
    return tag.split('}')[-1] if '}' in tag else tag


def parse_length(value):
    if not value:
        return 0.0
    m = LENGTH_RE.match(value.strip())
    return float(m.group()) if m else 0.0


def analyze_svg(filepath):
    size_bytes = os.path.getsize(filepath)
    try:
        root = ET.parse(filepath).getroot()
    except ET.ParseError:
        return {'filename': filepath, 'parse_error': True, 'size_bytes': size_bytes, 'path_count': 0}

    vb_w = vb_h = 0.0
    viewbox = root.get('viewBox')
    if viewbox:
        parts = re.split(r'[\s,]+', viewbox.strip())
        if len(parts) == 4:
            try:
                vb_w, vb_h = float(parts[2]), float(parts[3])
            except ValueError:
                pass
    if not vb_w or not vb_h:
        vb_w = vb_w or parse_length(root.get('width', ''))
        vb_h = vb_h or parse_length(root.get('height', ''))
    vb_area = vb_w * vb_h

    paths = [el for el in root.iter() if local_name(el.tag) == 'path']
    group_count = sum(1 for el in root.iter() if local_name(el.tag) == 'g')

    fill_colors, stroke_colors = set(), set()
    paths_with_fill = paths_with_stroke = paths_with_both = paths_with_neither = 0
    opacity_sum, opacity_count = 0.0, 0
    total_commands, curve_commands = 0, 0
    total_data_length = 0
    tiny_path_count = 0
    total_bbox_area = 0.0
    seen_d = set()
    duplicate_count = 0

    for p in paths:
        d = p.get('d', '') or ''
        total_data_length += len(d)

        if d:
            if d in seen_d:
                duplicate_count += 1
            else:
                seen_d.add(d)

        fill = (p.get('fill') or '').strip().lower()
        stroke = (p.get('stroke') or '').strip().lower()
        has_fill = bool(fill) and fill != 'none'
        has_stroke = bool(stroke) and stroke != 'none'
        if has_fill:
            fill_colors.add(fill)
        if has_stroke:
            stroke_colors.add(stroke)
        if has_fill and has_stroke:
            paths_with_both += 1
        elif has_fill:
            paths_with_fill += 1
        elif has_stroke:
            paths_with_stroke += 1
        else:
            paths_with_neither += 1

        opacity = p.get('opacity')
        if opacity is not None:
            try:
                opacity_sum += float(opacity)
                opacity_count += 1
            except ValueError:
                pass

        cmds = CMD_RE.findall(d)
        total_commands += len(cmds)
        curve_commands += sum(1 for c in cmds if c.lower() in CURVE_CMDS)

        coords = COORD_RE.findall(d)
        min_x, min_y = math.inf, math.inf
        max_x, max_y = -math.inf, -math.inf
        for i in range(0, len(coords) - 1, 2):
            try:
                x, y = float(coords[i]), float(coords[i + 1])
            except ValueError:
                continue
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
        if min_x != math.inf:
            area = max(0.0, max_x - min_x) * max(0.0, max_y - min_y)
            total_bbox_area += area
            if vb_area > 0 and area / vb_area < 0.0005:
                tiny_path_count += 1

    n = len(paths)
    return {
        'filename': filepath,
        'parse_error': False,
        'size_bytes': size_bytes,
        'path_count': n,
        'group_count': group_count,
        'vb_w': vb_w,
        'vb_h': vb_h,
        'aspect_ratio': (vb_w / vb_h) if vb_h else 0.0,
        'total_commands': total_commands,
        'avg_commands_per_path': (total_commands / n) if n else 0.0,
        'curve_ratio': (curve_commands / total_commands) if total_commands else 0.0,
        'unique_fill_colors': len(fill_colors),
        'unique_stroke_colors': len(stroke_colors),
        'unique_colors': len(fill_colors | stroke_colors),
        'fill_colors': fill_colors,
        'paths_with_fill': paths_with_fill,
        'paths_with_stroke': paths_with_stroke,
        'paths_with_both': paths_with_both,
        'paths_with_neither': paths_with_neither,
        'avg_opacity': (opacity_sum / opacity_count) if opacity_count else 1.0,
        'avg_path_data_length': (total_data_length / n) if n else 0.0,
        'tiny_path_count': tiny_path_count,
        'tiny_path_ratio': (tiny_path_count / n) if n else 0.0,
        'coverage_ratio': (total_bbox_area / vb_area) if vb_area > 0 else 0.0,
        'duplicate_path_count': duplicate_count,
        'duplicate_ratio': (duplicate_count / n) if n else 0.0,
    }


def find_svg_files(folder, recursive):
    if recursive:
        for dirpath, _, filenames in os.walk(folder):
            for name in sorted(filenames):
                if name.lower().endswith('.svg'):
                    yield os.path.join(dirpath, name)
    else:
        for name in sorted(os.listdir(folder)):
            if name.lower().endswith('.svg'):
                yield os.path.join(folder, name)


def ascii_histogram(values, bins=10, width=40, pct=False, fmt='{:.2f}'):
    valid = [v for v in values if v is not None and not math.isnan(v)]
    if not valid:
        return '  (no data)'

    lo, hi = min(valid), max(valid)
    if lo == hi:
        lo, hi = lo - 0.5, hi + 0.5
    bin_size = (hi - lo) / bins

    counts = [0] * bins
    for v in valid:
        idx = int((v - lo) / bin_size)
        idx = max(0, min(bins - 1, idx))
        counts[idx] += 1
    max_count = max(counts) or 1

    def label(v):
        return f'{v * 100:.0f}%' if pct else fmt.format(v)

    lines = []
    for i in range(bins):
        edge_lo, edge_hi = lo + i * bin_size, lo + (i + 1) * bin_size
        bar = '#' * round(counts[i] / max_count * width)
        lines.append(f'  [{label(edge_lo):>8} .. {label(edge_hi):>8}] {bar:<{width}} {counts[i]}')
    return '\n'.join(lines)


def fmt_bytes(n):
    if n < 1024:
        return f'{n} B'
    if n < 1024 * 1024:
        return f'{n / 1024:.1f} KB'
    return f'{n / (1024 * 1024):.2f} MB'


def pstdev(values):
    return stats.pstdev(values) if len(values) > 1 else 0.0


def print_summary(all_results, valid):
    path_counts = [r['path_count'] for r in valid]
    sizes = [r['size_bytes'] for r in all_results]
    all_colors = set()
    for r in valid:
        all_colors |= r['fill_colors']

    print('=' * 60)
    print('SUMMARY')
    print('=' * 60)
    print(f'  Files analyzed:            {len(all_results)}')
    print(f'  Files with >=1 path:       {len(valid)}')
    print(f'  Total paths:               {sum(path_counts)}')
    if path_counts:
        print(f'  Paths/file  mean/median:   {stats.mean(path_counts):.2f} / {stats.median(path_counts):.1f}')
        print(f'  Paths/file  min/max:       {min(path_counts)} / {max(path_counts)}')
        print(f'  Paths/file  std dev:       {pstdev(path_counts):.2f}')
    print(f'  Total file size:           {fmt_bytes(sum(sizes))}')
    print(f'  Avg file size:             {fmt_bytes(round(stats.mean(sizes))) if sizes else "0 B"}')
    print(f'  Distinct fill colors:      {len(all_colors)} (across whole dataset)')
    if valid:
        print(f'  Avg commands/path:         {stats.mean(r["avg_commands_per_path"] for r in valid):.2f}')
        print(f'  Avg curve-cmd ratio:       {stats.mean(r["curve_ratio"] for r in valid) * 100:.1f}%')
        print(f'  Avg tiny-path ratio:       {stats.mean(r["tiny_path_ratio"] for r in valid) * 100:.1f}%')
        print(f'  Avg bbox coverage ratio:   {stats.mean(r["coverage_ratio"] for r in valid):.2f}')
        print(f'  Avg duplicate-path ratio:  {stats.mean(r["duplicate_ratio"] for r in valid) * 100:.1f}%')


def print_flags(all_results, valid):
    print()
    print('=' * 60)
    print('QUALITY FLAGS')
    print('=' * 60)
    flags = []

    errored = [r for r in all_results if r['parse_error']]
    if errored:
        flags.append(f'{len(errored)} file(s) failed to parse as valid XML/SVG:')
        for r in errored[:10]:
            flags.append(f'    - {r["filename"]}')

    empty = [r for r in all_results if not r['parse_error'] and r['path_count'] == 0]
    if empty:
        flags.append(f'{len(empty)} file(s) contain no <path> elements:')
        for r in empty[:10]:
            flags.append(f'    - {r["filename"]}')

    if valid:
        path_counts = [r['path_count'] for r in valid]
        m, s = stats.mean(path_counts), pstdev(path_counts)
        if s > 0:
            outliers = [r for r in valid if abs(r['path_count'] - m) > 2 * s]
            if outliers:
                flags.append(f'{len(outliers)} file(s) have path counts >2 std dev from the mean '
                              f'(mean={m:.1f}, std={s:.1f}):')
                for r in sorted(outliers, key=lambda r: -r['path_count'])[:10]:
                    flags.append(f'    - {r["filename"]}: {r["path_count"]} paths')

        noisy = [r for r in valid if r['tiny_path_ratio'] > 0.25]
        if noisy:
            flags.append(f'{len(noisy)} file(s) have >25% tiny paths '
                          f'(bbox <0.05% of canvas) — possible over-segmentation:')
            for r in sorted(noisy, key=lambda r: -r['tiny_path_ratio'])[:10]:
                flags.append(f'    - {r["filename"]}: {r["tiny_path_ratio"] * 100:.1f}% tiny')

        dup_heavy = [r for r in valid if r['duplicate_ratio'] > 0.1]
        if dup_heavy:
            flags.append(f'{len(dup_heavy)} file(s) have >10% duplicate path data:')
            for r in sorted(dup_heavy, key=lambda r: -r['duplicate_ratio'])[:10]:
                flags.append(f'    - {r["filename"]}: {r["duplicate_ratio"] * 100:.1f}% duplicate')

        low_cov = [r for r in valid if 0 < r['coverage_ratio'] < 0.05]
        if low_cov:
            flags.append(f'{len(low_cov)} file(s) have <5% bbox coverage of the canvas:')
            for r in sorted(low_cov, key=lambda r: r['coverage_ratio'])[:10]:
                flags.append(f'    - {r["filename"]}: coverage={r["coverage_ratio"]:.3f}')

    if flags:
        for f in flags:
            print(f'  {f}')
    else:
        print('  No issues detected.')


HISTOGRAMS = [
    ('path_count', 'Paths per SVG',
     'Number of <path> elements in each file. A wide spread suggests inconsistent '
     'vectorization complexity across the dataset.', {'fmt': '{:.0f}'}),
    ('group_count', 'Groups (<g>) per SVG',
     'Number of <g> elements — a rough proxy for layering / structural nesting.', {'fmt': '{:.0f}'}),
    ('avg_commands_per_path', 'Avg path commands per path',
     'Average number of drawing commands (M/L/C/Q/A/...) per path — higher means more '
     'detailed / complex individual shapes.', {}),
    ('curve_ratio', 'Curve command ratio',
     'Share of path commands that are curves (C/S/Q/T/A) vs. straight lines (L) — higher '
     'values indicate smoother, more organic shapes.', {'pct': True}),
    ('unique_colors', 'Unique colors per SVG',
     'Number of distinct fill+stroke colors used in a single file — a proxy for palette richness.', {'fmt': '{:.0f}'}),
    ('aspect_ratio', 'ViewBox aspect ratio (W/H)',
     "Width-to-height ratio of each SVG's viewBox. 1.0 = square.", {}),
    ('tiny_path_ratio', 'Tiny-path ratio',
     'Fraction of paths whose bounding box covers less than 0.05% of the canvas area — a '
     'possible indicator of noisy / over-segmented vectorization.', {'pct': True}),
    ('coverage_ratio', 'Bbox coverage ratio',
     "Sum of each path's bounding-box area divided by the canvas area. Values well above 1 "
     'indicate heavy overlap between paths; near 0 indicates sparse content.', {}),
    ('duplicate_ratio', 'Duplicate path ratio',
     'Fraction of paths whose "d" attribute is an exact duplicate of another path in the '
     'same file — possible redundant/duplicated layers.', {'pct': True}),
]


def print_histograms(valid, bins):
    print()
    print('=' * 60)
    print('HISTOGRAMS')
    print('=' * 60)

    sizes_kb = [r['size_bytes'] / 1024 for r in valid]
    print('\nFile size (KB)')
    print(ascii_histogram(sizes_kb, bins=bins))

    for key, title, _desc, opts in HISTOGRAMS:
        values = [r[key] for r in valid]
        print(f'\n{title}')
        print(ascii_histogram(values, bins=bins, **opts))


def print_top_colors(valid, top_n):
    print()
    print('=' * 60)
    print(f'TOP {top_n} FILL COLORS (by number of files using them)')
    print('=' * 60)
    counts = {}
    for r in valid:
        for c in r['fill_colors']:
            counts[c] = counts.get(c, 0) + 1
    for color, count in sorted(counts.items(), key=lambda kv: -kv[1])[:top_n]:
        print(f'  {color:<20} {count}')


CSV_FIELDS = [
    'filename', 'parse_error', 'size_bytes', 'path_count', 'group_count',
    'vb_w', 'vb_h', 'aspect_ratio', 'total_commands', 'avg_commands_per_path',
    'curve_ratio', 'unique_fill_colors', 'unique_stroke_colors', 'unique_colors',
    'paths_with_fill', 'paths_with_stroke', 'paths_with_both', 'paths_with_neither',
    'avg_opacity', 'avg_path_data_length', 'tiny_path_count', 'tiny_path_ratio',
    'coverage_ratio', 'duplicate_path_count', 'duplicate_ratio',
]


def write_csv(all_results, path):
    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction='ignore')
        writer.writeheader()
        for r in all_results:
            writer.writerow(r)
    print(f'\nWrote per-file CSV to: {path}')


def save_plot(valid, path, bins):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print('\n[plot] matplotlib is not available — skipping image output.')
        return

    charts = [('size_kb', 'File size (KB)')] + [(k, t) for k, t, _desc, _opts in HISTOGRAMS]
    sizes_kb = [r['size_bytes'] / 1024 for r in valid]

    ncols = 3
    nrows = math.ceil(len(charts) / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(5 * ncols, 3.5 * nrows))
    axes = axes.flatten()

    opts_by_key = {k: o for k, _t, _desc, o in HISTOGRAMS}
    for ax, (key, title) in zip(axes, charts):
        values = sizes_kb if key == 'size_kb' else [r[key] for r in valid]
        ax.hist(values, bins=bins, color='#5a8ab5', edgecolor='#333')
        ax.set_title(title, fontsize=10)
        if opts_by_key.get(key, {}).get('pct'):
            ax.set_xlabel('ratio')

    for ax in axes[len(charts):]:
        ax.axis('off')

    fig.tight_layout()
    fig.savefig(path, dpi=120)
    print(f'\nWrote histogram plot to: {path}')


def svg_histogram_chart(values, bins=10, pct=False, fmt='{:.2f}', width=380, height=200, color='#5a8ab5'):
    """Render a histogram of `values` as an inline SVG bar chart."""
    pad_left, pad_right, pad_top, pad_bottom = 10, 10, 18, 26
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    valid = [v for v in values if v is not None and not math.isnan(v)]
    if not valid:
        body = (f'<text x="{width / 2}" y="{height / 2}" fill="#666" font-size="12" '
                f'text-anchor="middle">No data</text>')
        return f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}">{body}</svg>'

    lo, hi = min(valid), max(valid)
    if lo == hi:
        lo, hi = lo - 0.5, hi + 0.5
    bin_size = (hi - lo) / bins

    counts = [0] * bins
    for v in valid:
        idx = int((v - lo) / bin_size)
        idx = max(0, min(bins - 1, idx))
        counts[idx] += 1
    max_count = max(counts) or 1
    bar_w = plot_w / bins

    parts = []
    for i, c in enumerate(counts):
        bar_h = (c / max_count) * plot_h
        x = pad_left + i * bar_w
        y = pad_top + (plot_h - bar_h)
        parts.append(f'<rect x="{x + 1:.1f}" y="{y:.1f}" width="{max(bar_w - 2, 0.5):.1f}" '
                      f'height="{bar_h:.1f}" fill="{color}" />')
        if c > 0:
            parts.append(f'<text x="{x + bar_w / 2:.1f}" y="{y - 3:.1f}" fill="#ccc" '
                          f'font-size="10" text-anchor="middle">{c}</text>')

    def label(v):
        return f'{v * 100:.0f}%' if pct else fmt.format(v)

    mid = (lo + hi) / 2
    parts.append(f'<text x="{pad_left}" y="{height - 8}" fill="#888" font-size="10" '
                  f'text-anchor="start">{label(lo)}</text>')
    parts.append(f'<text x="{width / 2}" y="{height - 8}" fill="#888" font-size="10" '
                  f'text-anchor="middle">{label(mid)}</text>')
    parts.append(f'<text x="{width - pad_right}" y="{height - 8}" fill="#888" font-size="10" '
                  f'text-anchor="end">{label(hi)}</text>')

    return f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}">{"".join(parts)}</svg>'


def svg_color_chart(color_counts, top_n=8, width=380, height=200):
    """Render the top fill colors (by file count) as a horizontal bar chart with swatches."""
    entries = sorted(color_counts.items(), key=lambda kv: -kv[1])[:top_n]
    if not entries:
        body = (f'<text x="10" y="20" fill="#666" font-size="12">No fill colors found</text>')
        return f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}">{body}</svg>'

    max_count = max(c for _, c in entries)
    row_h = height / len(entries)
    parts = []
    for i, (color, count) in enumerate(entries):
        y = i * row_h
        swatch = min(row_h - 6, 14)
        safe_color = html.escape(color, quote=True) or 'none'
        bar_w = (count / max_count) * (width - 110)
        parts.append(f'<rect x="6" y="{y + (row_h - swatch) / 2:.1f}" width="{swatch:.1f}" '
                      f'height="{swatch:.1f}" fill="{safe_color}" stroke="#555" />')
        parts.append(f'<rect x="26" y="{y + row_h * 0.3:.1f}" width="{bar_w:.1f}" '
                      f'height="{row_h * 0.4:.1f}" fill="#5a8ab5" />')
        parts.append(f'<text x="30" y="{y + row_h * 0.55 + 8:.1f}" fill="#ccc" font-size="10">'
                      f'{html.escape(color)} ({count})</text>')
    return f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}">{"".join(parts)}</svg>'


TABLE_COLUMNS = [
    ('filename', 'File', lambda r: html.escape(os.path.basename(r['filename']))),
    ('path_count', 'Paths', lambda r: r['path_count']),
    ('group_count', 'Groups', lambda r: r['group_count']),
    ('avg_commands_per_path', 'Avg cmds/path', lambda r: f"{r['avg_commands_per_path']:.2f}"),
    ('curve_ratio', 'Curve %', lambda r: f"{r['curve_ratio'] * 100:.1f}"),
    ('unique_colors', 'Colors', lambda r: r['unique_colors']),
    ('size_bytes', 'Size', lambda r: fmt_bytes(r['size_bytes'])),
    ('aspect_ratio', 'Aspect (W/H)', lambda r: f"{r['aspect_ratio']:.2f}"),
    ('tiny_path_ratio', 'Tiny %', lambda r: f"{r['tiny_path_ratio'] * 100:.1f}"),
    ('coverage_ratio', 'Coverage', lambda r: f"{r['coverage_ratio']:.2f}"),
    ('duplicate_ratio', 'Dup %', lambda r: f"{r['duplicate_ratio'] * 100:.1f}"),
]


def write_html_report(all_results, valid, out_path, bins, top_n):
    path_counts = [r['path_count'] for r in valid]
    sizes = [r['size_bytes'] for r in all_results]
    all_colors = set()
    for r in valid:
        all_colors |= r['fill_colors']

    cards = [
        (len(all_results), 'SVG files'),
        (sum(path_counts), 'Total paths'),
        (f'{stats.mean(path_counts):.2f}' if path_counts else '–', 'Avg paths / file'),
        (f'{stats.median(path_counts):.1f}' if path_counts else '–', 'Median paths / file'),
        (min(path_counts) if path_counts else '–', 'Min paths'),
        (max(path_counts) if path_counts else '–', 'Max paths'),
        (fmt_bytes(sum(sizes)), 'Total size'),
        (fmt_bytes(round(stats.mean(sizes))) if sizes else '0 B', 'Avg file size'),
        (len(all_colors), 'Distinct fill colors (dataset)'),
        (f'{stats.mean(r["avg_commands_per_path"] for r in valid):.2f}' if valid else '–', 'Avg commands / path'),
        (f'{stats.mean(r["curve_ratio"] for r in valid) * 100:.1f}%' if valid else '–', 'Avg curve command ratio'),
    ]
    summary_html = ''.join(
        f'<div class="stat-card"><div class="val">{v}</div><div class="lbl">{l}</div></div>'
        for v, l in cards
    )

    # ---- quality flags ----
    flags = []
    errored = [r for r in all_results if r['parse_error']]
    if errored:
        flags.append(f'<b>{len(errored)} file(s)</b> failed to parse as valid XML/SVG.')
    empty = [r for r in all_results if not r['parse_error'] and r['path_count'] == 0]
    if empty:
        flags.append(f'<b>{len(empty)} file(s)</b> contain no &lt;path&gt; elements.')
    if path_counts:
        m, s = stats.mean(path_counts), pstdev(path_counts)
        if s > 0:
            outliers = [r for r in valid if abs(r['path_count'] - m) > 2 * s]
            if outliers:
                flags.append(f'<b>{len(outliers)} file(s)</b> have a path count more than '
                              f'2&sigma; from the mean (mean {m:.1f}, &sigma; {s:.1f}) — '
                              f'unusually simple or complex outputs.')
        noisy = [r for r in valid if r['tiny_path_ratio'] > 0.25]
        if noisy:
            flags.append(f'<b>{len(noisy)} file(s)</b> have &gt;25% tiny paths (bounding box '
                          f'&lt;0.05% of canvas) — possible noise / over-segmentation.')
        dup_heavy = [r for r in valid if r['duplicate_ratio'] > 0.1]
        if dup_heavy:
            flags.append(f'<b>{len(dup_heavy)} file(s)</b> have &gt;10% duplicate path data — '
                          f'possible redundant layers.')
        low_cov = [r for r in valid if 0 < r['coverage_ratio'] < 0.05]
        if low_cov:
            flags.append(f'<b>{len(low_cov)} file(s)</b> have very low bounding-box coverage '
                          f'(&lt;5% of canvas) — content may be tiny or off-canvas.')
    flags_html = ''.join(f'<div class="flag">{f}</div>' for f in flags)
    flags_class = ' has-items' if flags else ''

    # ---- charts ----
    chart_cards = []
    sizes_kb = [r['size_bytes'] / 1024 for r in valid]
    chart_cards.append(('File size (KB)',
                         'Raw SVG file size on disk — correlates with path count and path data verbosity.',
                         svg_histogram_chart(sizes_kb, bins=bins)))
    for key, title, desc, opts in HISTOGRAMS:
        values = [r[key] for r in valid]
        chart_cards.append((title, desc, svg_histogram_chart(values, bins=bins, **opts)))

    color_counts = {}
    for r in valid:
        for c in r['fill_colors']:
            color_counts[c] = color_counts.get(c, 0) + 1
    chart_cards.append((
        'Most common fill colors',
        'The most frequently used fill colors across the dataset, by number of files using that exact color value.',
        svg_color_chart(color_counts, top_n=top_n),
    ))

    charts_html = ''.join(
        f'<div class="chart-card"><h2>{html.escape(title)}</h2>{svg}<div class="chart-desc">{desc}</div></div>'
        for title, desc, svg in chart_cards
    )

    # ---- per-file table ----
    rows_html = []
    for r in sorted(all_results, key=lambda r: -r['path_count']):
        if r['parse_error']:
            rows_html.append(f'<tr><td class="fname warn">{html.escape(os.path.basename(r["filename"]))}</td>'
                              f'<td colspan="{len(TABLE_COLUMNS) - 1}" class="warn">Parse error</td></tr>')
            continue
        if r['path_count'] == 0:
            rows_html.append(f'<tr><td class="fname warn">{html.escape(os.path.basename(r["filename"]))}</td>'
                              f'<td colspan="{len(TABLE_COLUMNS) - 1}" class="warn">No &lt;path&gt; elements</td></tr>')
            continue
        cells = []
        for key, _label, getter in TABLE_COLUMNS:
            cls = ' class="fname"' if key == 'filename' else ''
            cells.append(f'<td{cls}>{getter(r)}</td>')
        rows_html.append('<tr>' + ''.join(cells) + '</tr>')
    table_header = ''.join(f'<th>{html.escape(label)}</th>' for _key, label, _getter in TABLE_COLUMNS)

    html_doc = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SVG Dataset Statistics</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #1a1a1a; color: #e0e0e0; font-family: system-ui, sans-serif;
    padding: 24px 16px 60px; display: flex; flex-direction: column; align-items: center;
  }}
  h1 {{ font-size: 20px; font-weight: 500; letter-spacing: 0.04em; color: #888; margin-bottom: 16px; text-transform: uppercase; }}
  h2 {{ font-size: 14px; color: #aaa; margin-bottom: 8px; font-weight: 500; }}
  .wrap {{ width: 100%; max-width: 1300px; display: flex; flex-direction: column; gap: 20px; }}

  .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }}
  .stat-card {{ background: #2a2a2a; border-radius: 10px; padding: 14px; text-align: center; box-shadow: 0 4px 20px rgba(0,0,0,0.35); }}
  .stat-card .val {{ font-size: 22px; color: #fff; font-weight: 600; }}
  .stat-card .lbl {{ font-size: 11px; color: #888; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.04em; }}

  #flags {{ display: flex; flex-direction: column; gap: 8px; }}
  .flag {{ background: #2a2a2a; border-left: 4px solid #c97a3d; border-radius: 6px; padding: 10px 14px; font-size: 13px; color: #ddd; }}
  .flag b {{ color: #ffcf9c; }}

  .charts-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 16px; }}
  .chart-card {{ background: #2a2a2a; border-radius: 10px; padding: 14px; box-shadow: 0 4px 20px rgba(0,0,0,0.35); }}
  .chart-desc {{ font-size: 11px; color: #777; margin-top: 8px; line-height: 1.5; }}

  .table-card {{ background: #2a2a2a; border-radius: 10px; padding: 14px; overflow-x: auto; box-shadow: 0 4px 20px rgba(0,0,0,0.35); }}
  table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
  th, td {{ padding: 6px 10px; text-align: right; white-space: nowrap; }}
  th:first-child, td:first-child {{ text-align: left; }}
  th {{ color: #aaa; font-weight: 500; border-bottom: 1px solid #444; }}
  tbody tr:nth-child(odd) {{ background: #252525; }}
  tbody tr:hover {{ background: #303a45; }}
  td.fname {{ text-align: left; color: #ccc; max-width: 280px; overflow: hidden; text-overflow: ellipsis; }}
  td.warn {{ color: #ff8888; }}
</style>
</head>
<body>
<h1>SVG Dataset Statistics</h1>
<div class="wrap">
  <div class="summary-grid">{summary_html}</div>
  <div id="flags" class="{flags_class.strip()}">{flags_html}</div>
  <div class="charts-grid">{charts_html}</div>
  <div class="table-card">
    <h2>Per-file details (sorted by path count)</h2>
    <table>
      <thead><tr>{table_header}</tr></thead>
      <tbody>{''.join(rows_html)}</tbody>
    </table>
  </div>
</div>
</body>
</html>
'''

    with open(out_path, 'w') as f:
        f.write(html_doc)
    print(f'\nWrote HTML report to: {out_path}')


def main():
    parser = argparse.ArgumentParser(description='Compute statistics over a folder of SVG files.')
    parser.add_argument('folder', help='Folder containing .svg files')
    parser.add_argument('-r', '--recursive', action='store_true', help='Search subfolders recursively')
    parser.add_argument('--csv', help='Write per-file statistics to this CSV path')
    parser.add_argument('--html', help='Write a self-contained HTML report with SVG charts to this path')
    parser.add_argument('--plot', help='Save a histogram grid image to this path (requires matplotlib)')
    parser.add_argument('--bins', type=int, default=10, help='Number of histogram bins (default: 10)')
    parser.add_argument('--top-colors', type=int, default=8, help='Number of top fill colors to show (default: 8)')
    args = parser.parse_args()

    files = list(find_svg_files(args.folder, args.recursive))
    if not files:
        print(f'No .svg files found in {args.folder}')
        return

    results = [analyze_svg(f) for f in files]
    valid = [r for r in results if not r['parse_error'] and r['path_count'] > 0]

    print_summary(results, valid)
    print_flags(results, valid)
    if valid:
        print_histograms(valid, args.bins)
        print_top_colors(valid, args.top_colors)

    if args.csv:
        write_csv(results, args.csv)
    if args.html:
        write_html_report(results, valid, args.html, args.bins, args.top_colors)
    if args.plot:
        save_plot(valid, args.plot, args.bins)


if __name__ == '__main__':
    main()
