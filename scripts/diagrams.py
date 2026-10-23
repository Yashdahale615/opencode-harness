"""Vector diagrams for the harness architecture PDF, drawn with reportlab.graphics
so they scale cleanly and use the same palette as the rest of the document."""
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon
from reportlab.lib import colors
from reportlab.lib.units import inch

INK = colors.HexColor("#1f2937")
BORDER = colors.HexColor("#334155")
ACCENT = colors.HexColor("#2563eb")
ALLOW = colors.HexColor("#15803d")
ASK = colors.HexColor("#b45309")
DENY = colors.HexColor("#b91c1c")
FILL = colors.HexColor("#eef2ff")
FILL2 = colors.HexColor("#f8fafc")


def _box(d, x, y, w, h, text, fill=FILL, stroke=BORDER, fs=8.3, textcolor=INK):
    d.add(Rect(x, y, w, h, fillColor=fill, strokeColor=stroke, strokeWidth=1,
               rx=5, ry=5))
    lines = text.split("\n")
    total_h = len(lines) * (fs + 2)
    ty = y + h / 2 + total_h / 2 - fs
    for ln in lines:
        d.add(String(x + w / 2, ty, ln, fontName="Helvetica", fontSize=fs,
                     fillColor=textcolor, textAnchor="middle"))
        ty -= (fs + 2)


def _arrow(d, x1, y1, x2, y2, color=BORDER, width=1.1):
    d.add(Line(x1, y1, x2, y2, strokeColor=color, strokeWidth=width))
    import math
    ang = math.atan2(y2 - y1, x2 - x1)
    hlen, hw = 6, 3.2
    bx, by = x2 - hlen * math.cos(ang), y2 - hlen * math.sin(ang)
    px, py = -math.sin(ang) * hw, math.cos(ang) * hw
    d.add(Polygon(points=[x2, y2, bx + px, by + py, bx - px, by - py],
                  fillColor=color, strokeColor=color))


def _elbow(d, x1, y1, x2, y2, mid_y, color=BORDER):
    """Vertical from (x1,y1) down to mid_y, across to x2, then arrow down
    into (x2,y2). Used to connect the end of one row to the start of the
    next without any diagonal or overlapping segments."""
    d.add(Line(x1, y1, x1, mid_y, strokeColor=color, strokeWidth=1.1))
    d.add(Line(x1, mid_y, x2, mid_y, strokeColor=color, strokeWidth=1.1))
    _arrow(d, x2, mid_y, x2, y2, color=color)


def pipeline_overview():
    """Top-level pipeline as three left-to-right rows, each row connected
    to the next by a simple elbow connector (down, across, down into the
    next box) so no segment is diagonal or overlaps a box. Coordinates
    use the normal bottom-left origin; the drawing height is computed
    from the content so nothing is clipped or overlaps what follows it
    on the page."""
    bw, bh = 92, 42
    col_gap, row_gap = 16, 32
    side_margin, bottom_margin, top_margin = 6, 6, 6

    row1 = ["USER", "HARNESS\nENTRY", "CONTEXT\nCONTROLLER",
           "MODEL\nCONTROLLER", "ORCHESTRATION\nCONTROLLER"]
    row2 = ["OPENCODE\nAGENT", "PERMISSION\n+ EXECUTION",
           "REAL\nWORKSPACE", "OBSERVABILITY\n/ TRACE"]
    final_label = "SNAPSHOT -> DIFF -> VERIFICATION -> GATE -> RECEIPT"

    w = side_margin * 2 + len(row1) * bw + (len(row1) - 1) * col_gap
    y_row3 = bottom_margin                        # final box, bottom row
    y_row2 = y_row3 + bh + row_gap                # middle row
    y_row1 = y_row2 + bh + row_gap                # top row
    h = y_row1 + bh + top_margin
    d = Drawing(w, h)

    x = side_margin
    row1_x = []
    for i, label in enumerate(row1):
        fill = ACCENT if i == 0 else FILL
        tc = colors.white if i == 0 else INK
        _box(d, x, y_row1, bw, bh, label, fill=fill, textcolor=tc, fs=7.4)
        row1_x.append(x)
        if i < len(row1) - 1:
            _arrow(d, x + bw, y_row1 + bh / 2, x + bw + col_gap,
                  y_row1 + bh / 2)
        x += bw + col_gap
    end_of_row1_x = row1_x[-1] + bw / 2

    x = side_margin
    row2_x = []
    for i, label in enumerate(row2):
        _box(d, x, y_row2, bw, bh, label, fs=7.4)
        row2_x.append(x)
        if i < len(row2) - 1:
            _arrow(d, x + bw, y_row2 + bh / 2, x + bw + col_gap,
                  y_row2 + bh / 2)
        x += bw + col_gap
    start_of_row2_x = row2_x[0] + bw / 2
    end_of_row2_x = row2_x[-1] + bw / 2

    mid1 = y_row1 - row_gap / 2
    _elbow(d, end_of_row1_x, y_row1, start_of_row2_x, y_row2 + bh, mid1)

    final_w = w - 2 * side_margin
    _box(d, side_margin, y_row3, final_w, bh, final_label, fill=FILL2,
        fs=7.6)
    mid2 = y_row2 - row_gap / 2
    _elbow(d, end_of_row2_x, y_row2, side_margin + final_w / 2,
          y_row3 + bh, mid2)
    return d


