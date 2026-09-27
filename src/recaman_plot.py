import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import Arc
from matplotlib.ticker import FuncFormatter

from recaman import recaman

# 색상 (밝은 배경 기준)
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
TEXT_MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"     # 앞으로(더하기)
ORANGE = "#eb6834"   # 뒤로(빼기)

ARC_TERMS = 60       # 위쪽 그림에 쓸 항 개수


def set_korean_font():
    """설치된 한글 글꼴 중 첫 번째를 사용합니다 (Windows / Mac / Linux)."""
    candidates = ["Malgun Gothic", "AppleGothic", "NanumGothic",
                  "Noto Sans CJK KR", "WenQuanYi Zen Hei"]
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in installed:
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def to_man(x, _pos=None):
    """숫자를 '만' 단위로 읽기 쉽게 바꿉니다. 예) 2000000 -> 200만"""
    if x == 0:
        return "0"
    return f"{x / 10000:,.0f}만"


def style_axes(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(colors=TEXT_MUTED, length=0, labelsize=10)


def draw_arcs(ax, seq):
    """한 번 이동할 때마다 반원 하나: 앞으로 가면 위쪽(파랑), 뒤로 가면 아래쪽(주황)."""
    for k in range(1, len(seq)):
        a, b = seq[k - 1], seq[k]
        forward = b > a
        ax.add_patch(Arc(((a + b) / 2, 0), abs(b - a), abs(b - a),
                         theta1=0 if forward else 180,
                         theta2=180 if forward else 360,
                         color=BLUE if forward else ORANGE,
                         lw=1.6, capstyle="round"))

    top = max(seq) + 2
    radius = (len(seq) - 1) / 2 + 2
    ax.axhline(0, color=BASELINE, lw=1)
    ax.set_xlim(-2, top)
    ax.set_ylim(-radius, radius)
    ax.set_aspect("equal")
    style_axes(ax)
    ax.spines["bottom"].set_visible(False)
    ax.set_yticks([])
    ax.set_xticks(range(0, top, 10))
    ax.set_anchor("W")

    keys = [Line2D([], [], color=BLUE, lw=3, label="앞으로 가기 (더하기) · 위쪽"),
            Line2D([], [], color=ORANGE, lw=3, label="뒤로 가기 (빼기) · 아래쪽")]
    ax.legend(handles=keys, loc="upper left", bbox_to_anchor=(0, 1), ncol=2,
              frameon=False, fontsize=10, labelcolor=TEXT_SECONDARY,
              handlelength=1.5, borderaxespad=0)


def draw_scatter(ax, seq):
    """모든 항을 점 하나씩: 가로 = 몇 번째 항, 세로 = 그 값."""
    n = len(seq)
    ax.scatter(range(n), seq, s=0.6, color=BLUE, alpha=0.6,
               linewidths=0, rasterized=True)

    peak = max(seq)
    peak_at = seq.index(peak)
    ax.scatter([peak_at], [peak], s=60, color=BLUE,
               edgecolors=SURFACE, linewidths=2, zorder=3)
    ax.annotate(f"가장 큰 값 {peak:,}\n({peak_at:,}번째 항)",
                xy=(peak_at, peak), xytext=(-12, -4), textcoords="offset points",
                ha="right", va="top", fontsize=10, color=TEXT_SECONDARY)

    style_axes(ax)
    ax.grid(axis="y", color=GRID, lw=1)
    ax.set_axisbelow(True)
    ax.set_xlim(0, n)
    ax.set_ylim(0, peak * 1.05)
    ax.xaxis.set_major_formatter(FuncFormatter(to_man))
    ax.yaxis.set_major_formatter(FuncFormatter(to_man))
    ax.set_xlabel("몇 번째 항", color=TEXT_MUTED, fontsize=10)


def add_title(ax, title, subtitle):
    ax.set_title(title + "\n", loc="left", fontsize=14, fontweight="bold",
                 color=TEXT_PRIMARY)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes,
            fontsize=10, color=TEXT_SECONDARY)


def main():
    # 사용법: python src/recaman_plot.py [개수] [저장할 그림 파일]
    #   예) python src/recaman_plot.py 1000000 recaman.png
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
    out_path = sys.argv[2] if len(sys.argv) > 2 else "recaman.png"

    set_korean_font()
    seq = recaman(n)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 13),
                                   gridspec_kw={"height_ratios": [1, 1.1]})
    fig.patch.set_facecolor(SURFACE)

    arc_seq = seq[:ARC_TERMS]
    draw_arcs(ax1, arc_seq)
    add_title(ax1, f"① 처음 {len(arc_seq)}개 항: 숫자가 뛰어다니는 길",
              "0에서 출발해 n번째에는 n칸 이동해요. 뒤로 갈 수 없으면 앞으로 가요.")

    draw_scatter(ax2, seq)
    add_title(ax2, f"② {n:,}개 항 전체",
              "점 하나가 항 하나예요 (가로 = 몇 번째 항, 세로 = 값). 여러 갈래 줄을 따라 점점 커져요.")

    fig.tight_layout(h_pad=3)
    fig.savefig(out_path, dpi=150, facecolor=SURFACE)
    print(f"-> {out_path} 에 그래프 저장 완료")


if __name__ == "__main__":
    main()
