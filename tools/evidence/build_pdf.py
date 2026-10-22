import argparse
import json
import textwrap
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch

matplotlib.use("Agg")

INK = "#202020"
MUTED = "#666666"
LINE = "#dedede"
PAPER = "#ffffff"
GOOD = "#356345"
BAD = "#9b4141"


def text(fig, x, y, value, size=10, color=INK, weight="normal", width=None, **kwargs):
    if width:
        value = "\n".join(textwrap.fill(line, width) for line in value.split("\n"))
    return fig.text(
        x,
        y,
        value,
        ha="left",
        va="top",
        fontsize=size,
        color=color,
        weight=weight,
        linespacing=1.5,
        **kwargs,
    )


def line(fig, y, x1=0.08, x2=0.92):
    fig.add_artist(
        plt.Line2D(
            [x1, x2], [y, y], transform=fig.transFigure, color=LINE, linewidth=0.7
        )
    )


def card(fig, x, y, w, h, color="#f6f6f4"):
    fig.add_artist(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.008,rounding_size=0.006",
            facecolor=color,
            edgecolor="none",
            transform=fig.transFigure,
            zorder=-1,
        )
    )


def header(fig, page, title, subtitle):
    fig.patch.set_facecolor(PAPER)
    text(fig, 0.08, 0.955, "SENTINEL", 11, weight="bold")
    text(fig, 0.88, 0.955, f"0{page}", 10, MUTED)
    text(fig, 0.08, 0.911, title, 29, weight="bold")
    text(fig, 0.08, 0.858, subtitle, 9.5, MUTED, width=98)
    line(fig, 0.817)


def footer(fig, data, page):
    line(fig, 0.067)
    text(
        fig,
        0.08,
        0.052,
        f"Recorded synthetic demo · {data['incident']['opened_at'][:10]} · {page}/2",
        8,
        MUTED,
    )
    text(fig, 0.08, 0.034, f"Incident {data['incident']['incident_id']}", 7.5, MUTED)


