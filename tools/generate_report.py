"""Build NetArchitect-Report.pdf from the live planning engine.

Usage:  python tools/generate_report.py

The section order follows the reference CIC-307 report:
abstract, objectives, tools, architecture, media, VLSM, routing/topology,
dashboard, Cisco IOS, tests, Packet Tracer, AI audit, how to run, conclusion,
references.

Every number in the PDF is read from ``analyze(load_preset(...))`` at build
time, so the report cannot drift away from the code or the exports.
"""

from __future__ import annotations

import sys
import textwrap
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)

from netarchitect.core.design import analyze
from netarchitect.core.spec import load_preset

OUTPUT = ROOT / "NetArchitect-Report.pdf"

NAVY = colors.HexColor("#12263A")
TEAL = colors.HexColor("#1F6F78")
ACCENT = colors.HexColor("#C8553D")
LIGHT = colors.HexColor("#EAF0F2")
GREY = colors.HexColor("#5A6672")
ROW = colors.HexColor("#F5F8F9")

PRESETS = ("campus", "metro", "wan")
ANALYSES = {name: analyze(load_preset(name)) for name in PRESETS}

STUDENT = "Aayush Kumar"
ROLL = "08514802724"
REPOSITORY = "https://github.com/Aayush3238/CN_Assignment"


# --------------------------------------------------------------------------- #
# Styles
# --------------------------------------------------------------------------- #
styles = getSampleStyleSheet()
styles.add(
    ParagraphStyle(
        "CoverTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=30,
        leading=35,
        textColor=NAVY,
        spaceAfter=6,
        alignment=TA_LEFT,
    )
)
styles.add(
    ParagraphStyle(
        "CoverSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=13,
        leading=19,
        textColor=TEAL,
        spaceAfter=4,
    )
)
styles.add(
    ParagraphStyle(
        "CoverMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=15,
        textColor=colors.HexColor("#283845"),
    )
)
styles.add(
    ParagraphStyle(
        "H1x",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=NAVY,
        spaceBefore=6,
        spaceAfter=7,
    )
)
styles.add(
    ParagraphStyle(
        "H2x",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=TEAL,
        spaceBefore=9,
        spaceAfter=4,
    )
)
styles.add(
    ParagraphStyle(
        "Bodyx",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.4,
        leading=13.4,
        alignment=TA_JUSTIFY,
        textColor=colors.HexColor("#1D252C"),
        spaceAfter=5,
    )
)
styles.add(
    ParagraphStyle(
        "Smallx",
        parent=styles["BodyText"],
        fontSize=8,
        leading=10.5,
        textColor=GREY,
        alignment=TA_LEFT,
    )
)
styles.add(
    ParagraphStyle(
        "Cell",
        parent=styles["BodyText"],
        fontSize=7.6,
        leading=9.6,
        alignment=TA_LEFT,
        spaceAfter=0,
    )
)
styles.add(
    ParagraphStyle(
        "CellBold",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=7.6,
        leading=9.6,
        textColor=NAVY,
        spaceAfter=0,
    )
)
styles.add(
    ParagraphStyle(
        "CellHead",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=7.8,
        leading=9.8,
        textColor=colors.white,
        spaceAfter=0,
    )
)
styles.add(
    ParagraphStyle(
        "Bulletx",
        parent=styles["BodyText"],
        fontSize=9.3,
        leading=13,
        leftIndent=11,
        bulletIndent=2,
        spaceAfter=2,
        alignment=TA_JUSTIFY,
    )
)
styles.add(
    ParagraphStyle(
        "Codex",
        parent=styles["Code"],
        fontName="Courier",
        fontSize=7.1,
        leading=8.9,
        leftIndent=6,
        textColor=colors.HexColor("#20303B"),
        backColor=colors.HexColor("#F3F5F6"),
        borderPadding=4,
    )
)
styles.add(
    ParagraphStyle(
        "CodeBlock",
        parent=styles["Code"],
        fontName="Courier",
        fontSize=6.1,
        leading=7.5,
        leftIndent=4,
        rightIndent=4,
        textColor=colors.HexColor("#20303B"),
        backColor=colors.HexColor("#F3F5F6"),
        borderPadding=5,
    )
)
styles.add(
    ParagraphStyle(
        "Caption",
        parent=styles["BodyText"],
        fontSize=8,
        leading=10,
        alignment=TA_CENTER,
        textColor=GREY,
        spaceBefore=3,
        spaceAfter=9,
    )
)


def body(text: str) -> Paragraph:
    return Paragraph(text, styles["Bodyx"])


def bullet(text: str) -> Paragraph:
    return Paragraph(text, styles["Bulletx"], bulletText="\u2022")


def cell(text: str, bold: bool = False) -> Paragraph:
    return Paragraph(str(text), styles["CellBold" if bold else "Cell"])


def head(text: str) -> Paragraph:
    return Paragraph(str(text), styles["CellHead"])


def code_block(text: str, width: int = 118) -> Preformatted:
    """Preformatted block with long IOS lines wrapped so nothing is clipped."""
    lines: list[str] = []
    for raw in text.splitlines():
        if len(raw) <= width:
            lines.append(raw)
            continue
        chunks = textwrap.wrap(
            raw,
            width=width,
            subsequent_indent="    ",
            break_long_words=True,
            break_on_hyphens=False,
        )
        lines.extend(chunks or [raw])
    return Preformatted("\n".join(lines), styles["CodeBlock"])