def permission_flow():
    w = 460
    top_bw, top_bh = 160, 32
    bot_bw, bot_bh = 110, 32
    row_gap = 30
    bottom_margin, top_margin = 6, 6

    y_bottom = bottom_margin
    y_row3 = y_bottom + bot_bh + row_gap          # POLICY RULES
    y_row2 = y_row3 + top_bh + row_gap            # RISK CLASSIFICATION
    y_row1 = y_row2 + top_bh + row_gap            # TOOL REQUEST
    h = y_row1 + top_bh + top_margin
    d = Drawing(w, h)

    cx = w / 2
    _box(d, cx - top_bw / 2, y_row1, top_bw, top_bh, "TOOL REQUEST", fs=8)
    _arrow(d, cx, y_row1, cx, y_row2 + top_bh)
    _box(d, cx - top_bw / 2, y_row2, top_bw, top_bh,
        "RISK CLASSIFICATION", fs=7.6)
    _arrow(d, cx, y_row2, cx, y_row3 + top_bh)
    _box(d, cx - top_bw / 2, y_row3, top_bw, top_bh,
        "POLICY RULES\n(first match wins)", fs=7)

    xs = {"ALLOW": w * 0.14, "ASK": w * 0.5, "DENY\n(default)": w * 0.86}
    stroke = {"ALLOW": ALLOW, "ASK": ASK, "DENY\n(default)": DENY}
    fill = {"ALLOW": colors.HexColor("#dcfce7"),
           "ASK": colors.HexColor("#fef3c7"),
           "DENY\n(default)": colors.HexColor("#fee2e2")}
    for label, x in xs.items():
        bx = x - bot_bw / 2
        _arrow(d, cx, y_row3, x, y_bottom + bot_bh, color=stroke[label])
        _box(d, bx, y_bottom, bot_bw, bot_bh, label, fill=fill[label],
            stroke=stroke[label], textcolor=stroke[label], fs=8)
    return d


def gate_tree():
    """A vertical decision ladder: one question box per row on the main
    (center) column, with a terminal outcome peeling off to the right at
    each row where the answer is already decided. Every row's geometry
    is computed from a fixed row height so nothing overlaps or goes
    negative, however many rows are added."""
    w = 530
    q_bw, q_bh = 210, 34
    out_bw, out_bh = 150, 34
    row_h = 58
    side_margin, bottom_margin, top_margin = 8, 8, 8
    cx = 165                                    # center column x (left-biased)
    out_x = w - side_margin - out_bw

    rows = [
        ("Permission violation\nrecorded?", "BLOCKED\n(permission_violation)",
        colors.HexColor("#fee2e2")),
        ("Run succeeded?", "BLOCKED\n(run_failed)",
        colors.HexColor("#fee2e2")),
        ("Workspace changed?", "ALLOWED\n(no_mutation)",
        colors.HexColor("#dcfce7")),
        ("Applicable trusted\ncheck exists?", "ALLOWED or ASK\n(no_trusted_check)",
        colors.HexColor("#fef3c7")),
        ("Check PASSED?", "BLOCKED or ASK\n(failed / unavailable)",
        colors.HexColor("#fee2e2")),
        ("Reconciled\nunchanged?", "BLOCKED or REVERIFY\n(state changed)",
        colors.HexColor("#fef3c7")),
    ]
    n = len(rows)
    h = top_margin + n * row_h + bottom_margin + q_bh
    d = Drawing(w, h)

    y_top = h - top_margin - q_bh
    ys = [y_top - i * row_h for i in range(n)]

    for i, (question, outcome, fill) in enumerate(rows):
        y = ys[i]
        _box(d, cx - q_bw / 2, y, q_bw, q_bh, question, fs=7.8)
        _box(d, out_x, y, out_bw, out_bh, outcome, fill=fill, fs=6.8)
        _arrow(d, cx + q_bw / 2, y + q_bh / 2, out_x, y + out_bh / 2)
        if i < n - 1:
            _arrow(d, cx, y, cx, ys[i + 1] + q_bh)

    final_bw, final_bh = 180, 40
    final_y = ys[-1] - row_h + (row_h - final_bh) / 2
    _box(d, cx - final_bw / 2, final_y, final_bw, final_bh,
        "ALLOWED_VERIFIED\n(all checks passed)",
        fill=colors.HexColor("#dcfce7"), fs=7.6)
    _arrow(d, cx, ys[-1], cx, final_y + final_bh)
    return d