def make_pdf(data, destination):
    assert data["incident"]["status"] == "resolved"
    assert data["repair"]["status"] == "verified"
    assert len(data["repair"]["recovery_windows"]) == 2
    plt.rcParams.update({"font.family": "DejaVu Sans", "pdf.fonttype": 42})
    metrics = data["metrics"]
    repair = data["repair"]
    source = data["faulty"]
    passing = sum(
        window["evidence"]["passing"] for window in repair["recovery_windows"]
    )
    samples = data["baseline"]["samples"]
    failure = data["contract"]["failure_ratio"] * 100
    after_unit = repair["proposal"]["after"]["event_time_unit"]
    figures = []

    fig = plt.figure(figsize=(8.27, 11.69))
    header(
        fig,
        1,
        "From breach to verified repair",
        "One recorded end-to-end journey, backed by frozen evidence and fresh recovery data.",
    )
    card(fig, 0.08, 0.562, 0.397, 0.214, "#faf3f2")
    card(fig, 0.523, 0.562, 0.397, 0.214, "#f0f5f0")
    text(fig, 0.101, 0.758, f"BEFORE · REVISION {source['revision']}", 9, BAD, "bold")
    text(fig, 0.101, 0.727, source["event_time_unit"].capitalize(), 23, weight="bold")
    text(fig, 0.101, 0.679, "Contract requires milliseconds", 10)
    text(
        fig,
        0.101,
        0.642,
        f"{data['baseline']['accepted']}/{samples} accepted by integer type check",
        10,
    )
    text(
        fig,
        0.101,
        0.608,
        f"{samples}/{samples} violate the recorded contract",
        10,
        BAD,
        "bold",
    )
    text(
        fig,
        0.544,
        0.758,
        f"AFTER · REVISION {repair['recovery_revision']}",
        9,
        GOOD,
        "bold",
    )
    text(fig, 0.544, 0.727, after_unit.capitalize(), 23, weight="bold")
    text(fig, 0.544, 0.679, "Producer configuration repaired through Git", 10)
    text(fig, 0.544, 0.642, f"{passing}/{passing} pass across two recovery windows", 10)
    text(fig, 0.544, 0.608, "Incident resolved after verification", 10, GOOD, "bold")

    text(fig, 0.08, 0.524, "The recorded journey", 15, weight="bold")
    rows = [
        (
            "01",
            "Commit the fault",
            f"Git-backed revision {source['revision']} changes the producer to seconds.",
        ),
        (
            "02",
            "Capture the breach",
            "Freeze the events, contract and configuration history.",
        ),
        (
            "03",
            "Investigate with evidence",
            "The agent reads typed tools and cites the affected revision.",
        ),
        (
            "04",
            "Open and review the repair",
            f"PR #{repair['pr_number']} restores the required unit; an engineer merges it.",
        ),
        (
            "05",
            "Verify fresh data",
            "Two separate ten-second windows pass before resolution.",
        ),
    ]
    for index, (number, title, description) in enumerate(rows):
        y = 0.484 - index * 0.071
        text(fig, 0.08, y, number, 9, MUTED)
        text(fig, 0.125, y, title, 10.5, weight="bold")
        text(fig, 0.125, y - 0.023, description, 9.5, MUTED)
    line(fig, 0.117)
    text(fig, 0.08, 0.102, "Fault commit", 8.5, MUTED)
    commit = source.get("source_commit", "")
    text(
        fig,
        0.205,
        0.102,
        commit[:12],
        9,
        url=f"https://github.com/{repair['repository']}/commit/{commit}",
    )
    text(fig, 0.44, 0.102, "Repair PR", 8.5, MUTED)
    text(
        fig,
        0.55,
        0.102,
        f"github.com/{repair['repository']}/pull/{repair['pr_number']}",
        9,
        url=repair["pr_url"],
    )
    footer(fig, data, 1)
    figures.append(fig)

    fig = plt.figure(figsize=(8.27, 11.69))
    header(
        fig,
        2,
        "Measured evidence",
        "A timestamp type-check baseline, one real investigation, and recovery checked against the contract.",
    )
    text(fig, 0.08, 0.788, "What the comparison shows", 15, weight="bold")
    ax = fig.add_axes([0.08, 0.579, 0.84, 0.18])
    ax.axis("off")
    table = ax.table(
        cellText=[
            [
                "Timestamp type",
                f"{samples}/{samples} accepted",
                "Accepted by ingestion",
            ],
            [
                "Meaning of the value",
                "Not evaluated",
                f"{failure:.0f}% contract failures",
            ],
            [
                "Producer attribution",
                "Not evaluated",
                f"Evidence-linked revision {source['revision']}",
            ],
            [
                "Repair and outcome",
                "Not evaluated",
                f"PR #{repair['pr_number']} + 2 verified windows",
            ],
        ],
        colLabels=["Check", "Integer type baseline", "Sentinel"],
        cellLoc="left",
        colLoc="left",
        colWidths=[0.3, 0.3, 0.4],
        bbox=[0, 0, 1, 1],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    for (row, column), cell in table.get_celld().items():
        cell.set_edgecolor(LINE)
        cell.set_linewidth(0.5)
        cell.PAD = 0.08
        cell.set_facecolor("#f6f6f4" if row == 0 else PAPER)
        if row == 0:
            cell.get_text().set_weight("bold")
    text(fig, 0.08, 0.55, "Recorded timings and usage", 15, weight="bold")
    values = [
        (
            "Detection",
            f"{metrics['detection_seconds']:.1f}s",
            "From faulty revision becoming active",
        ),
        (
            "Investigation",
            f"{metrics['investigation_seconds']:.1f}s",
            f"{metrics['model_requests']} model requests · {metrics['tool_calls']} tool calls",
        ),
        (
            "Reported usage",
            f"{metrics['reported_tokens']:,} tokens",
            data["run"]["model_id"],
        ),
        (
            "Verified recovery",
            f"{metrics['recovery_seconds']:.1f}s",
            "From repaired revision becoming active",
        ),
    ]
    for index, (name, value, note) in enumerate(values):
        y = 0.509 - index * 0.058
        text(fig, 0.08, y, name, 10)
        text(fig, 0.38, y, value, 12, weight="bold")
        text(fig, 0.38, y - 0.024, note, 8.5, MUTED)
    text(fig, 0.08, 0.253, "Data layer and verification", 15, weight="bold")
    text(
        fig,
        0.08,
        0.221,
        "Aiven Kafka carries the events. Aiven PostgreSQL stores contracts, producer revisions, frozen incident evidence, tool activity and recovery records. The agent reads the captured snapshot through typed tools.",
        9.5,
        width=108,
    )
    text(
        fig,
        0.08,
        0.153,
        "Scope: one synthetic end-to-end run, not a production benchmark or an average latency claim. Detection is deterministic; the agent contributes diagnosis and evidence references. The PR adapter constrains the edit. Fresh data establishes recovery.",
        8.8,
        MUTED,
        width=113,
    )
    text(
        fig,
        0.08,
        0.093,
        "Source: deployed application APIs. Screenshot capture requires the separate Playwright exporter.",
        8.2,
        MUTED,
    )
    footer(fig, data, 2)
    figures.append(fig)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(
        destination,
        metadata={
            "Title": "Sentinel — Recorded Evidence",
            "Author": "Sentinel",
            "Subject": "Before/after and measured evidence from a verified Kafka contract incident",
        },
    ) as pdf:
        for index, figure in enumerate(figures, 1):
            pdf.savefig(figure, facecolor=PAPER)
            figure.savefig(
                destination.with_name(f"evidence-page-{index}.png"),
                dpi=140,
                facecolor=PAPER,
            )
            plt.close(figure)
        assert pdf.get_pagecount() == 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    make_pdf(json.loads(args.bundle.read_text()), args.output)
    print(args.output)