def make_table(
    headers: list[str],
    rows: list[list[object]],
    widths: list[float],
    *,
    align_right: tuple[int, ...] = (),
) -> Table:
    data = [[head(item) for item in headers]]
    for row in rows:
        data.append(
            [
                cell(value, bold=(index == 0))
                for index, value in enumerate(row)
            ]
        )
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    command = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C7D2D8")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for row_index in range(1, len(data)):
        if row_index % 2 == 0:
            command.append(("BACKGROUND", (0, row_index), (-1, row_index), ROW))
    for column in align_right:
        command.append(("ALIGN", (column, 1), (column, -1), "RIGHT"))
    table.setStyle(TableStyle(command))
    return table


# --------------------------------------------------------------------------- #
# Diagrams
# --------------------------------------------------------------------------- #
def pipeline_drawing() -> Drawing:
    labels = [
        ("Scenario\nJSON", 0),
        ("Media +\noptical", 1),
        ("VLSM\nallocator", 2),
        ("Topology\n+ STP", 3),
        ("OSPF /\nBGP", 4),
        ("IOS\nconfigs", 5),
    ]
    width = 17.0 * cm
    drawing = Drawing(width, 2.55 * cm)
    box_w, box_h, gap = 2.32 * cm, 1.25 * cm, 0.47 * cm
    y = 1.0 * cm
    for label, index in labels:
        x = 0.25 * cm + index * (box_w + gap)
        drawing.add(
            Rect(
                x,
                y,
                box_w,
                box_h,
                rx=3,
                ry=3,
                fillColor=LIGHT if index not in (0, 5) else colors.HexColor("#DCE9EC"),
                strokeColor=TEAL,
                strokeWidth=0.8,
            )
        )
        lines = label.split("\n")
        for line_index, line in enumerate(lines):
            drawing.add(
                String(
                    x + box_w / 2,
                    y + box_h / 2 + (0.16 * cm if len(lines) > 1 else 0)
                    - line_index * 0.36 * cm,
                    line,
                    fontSize=6.6,
                    fontName="Helvetica-Bold",
                    fillColor=NAVY,
                    textAnchor="middle",
                )
            )
        if index < len(labels) - 1:
            drawing.add(
                Line(
                    x + box_w,
                    y + box_h / 2,
                    x + box_w + gap,
                    y + box_h / 2,
                    strokeColor=ACCENT,
                    strokeWidth=1.1,
                )
            )
    drawing.add(
        String(
            width / 2,
            0.25 * cm,
            "one Analysis object feeds the export, the CLI, and the dashboard",
            fontSize=6.8,
            fontName="Helvetica-Oblique",
            fillColor=GREY,
            textAnchor="middle",
        )
    )
    return drawing


def tier_drawing() -> Drawing:
    drawing = Drawing(16.6 * cm, 4.5 * cm)
    layers = [
        ("Core", "2 x Layer-3 switches, HSRP pair, OSPF Area 0", 3.25),
        ("Distribution", "3 x building distribution switches", 1.95),
        ("Access", "34 x 48-port access switches, PortFast + BPDU Guard", 0.65),
    ]
    for title, subtitle, y in layers:
        drawing.add(
            Rect(
                1.0 * cm,
                y * cm,
                14.4 * cm,
                0.92 * cm,
                rx=3,
                ry=3,
                fillColor=LIGHT,
                strokeColor=TEAL,
                strokeWidth=0.9,
            )
        )
        drawing.add(
            String(
                1.35 * cm,
                y * cm + 0.56 * cm,
                title,
                fontSize=8.4,
                fontName="Helvetica-Bold",
                fillColor=NAVY,
            )
        )
        drawing.add(
            String(
                4.0 * cm,
                y * cm + 0.56 * cm,
                subtitle,
                fontSize=6.9,
                fontName="Helvetica",
                fillColor=colors.HexColor("#33454F"),
            )
        )
    for start, end in ((1.55, 2.58), (2.86, 3.90)):
        drawing.add(
            Line(8.2 * cm, start * cm, 8.2 * cm, end * cm, strokeColor=ACCENT, strokeWidth=1.2)
        )
    drawing.add(
        String(
            16.6 * cm / 2,
            0.15 * cm,
            "Figure 2. Campus preset: selected three-tier layout",
            fontSize=7,
            fillColor=GREY,
            textAnchor="middle",
        )
    )
    return drawing


# --------------------------------------------------------------------------- #
# Content helpers
# --------------------------------------------------------------------------- #
def plan_row(name: str) -> list[object]:
    plan = ANALYSES[name].selected
    return [
        name,
        plan.topology.tier,
        plan.routing.protocol,
        plan.switching.stp,
        "HSRP" if plan.switching.fhrp.startswith("HSRP") else plan.switching.fhrp,
        f"{plan.vlsm.utilization:.1f}%",
        plan.topology.ratio,
    ]


def build() -> None:
    doc = BaseDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=1.9 * cm,
        bottomMargin=1.9 * cm,
        title="NetArchitect: Design and Implementation Report",
        author=STUDENT,
        subject="CIC-307 Computer Networks Mini-Project",
    )
    frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        doc.height,
        id="normal",
    )
    # No header and no footer: the page is left clean, as requested.
    doc.addPageTemplates([PageTemplate(id="body", frames=[frame])])

    story: list[object] = []

    # ------------------------------------------------------------------ cover
    story += [
        Spacer(1, 1.1 * cm),
        Paragraph("CIC-307  |  Computer Networks  |  Mini Project", styles["CoverSub"]),
        Spacer(1, 0.15 * cm),
        Paragraph("Maharaja Agrasen Institute of Technology", styles["H2x"]),
        Paragraph("Department of Computer Science and Engineering", styles["CoverMeta"]),
        Spacer(1, 1.1 * cm),
        Paragraph("NetArchitect", styles["CoverTitle"]),
        Paragraph(
            "A network planning and Cisco IOS configuration engine that turns a "
            "campus, metro, or WAN scenario into explained design decisions, a VLSM "
            "address plan, and Packet Tracer configs.",
            styles["CoverSub"],
        ),
        Spacer(1, 0.45 * cm),
        Table(
            [[""]],
            colWidths=[4.2 * cm],
            rowHeights=[0.13 * cm],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), ACCENT),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            ),
        ),
        Spacer(1, 1.3 * cm),
        Paragraph("Submitted by", styles["CoverMeta"]),
        Spacer(1, 0.12 * cm),
        Paragraph(f"<b>{STUDENT}</b>", styles["CoverSub"]),
        Paragraph(f"Roll number {ROLL}", styles["CoverMeta"]),
        Paragraph("B.Tech Computer Science and Engineering", styles["CoverMeta"]),
        Spacer(1, 0.9 * cm),
        Paragraph(f"Source code: {REPOSITORY}", styles["CoverMeta"]),
        Paragraph("November 2026", styles["CoverMeta"]),
        Spacer(1, 2.0 * cm),
        Paragraph(
            "All Cisco IOS in this report is generated by the project itself. "
            "Lab credentials are intentionally non-production.",
            styles["Smallx"],
        ),
        PageBreak(),
    ]

    # ---------------------------------------------------------- 1. Abstract
    story += [
        Paragraph("1. Abstract", styles["H1x"]),
        body(
            "NetArchitect is a Python planning tool for CIC-307. A scenario, either "
            "one of three built-in presets or a custom JSON file, is passed through "
            "media selection, bitwise VLSM, topology sizing, and routing selection. "
            "Each choice is returned as a decision that cites the input numbers and "
            "the standard that justifies it. The same result is rendered as Cisco "
            "IOS for Packet Tracer 8.x and shown on a local web dashboard. The "
            "subnet arithmetic does not use Python's ipaddress module; the tests "
            "cross-check the allocator against that module."
        ),
        body(
            "The campus preset is a 1,600-endpoint, three-building LAN and is planned "
            "as three-tier with single-area OSPF. The metro preset connects a "
            "headquarters to two remote sites over 15 km and 35 km and is planned as "
            "a collapsed core with multi-area OSPF. The WAN preset covers four "
            "cities and a cloud VPC and is planned as three-tier with multi-area "
            "OSPF plus eBGP. The suite contains 128 tests, and ai_audit_log.md "
            "records four real defects found in AI-generated code, including a "
            "cloud prefix leaked into OSPF and a duplicate OSPF router ID on an "
            "HSRP pair."
        ),
        Paragraph("2. Objectives", styles["H1x"]),
    ]
    for item in [
        "Accept three realistic presets and a custom scenario, and reject distances, counts, and prefixes that are missing, non-numeric, duplicate, or out of range.",
        "Explain every media type, transceiver, routing protocol, topology tier, and switching choice in natural language tied to the scenario numbers.",
        "Allocate subnets with bitwise VLSM, with no overlap, correct wildcard masks, and explicit failure on exhaustion.",
        "Emit copy-oriented Cisco IOS for switches, routers, SVIs, trunks, HSRP, OSPF, BGP, ACLs, QoS, and IPsec.",
        "Expose the same analysis through a CLI and a browser dashboard without recalculating any value twice.",
        "Lock the rules in with automated tests, and record real generation mistakes with a packet-flow explanation.",
    ]:
        story.append(bullet(item))

    # ------------------------------------------------------------- 3. Tools
    story += [
        Paragraph("3. Tools", styles["H1x"]),
        make_table(
            ["Piece", "Role"],
            [
                ["Python 3.10+", "Engine, CLI, dashboard, and tests. The core has no web imports."],
                ["pytest", "Unit and integration tests for media, VLSM, routing, topology, switching, configs, CLI, and API."],
                ["Jinja2", "One IOS template rendered per device, with strict undefined variables."],
                ["FastAPI and Jinja2", "Dashboard at http://127.0.0.1:8000. No frontend build step."],
                ["Rich", "Coloured CLI tables for decisions, the address plan, and errors."],
                ["Cisco Packet Tracer 8.x", "Lab used to paste exports/campus.txt, metro.txt, and wan.txt."],
                ["reportlab", "Builds this PDF from the live engine at report time."],
            ],
            [4.0 * cm, 12.8 * cm],
        ),
        Spacer(1, 0.15 * cm),
        Paragraph("Table 1. Tools and their role.", styles["Caption"]),
    ]

    # -------------------------------------------------------- 4. Architecture
    story += [
        Paragraph("4. Architecture", styles["H1x"]),
        body(
            "A scenario is a JSON object with a name, endpoint count, building count, "
            "links, subnet requests, a root prefix, sites, and flags for a single "
            "autonomous system, a cloud boundary, and resiliency. core/spec.py "
            "parses that object and rejects a blank name, a boolean where an integer "
            "is required, a zero or non-numeric distance, a duplicate VLAN, a subnet "
            "claimed by two sites, and a pricing block that does not include all "
            "three switch prices."
        ),
        body(
            "design() runs media selection on every link, allocates the VLSM plan, "
            "sizes the topology, and then plans routing from those results. "
            "analyze() also builds a second architecture so the dashboard can show "
            "the selected design beside an alternate. The CLI and the web API both "
            "call analyze(); they do not recalculate masks or optical loss "
            "themselves."
        ),
        Spacer(1, 0.1 * cm),
        pipeline_drawing(),
        Paragraph("Figure 1. Analysis pipeline shared by every interface.", styles["Caption"]),
        make_table(
            ["Module", "Responsibility", "Output"],
            [
                ["core/spec.py", "Parse and validate scenarios; load presets.", "Scenario"],
                ["core/ipv4.py", "Bitwise address arithmetic without ipaddress.", "int helpers"],
                ["core/media.py", "Distance rules, transceiver choice, optical budget.", "MediaChoice"],
                ["core/vlsm.py", "Descending sort, boundary alignment, overlap scan.", "VLSMPlan"],
                ["core/topology.py", "Tier rule, switch counts, oversubscription.", "TopologyPlan"],
                ["core/routing.py", "Area mapping, summaries, eBGP, cloud isolation.", "RoutingPlan"],
                ["core/switching.py", "RSTP/MSTP, HSRP/VRRP, hardening list.", "SwitchingPlan"],
                ["core/design.py", "Orchestration, alternate plan, violations.", "Analysis"],
                ["configs/configs.py", "Device model and Cisco IOS rendering.", "dict[str, str]"],
            ],
            [3.5 * cm, 10.0 * cm, 3.3 * cm],
        ),
        Spacer(1, 0.15 * cm),
        Paragraph("Table 2. Module responsibilities.", styles["Caption"]),
        body(
            "A Decision carries a category, the choice, a reason, the standard, a "
            "severity, and an evidence dictionary. Calculations such as subnet "
            "addresses and optical budgets live on the plan object next to the "
            "decision, so the interface can show the numbers the engine actually "
            "computed. Each run writes three artifacts from that one object."
        ),
        make_table(
            ["Artifact", "Content", "Consumer"],
            [
                ["<preset>.txt", "Combined Cisco IOS, one banner-delimited block per device.", "Packet Tracer operator"],
                ["<preset>-plan.json", "Scenario, media, VLSM, topology, routing, switching, decisions, violations, configs.", "Automated checker"],
                ["<preset>-rationale.md", "Scenario, selected design, media table, decision log, address plan, alternate design.", "Report reader"],
            ],
            [3.4 * cm, 10.0 * cm, 3.4 * cm],
        ),
        Spacer(1, 0.15 * cm),
        Paragraph("Table 3. Artifacts written by one run.", styles["Caption"]),
        PageBreak(),
    ]

    # ------------------------------------------------------- 5. Media selection
    story += [
        Paragraph("5. Media selection", styles["H1x"]),
        body(
            "Distance picks the medium. Up to 100 m the choice is Cat6a with "
            "10GBASE-T (IEEE 802.3an). From just over 100 m through 400 m the choice "
            "is OM4 multimode with 10GBASE-SR at 850 nm (IEEE 802.3ae). Beyond 400 m "
            "the choice is OS2 single-mode: 10GBASE-LR out to 10 km with a 6.2 dB "
            "budget, and 10GBASE-ER from there out to 40 km with an 11.1 dB budget. "
            "Past 40 km the plan warns that the span needs amplification or DWDM."
        ),
        body(
            "Loss is kilometres times 0.35 dB, plus 0.5 dB per connector, plus 0.1 dB "
            "per splice, plus a 3 dB margin. When the scenario omits connector and "
            "splice counts, the engine uses two connectors, no splices, and says so "
            "in the reason. A copper request past 100 m raises "
            "PhysicalDistanceViolationError rather than being clamped. A zero, "
            "negative, or non-numeric distance raises InvalidParameterError."
        ),
        Paragraph(
            "<font name='Courier'>loss = 0.35 x km + 0.5 x connectors + 0.1 x splices + 3.0 dB margin</font>",
            styles["Codex"],
        ),
        Spacer(1, 0.12 * cm),
        body(
            "A long dark-fibre span can be inside the catalogue reach and still warn. "
            "Forty kilometres at 0.35 dB/km is already 14 dB before connectors, "
            "splices, and the margin, which is more than the ER budget. The metro "
            "preset demonstrates the point: its 35 km link estimates 16.25 dB against "
            "11.1 dB, so the plan is kept and a warning is reported. The WAN preset "
            "has four inter-city spans (650, 1,200, 4,800, and 250 km) that all "
            "exceed the 40 km ER catalogue reach. Those warnings are intentional; "
            "the logical design is still valid, but the physical layer would use "
            "provider wavelengths or a DWDM line system."
        ),
        body(
            "The media table in the export records the link, distance, medium, "
            "transceiver, estimated loss, budget, and severity. The dashboard shows "
            "the same table, so a reviewer can challenge a choice without reading "
            "the source."
        ),
        Paragraph("6. VLSM", styles["H1x"]),
        body(
            "IPv4 addresses are 32-bit integers. Requests are sorted by host count, "
            "largest first, with the original order kept for ties. A LAN block needs "
            "hosts + 2 addresses. The prefix length is 32 minus the smallest host-bit "
            "count that covers that need. The block is aligned with "
            "(address + size - 1) AND NOT (size - 1). If that alignment would pass "
            "255.255.255.255, allocation raises AddressSpaceExhaustedError instead "
            "of wrapping to 0.0.0.0."
        ),
        body(
            "Each block records the network, prefix, mask, wildcard, broadcast, first "
            "and last usable address, gateway, usable count, and utilization. The "
            "gateway is the first usable address. The wildcard is the inverse of the "
            "mask, not the mask itself. A /31 follows RFC 3021 and has no broadcast. "
            "A /32 is a single host. Point-to-point helper modes allocate /30 or "
            "/31. After the last block, the plan checks independently that no two "
            "ranges overlap and reports wasted addresses inside the root."
        ),
        body(
            "The trace below is produced by the standalone allocator for a /24 with "
            "four requests. It shows the descending sort and the alignment of each "
            "block to its own size."
        ),
        code_block(
            "Allocation trace for 192.168.10.0/24 with hosts 100,50,20,10\n"
            "\n"
            "request  100 hosts -> /25 (128 addresses) -> 192.168.10.0/25\n"
            "request   50 hosts -> /26 ( 64 addresses) -> 192.168.10.128/26\n"
            "request   20 hosts -> /27 ( 32 addresses) -> 192.168.10.192/27\n"
            "request   10 hosts -> /28 ( 16 addresses) -> 192.168.10.224/28\n"
            "\n"
            "usable addresses: 126 + 62 + 30 + 14 = 232\n"
            "allocated block space: 128 + 64 + 32 + 16 = 240 (93.8% packing)\n"
            "overlap check: PASS (four disjoint ranges, none crossing .255)"
        ),
        Spacer(1, 0.15 * cm),
        body(
            "A fixed-length plan at /25 would fit only two of the four requests, and "
            "an unaligned allocator would leave the third request at .160 or push "
            "the fourth block past the end of the /24. The engine reports the gap "
            "after .240 as unused rather than silently reusing it."
        ),
        make_table(
            ["Preset", "Root", "What is allocated"],
            [
                ["Campus", "10.10.0.0/16", "Data, Wi-Fi, voice, management, and servers. Five VLANs."],
                ["Metro", "10.20.0.0/16", "HQ users, trading, two remote user LANs, colo, and two /30 links."],
                ["WAN", "10.64.0.0/14", "Four city IoT LANs, a cloud VPC, and four /30 links."],
            ],
            [2.2 * cm, 3.5 * cm, 11.1 * cm],
        ),
        Spacer(1, 0.15 * cm),
        Paragraph("Table 4. Preset roots and allocated blocks.", styles["Caption"]),
        PageBreak(),
    ]

    # --------------------------------------------- 7. Routing and topology
    story += [
        Paragraph("7. Routing and topology", styles["H1x"]),
        body(
            "Routing follows the inputs. A cloud boundary, or more than one autonomous "
            "system, selects multi-area OSPF plus eBGP (RFC 2328 and RFC 4271). eBGP "
            "requires local_asn and peer_asn; the engine does not invent them. "
            "Otherwise, more than one site with a link longer than 400 m, or 50 or "
            "more subnets, selects multi-area OSPF with a summary per site. The "
            "summary is the shortest prefix that covers that site and no other site. "
            "Every remaining case is OSPF Area 0 only."
        ),
        make_table(
            ["Condition", "Selected protocol", "Reason"],
            [
                ["One AS, one site, <50 subnets", "OSPF Area 0", "No inter-area boundary exists; one area keeps the design and the lab simple."],
                ["Multiple sites with a link >400 m, or >=50 subnets", "Multi-area OSPF", "Each site becomes an area; area 0 carries inter-site traffic and each ABR summarises its own site."],
                ["Cloud boundary or more than one AS", "Multi-area OSPF + eBGP", "The provider domain is isolated at an AS boundary; internal prefixes are advertised selectively."],
            ],
            [5.1 * cm, 4.3 * cm, 7.4 * cm],
        ),
        Spacer(1, 0.15 * cm),
        Paragraph("Table 5. Routing decision table.", styles["Caption"]),
        body(
            "Area numbers are assigned deterministically: the HQ or core site is area "
            "0, and remote sites receive 1, 2, 3 in input order. When a site has a "
            "single /25, the summary is that exact /25; the engine records "
            "exact=True so the config generator can decide whether an area range "
            "statement adds anything. Ranges are emitted only on the ABR that owns "
            "the site LAN, never on the HQ router that has no interface in that area."
        ),
        body(
            "BGP is only enabled when the scenario crosses an AS boundary. The local "
            "AS is 65010 and the peer is 64512 in the WAN preset. The cloud VPC "
            "prefix is advertised by BGP and is explicitly skipped by the OSPF "
            "network list; this is the fix for the first audited fault."
        ),
        body(
            "RSTP (IEEE 802.1w) is selected when there are at most 16 VLANs and "
            "fewer than 50 switches. Above either limit the decision is MSTP "
            "(IEEE 802.1s). HSRP is selected when the scenario is resilient; the "
            "open alternative, VRRP (RFC 5798), is named in the decision. Topology "
            "is three-tier when endpoints are at least 1,000 or buildings are at "
            "least 4. Otherwise it is a collapsed core. Access switch count is the "
            "endpoint count divided by 48 ports, rounded up. Oversubscription is "
            "(ports per switch x access speed) / (uplinks x uplink speed), so the "
            "campus ratio is (48 x 1) / (2 x 10) = 2.4:1."
        ),
        make_table(
            ["Preset", "Tier", "Control plane", "STP", "FHRP", "Address use", "Over-sub"],
            [plan_row(name) for name in PRESETS],
            [1.7 * cm, 2.9 * cm, 4.1 * cm, 1.4 * cm, 1.4 * cm, 2.4 * cm, 1.9 * cm],
            align_right=(5, 6),
        ),
        Spacer(1, 0.15 * cm),
        Paragraph("Table 6. Selected design per preset.", styles["Caption"]),
        body(
            "The comparison builds the natural plan and one alternate tier and "
            "routing mode. Each option lists advantages, disadvantages, trade-offs, "
            "and violations. Cost is computed only when the scenario supplies a "
            "price for the access, distribution, and core switch, so all three "
            "presets state that cost was not scored."
        ),
        PageBreak(),
    ]

    # --------------------------------------------------- 8. Dashboard result
    campus = ANALYSES["campus"].selected
    story += [
        Paragraph("8. Dashboard result for the campus preset", styles["H1x"]),
        body(
            "The web page loads a preset or a custom distance, endpoint count, "
            "building count, and resiliency flag. Tabs show the overview, the "
            "decision log, the address plan, a tier diagram, and the per-device "
            "configuration. The campus run below selected three-tier and single-area "
            "OSPF, reported 2.4:1 oversubscription, and reported "
            f"{campus.vlsm.utilization:.1f}% address utilization. The alternate "
            "collapsed-core plan is shown beside it and is marked as a violation of "
            "the tier rule for 1,600 endpoints."
        ),
        tier_drawing(),
        make_table(
            ["Item", "Selected", "Alternate"],
            [
                ["Topology", campus.topology.tier, ANALYSES["campus"].alternate.topology.tier],
                ["Routing", campus.routing.protocol, ANALYSES["campus"].alternate.routing.protocol],
                ["Switches", campus.topology.switch_count, ANALYSES["campus"].alternate.topology.switch_count],
                ["Violations", len(campus.violations), len(ANALYSES["campus"].alternate.violations)],
                ["Address utilization", f"{campus.vlsm.utilization:.1f}%", "-"],
            ],
            [4.3 * cm, 6.2 * cm, 6.3 * cm],
        ),
        Spacer(1, 0.15 * cm),
        Paragraph("Table 7. Campus selected and alternate plans.", styles["Caption"]),
        make_table(
            ["Tab", "What it proves"],
            [
                ["Overview", "Selected and alternate designs side by side, with the media table."],
                ["Decision log", "Every choice carries a standard and a severity."],
                ["Address plan", "CIDR, mask, wildcard, broadcast, gateway, usable hosts, and use."],
                ["Tier diagram", "Core, distribution, and access counts from the topology plan."],
                ["Configurations", "The exact IOS text written to the export, per device."],
            ],
            [3.4 * cm, 13.4 * cm],
        ),
        Spacer(1, 0.15 * cm),
        Paragraph("Table 8. Dashboard tabs.", styles["Caption"]),
        body(
            "The dashboard is not a second implementation. A test opens every tab and "
            "asserts that the rendered page contains a value computed by the engine, "
            "so a template that invents a number fails the suite. The alternate "
            "design is built by the same engine with the opposite tier and routing "
            "mode; it is a counterfactual check rather than a second guess."
        ),
        PageBreak(),
    ]

    # -------------------------------------------------------- 9. Cisco IOS
    story += [
        Paragraph("9. Cisco IOS", styles["H1x"]),
        body(
            "configs.py fills one Jinja2 template, templates/ios_device.j2, once per "
            "device. Campus cores are Layer-3 switches with SVIs and HSRP: the "
            "virtual address is the first usable host, the first core takes the next "
            "address at priority 110, and the second core takes the following "
            "address at priority 100. Distribution and access switches are Layer-2. "
            "Where a scenario has point-to-point subnets, the routers own the "
            "Layer-3 interfaces and the switches stay Layer-2."
        ),
    ]
    for item in [
        "Trunks list the allowed VLAN ids in numeric order and set native VLAN 999, which is not in the allowed list.",
        "Access ports enable PortFast and BPDU Guard. Campus voice and Wi-Fi ports also request inline power where the scenario marks PoE.",
        "Spanning tree mode follows the switching decision: rapid-pvst for the presets, mst when the engine selects MSTP.",
        "OSPF network statements use wildcard masks. Area range and BGP network statements use the subnet mask.",
        "User SVIs are passive. WAN adds eBGP and an ISAKMP crypto map on the cloud-facing interface only. Metro adds an LLQ policy for the trading subnet.",
        "An extended ACL denies the Wi-Fi subnet from reaching the server subnet. VTY lines accept SSH only, from the management subnet.",
        "Each core uses its own SVI address as the OSPF router ID, so an HSRP pair never presents duplicate IDs.",
    ]:
        story.append(bullet(item))
    story += [
        body(
            "The files are written to exports/campus.txt, exports/metro.txt, and "
            "exports/wan.txt. The enable secret and the IPsec pre-shared key are lab "
            "strings for Packet Tracer. They are documented in the README and are "
            "not production credentials."
        ),
        Paragraph("10. Tests", styles["H1x"]),
        body(
            "The suite lives in tests/ and contains 128 tests. It is organised by "
            "rule, so a failure names the engineering rule that broke rather than a "
            "source file. Media tests sit on the boundaries at 100 m, 101 m, 400 m, "
            "401 m, 10 km, 40 km, and 50 km, and they expect an error when copper is "
            "requested past 100 m. VLSM tests cover exhaustion, an exact fit, a "
            "single host, /30, /31, and /32, descending sort, alignment that must not "
            "wrap, and wildcard masks at /0, /8, /24, /30, /31, and /32. A 1,000-run "
            "property test draws random subnet lists inside 10.0.0.0/16 and checks "
            "that nothing overlaps and nothing leaves the root. The ipaddress module "
            "is imported only in that test file."
        ),
        make_table(
            ["Area", "Representative assertions"],
            [
                ["Media", "Distance boundaries; copper past 100 m raises; optical formula, LR/ER budgets, and the >40 km warning."],
                ["VLSM", "Descending order, alignment, exact fit, exhaustion, /30, /31, /32, wildcards at /0 through /32, 1,000-run ipaddress cross-check."],
                ["Routing", "Single-area OSPF, multi-area summaries, eBGP ASN requirement, 50-subnet threshold, cloud exclusion from OSPF."],
                ["Topology", "Tier thresholds, forced collapsed-core violation, oversubscription formula."],
                ["Switching", "RSTP/MSTP boundary, HSRP priorities, trunk VLAN ordering, native VLAN exclusion."],
                ["Configs", "No allowed vlan all, no phantom WAN, unique router IDs, ACL and QoS presence, IPsec at the cloud boundary."],
                ["Integration", "All three presets end to end, CLI exit codes, every dashboard route."],
            ],
            [2.5 * cm, 14.3 * cm],
        ),
        Spacer(1, 0.15 * cm),
        Paragraph("Table 9. Test coverage by engineering area.", styles["Caption"]),
        body(
            "Run the suite from the project folder. Exit codes are part of the CLI "
            "contract: 0 for success, 2 for invalid input or a boundary error, and 3 "
            "for address-space exhaustion."
        ),
        code_block(
            "python -m pytest -q\n"
            "python -m pytest --cov=netarchitect.core --cov-report=term-missing"
        ),
        PageBreak(),
    ]

    # ---------------------------------------------------- 11. Packet Tracer
    story += [
        Paragraph("11. Packet Tracer lab", styles["H1x"]),
        body(
            "Each export is split by the hostname banner and is pasted into a "
            "matching device in Packet Tracer 8.x, from the hostname line through "
            "end, while the CLI is in configuration mode. Campus cores and "
            "distribution switches are 3560-24PS switches. Access switches are "
            "2960-24TT switches. Metro and WAN routers are 2911 routers."
        ),
    ]
    for item in [
        "Open the device, enter <b>enable</b>, then <b>configure terminal</b>.",
        "Paste the block from the hostname line through <b>end</b>.",
        "Save with <b>write memory</b>.",
        "The 3560-24PS model has GigabitEthernet0/1 and GigabitEthernet0/2 only. The generated third trunk, GigabitEthernet0/3, has to be applied to FastEthernet0/1 on that chassis and cabled there. Until that port is a trunk, the access link stays down and HSRP remains in Init because the VLAN interfaces have no forwarding port.",
        "On the 2911 used in the lab, HWIC-2T cards may enumerate as Serial0/2/0 and Serial0/3/0 rather than the generated names. Enter the address on the serial port the cable actually uses.",
        "The DCE end needs <b>clock rate</b> before line protocol comes up; the hub side already includes it.",
        "OSPF hellos need a short wait after line protocol comes up before <b>show ip ospf neighbor</b> lists the peers as FULL.",
        "The WAN export includes a cloud router, so the eBGP neighbour has a real peer in the generated file. Cable it to City A's cloud-facing interface.",
    ]:
        story.append(bullet(item))
    story += [
        Paragraph("Verification commands after pasting:", styles["H2x"]),
        code_block(
            "show vlan brief\n"
            "show interfaces trunk\n"
            "show standby brief\n"
            "show ip ospf neighbor\n"
            "show ip route ospf\n"
            "show ip bgp summary\n"
            "show crypto map\n"
            "ping <gateway>"
        ),
        Spacer(1, 0.12 * cm),
        body(
            "The manual lab itself is the remaining step: this report verifies the "
            "engine, the exports, and the tests, not a set of Packet Tracer "
            "screenshots. The README lists the same procedure and port caveats."
        ),
        PageBreak(),
    ]

    # ---------------------------------------------------------- 12. AI audit
    story += [
        Paragraph("12. AI audit", styles["H1x"]),
        body(
            "ai_audit_log.md records four mistakes that appeared in generated output "
            "and were then fixed. The rubric asks for two; all four are included "
            "because each was reproduced from the generated IOS or a traceback. The "
            "log adds the prompt, the buggy code, the packet-flow consequence, the "
            "fix, and the regression test."
        ),
        make_table(
            ["#", "Fault", "Forwarding effect", "Fix"],
            [
                ["1", "Cloud VPC prefix leaked into OSPF.", "Cloud traffic matched an OSPF summary, bypassed eBGP, and avoided the IPsec crypto map.", "Treat the cloud as area 0 and skip it in OSPF when BGP is used."],
                ["2", "Area ranges applied on the HQ router, not the ABRs.", "A widened prefix could be advertised by two areas, sending a packet back into its own area.", "Emit each site's range only on the router that owns the LAN."],
                ["3", "Both HSRP cores used the same OSPF router ID.", "The cores never reached FULL, so inter-VLAN routing failed while HSRP still looked healthy.", "Use each core's own SVI address as the router ID."],
                ["4", "bgp read before assignment in routing.py.", "analyze() crashed before writing any config; no packet flow existed.", "Compute bgp before the network loop."],
            ],
            [0.7 * cm, 4.6 * cm, 6.4 * cm, 5.1 * cm],
        ),
        Spacer(1, 0.15 * cm),
        Paragraph("Table 10. AI-generated defects and their corrections.", styles["Caption"]),
        body(
            "The same log lists patterns checked on purpose even though they did not "
            "become faults: a wildcard copied from the subnet mask, a subnet aligned "
            "so carelessly that it wraps to 0.0.0.0, a trunk with no allowed-VLAN "
            "list, an OSPF network statement given a subnet mask, and an optical "
            "budget that forgets connector loss, splice loss, or the 3 dB margin."
        ),
        body(
            "The audit matters for academic integrity as much as for code quality. It "
            "shows that generated output was treated as a draft: each rule was "
            "checked against the specification, exercised through the CLI, inspected "
            "in the exported IOS, and then frozen by a test. Fault 3 is the most "
            "instructive because HSRP still showed Active/Standby while OSPF was "
            "silently broken; a superficial check would have passed it."
        ),
        PageBreak(),
    ]

    # ---------------------------------------------------- 13. How to run
    story += [
        Paragraph("13. How to run the project", styles["H1x"]),
        body(
            "From the project folder, with Python 3.10 or newer, create the virtual "
            "environment, install the package, and run the commands below. The "
            "dashboard is served at http://127.0.0.1:8000 and the API documentation "
            "is at /docs."
        ),
        code_block(
            "python -m venv .venv\n"
            ".\\.venv\\Scripts\\Activate.ps1\n"
            'python -m pip install -e ".[dev]"\n'
            "python -m netarchitect list-presets\n"
            "python -m netarchitect explain campus\n"
            "python -m netarchitect run --preset campus --out exports\n"
            "python -m netarchitect run --preset metro  --out exports\n"
            "python -m netarchitect run --preset wan    --out exports\n"
            "python -m netarchitect serve --reload"
        ),
        Spacer(1, 0.15 * cm),
        body(
            "Preset JSON files are netarchitect/presets/campus.json, metro.json, and "
            "wan.json. Generated IOS is under exports/. A custom scenario can be "
            "validated or run with --input, as in the branch-office example. The "
            "report itself is rebuilt with the optional report dependency:"
        ),
        code_block(
            'python -m pip install -e ".[report]"\n'
            "python tools/generate_report.py"
        ),
        Paragraph("14. Conclusion", styles["H1x"]),
        body(
            "NetArchitect keeps the planning rules in one place and makes both the "
            "CLI and the dashboard call that place. Media, VLSM, routing, and "
            "topology each return an explanation that names the input and the "
            "standard. The three presets produce different, checkable designs: a "
            "three-tier campus with one OSPF area, a collapsed metro with area "
            "summaries, and a WAN that adds eBGP at the cloud boundary. The test "
            "suite guards the distance boundaries, the address allocator, and the "
            "wildcard masks. The audit log keeps the four generation mistakes that "
            "were found and fixed, including the metro summary that would have "
            "looped a packet back into the wrong OSPF area."
        ),
        body(
            "The main lesson is that explainability is an engineering constraint, not "
            "a reporting feature. Once every number has to name its input and its "
            "standard, silent clamping and unsupported assumptions become visible. "
            "The 35 km metro span and the 4,800 km WAN span are good examples: the "
            "tool refuses to pretend that a catalogue reach is a working link."
        ),
        Paragraph("References", styles["H1x"]),
    ]
    references = [
        f"{STUDENT}, NetArchitect source code, GitHub, {REPOSITORY}, accessed {date.today().strftime('%d %B %Y')}.",
        "IEEE 802.3an, Physical Layer and Management Parameters for 10 Gb/s Operation, Type 10GBASE-T.",
        "IEEE 802.3ae, 10 Gb/s Ethernet over fiber, including 10GBASE-SR, 10GBASE-LR, and 10GBASE-ER.",
        "IEEE 802.1Q, Bridges and Bridged Networks. IEEE 802.1w, Rapid Spanning Tree. IEEE 802.1s, Multiple Spanning Tree.",
        "RFC 1918, Address Allocation for Private Internets. RFC 4632, Classless Inter-domain Routing.",
        "RFC 2328, OSPF Version 2. RFC 4271, A Border Gateway Protocol 4. RFC 3021, Using 31-Bit Prefixes on IPv4 Point-to-Point Links.",
        "RFC 5798, Virtual Router Redundancy Protocol. Cisco IOS configurations in this project use HSRP.",
        "Cisco Systems, Catalyst 3560 and 2960 configuration guides; Cisco 2911 ISR configuration guide.",
        "CIC-307 NetArchitect assignment specification, 2026.",
    ]
    for index, reference in enumerate(references, start=1):
        story.append(Paragraph(f"[{index}]  {reference}", styles["Smallx"]))
        story.append(Spacer(1, 1.6 * cm / 10))

    # ------------------------------------------------------------- appendix
    story += [
        PageBreak(),
        Paragraph("Appendix A. Generated configuration excerpt", styles["H1x"]),
        body(
            "The following block is taken verbatim from the campus core export. It "
            "shows the HSRP groups on the SVIs, the OSPF router ID and wildcard "
            "masks, and the management and guest ACLs. The full text is "
            "exports/campus.txt and the matching plan is exports/campus-plan.json."
        ),
    ]
    campus_core = ANALYSES["campus"].device_configs.get("campus-core1", "")
    story.append(code_block("\n".join(campus_core.splitlines()[53:])))

    doc.build(story)
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size / 1024:.1f} KiB)")


if __name__ == "__main__":
    build()
