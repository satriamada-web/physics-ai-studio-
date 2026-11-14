"""PDF reporting utilities for Physics AI Studio Heat Transfer."""
from io import BytesIO

import numpy as np
from physics.heat_transfer import calculate_heat_flux
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Flowable, KeepTogether
)


def _thermal_color(value, vmin, vmax):
    """Map a normalized temperature to a dark-purple/red/orange/yellow scale."""
    ratio = 0.5 if vmax <= vmin else max(0.0, min(1.0, (value - vmin) / (vmax - vmin)))
    stops = [
        (0.00, (0.05, 0.00, 0.12)),
        (0.25, (0.30, 0.05, 0.45)),
        (0.50, (0.72, 0.08, 0.22)),
        (0.75, (0.95, 0.36, 0.06)),
        (1.00, (1.00, 0.91, 0.35)),
    ]
    for idx in range(len(stops) - 1):
        p0, c0 = stops[idx]
        p1, c1 = stops[idx + 1]
        if ratio <= p1:
            f = (ratio - p0) / (p1 - p0)
            return colors.Color(*(c0[j] + f * (c1[j] - c0[j]) for j in range(3)))
    return colors.Color(1.0, 0.91, 0.35)


class HeatmapFlowable(Flowable):
    def __init__(self, matrix, width=165 * mm, height=78 * mm):
        super().__init__()
        self.matrix = np.asarray(matrix, dtype=float)
        self.width = width
        self.height = height

    def wrap(self, avail_width, avail_height):
        return min(self.width, avail_width), self.height

    def draw(self):
        rows, cols = self.matrix.shape
        vmin, vmax = float(np.min(self.matrix)), float(np.max(self.matrix))
        cw, ch = self.width / cols, self.height / rows
        for r in range(rows):
            for c in range(cols):
                value = self.matrix[rows - 1 - r, c]
                self.canv.setFillColor(_thermal_color(value, vmin, vmax))
                self.canv.setStrokeColor(_thermal_color(value, vmin, vmax))
                self.canv.rect(c * cw, r * ch, cw + 0.15, ch + 0.15, fill=1, stroke=0)
        self.canv.setStrokeColor(colors.grey)
        self.canv.rect(0, 0, self.width, self.height, fill=0, stroke=1)


class ProfileFlowable(Flowable):
    def __init__(self, x_values, temperatures, width=165 * mm, height=55 * mm):
        super().__init__()
        self.x_values = np.asarray(x_values, dtype=float)
        self.temperatures = np.asarray(temperatures, dtype=float)
        self.width = width
        self.height = height

    def wrap(self, avail_width, avail_height):
        return min(self.width, avail_width), self.height

    def draw(self):
        left, right, bottom, top = 28, self.width - 8, 18, self.height - 8
        xmin, xmax = float(self.x_values.min()), float(self.x_values.max())
        ymin, ymax = float(self.temperatures.min()), float(self.temperatures.max())
        if xmax == xmin:
            xmax = xmin + 1
        if ymax == ymin:
            ymin, ymax = ymin - 1, ymax + 1
        self.canv.setStrokeColor(colors.grey)
        self.canv.setLineWidth(0.6)
        self.canv.line(left, bottom, left, top)
        self.canv.line(left, bottom, right, bottom)
        self.canv.setFont("Helvetica", 7)
        self.canv.drawString(0, top - 2, f"{ymax:.2f} C")
        self.canv.drawString(0, bottom - 2, f"{ymin:.2f} C")
        self.canv.drawCentredString((left + right) / 2, 3, "Position X (m)")
        points = []
        for xv, tv in zip(self.x_values, self.temperatures):
            px = left + (xv - xmin) / (xmax - xmin) * (right - left)
            py = bottom + (tv - ymin) / (ymax - ymin) * (top - bottom)
            points.append((px, py))
        self.canv.setStrokeColor(colors.HexColor("#D65A31"))
        self.canv.setLineWidth(1.6)
        for a, b in zip(points[:-1], points[1:]):
            self.canv.line(a[0], a[1], b[0], b[1])
        self.canv.setFillColor(colors.HexColor("#D65A31"))
        for px, py in points:
            self.canv.circle(px, py, 1.5, fill=1, stroke=0)


def build_heat_transfer_pdf(data):
    """Create a downloadable A4 PDF report from the app's last_result payload."""
    T = np.asarray(data["T"], dtype=float)
    x = np.asarray(data["x"], dtype=float)
    y = np.asarray(data["y"], dtype=float)
    p = data["p"]
    boundary = p["boundary"]
    _, _, heat_flux = calculate_heat_flux(T, p["k"], p["lx"], p["ly"])

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=20 * mm, leftMargin=20 * mm,
        topMargin=19 * mm, bottomMargin=18 * mm,
        title="Heat Transfer Simulation Report",
        author="Physics AI Studio",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=19, leading=23, alignment=TA_CENTER, textColor=colors.HexColor("#17324D"),
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="SubTitle", parent=styles["Normal"], alignment=TA_CENTER,
        fontSize=9, textColor=colors.HexColor("#607080"), spaceAfter=15,
    ))
    styles.add(ParagraphStyle(
        name="Section", parent=styles["Heading2"], fontSize=12, leading=15,
        textColor=colors.HexColor("#17324D"), spaceBefore=10, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="SmallNote", parent=styles["Normal"], fontSize=8, leading=11,
        textColor=colors.HexColor("#555555"),
    ))

    story = [
        Paragraph("PHYSICS AI STUDIO", styles["ReportTitle"]),
        Paragraph("HEAT TRANSFER SIMULATION REPORT · MVP 1.0", styles["SubTitle"]),
        Paragraph("1. Simulation Overview", styles["Section"]),
        Paragraph(
            f"<b>Simulation mode:</b> {data['mode']}<br/>"
            f"<b>Solver status:</b> {data['info']}<br/>"
            f"<b>Numerical note:</b> {data['extra']}",
            styles["BodyText"],
        ),
        Paragraph("2. Geometry &amp; Mesh", styles["Section"]),
    ]

    def add_table(rows, widths=None):
        table = Table(rows, colWidths=widths, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF3")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#17324D")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CAD3DC")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return table

    story.append(add_table([
        ["Parameter", "Value"],
        ["Domain length X", f"{p['lx']:.5g} m"],
        ["Domain length Y", f"{p['ly']:.5g} m"],
        ["Grid", f"{p['nx']} × {p['ny']} nodes"],
        ["Grid spacing dx", f"{x[1]-x[0]:.5g} m"],
        ["Grid spacing dy", f"{y[1]-y[0]:.5g} m"],
    ], [70 * mm, 90 * mm]))

    story.extend([
        Paragraph("3. Material Properties", styles["Section"]),
        add_table([
            ["Property", "Value"],
            ["Material", p.get("material_name", "Custom")],
            ["Thermal conductivity, k", f"{p['k']:.5g} W/(m·K)"],
            ["Density, rho", f"{p['rho']:.5g} kg/m³"],
            ["Specific heat, cp", f"{p['cp']:.5g} J/(kg·K)"],
            ["Thermal diffusivity, alpha", f"{p['k']/(p['rho']*p['cp']):.5e} m²/s"],
            ["Volumetric heat generation", f"{p['q']:.5g} W/m³"],
            ["Initial temperature", f"{p['initial']:.5g} °C"],
        ], [70 * mm, 90 * mm]),
        Paragraph("4. Boundary Conditions", styles["Section"]),
        add_table([
            ["Boundary", "Temperature"],
            ["Left", f"{boundary['left']:.4g} °C"],
            ["Right", f"{boundary['right']:.4g} °C"],
            ["Top", f"{boundary['top']:.4g} °C"],
            ["Bottom", f"{boundary['bottom']:.4g} °C"],
        ], [70 * mm, 90 * mm]),
        Paragraph("5. Numerical Method", styles["Section"]),
        Paragraph(
            "The model solves the two-dimensional heat conduction equation on a "
            "uniform Cartesian grid using a finite-difference method. Steady-state "
            "mode uses Jacobi iteration; transient mode uses an explicit time-marching "
            "scheme. Transient stability is constrained by the explicit diffusion "
            "time-step limit.",
            styles["BodyText"],
        ),
        Paragraph("6. Temperature Distribution", styles["Section"]),
        HeatmapFlowable(T),
        Spacer(1, 4),
        Paragraph(
            f"Temperature field on a {p['nx']} × {p['ny']} grid. "
            f"Domain: {p['lx']:.4g} m × {p['ly']:.4g} m.",
            styles["SmallNote"],
        ),
        Paragraph("7. Centerline Temperature Profile", styles["Section"]),
        ProfileFlowable(x, T[len(y) // 2, :]),
        Paragraph("8. Heat Flux Analysis", styles["Section"]),
        add_table([
            ["Metric", "Result"],
            ["Maximum heat flux magnitude", f"{float(heat_flux.max()):.5g} W/m²"],
            ["Mean heat flux magnitude", f"{float(heat_flux.mean()):.5g} W/m²"],
            ["Minimum heat flux magnitude", f"{float(heat_flux.min()):.5g} W/m²"],
        ], [70 * mm, 90 * mm]),
        Paragraph(
            "Heat flux is estimated from Fourier's law, q = -k grad(T), using "
            "finite-difference temperature gradients on the Cartesian grid. "
            "Values are local conductive heat-flux density, not total heat rate.",
            styles["SmallNote"],
        ),
        Paragraph("9. Simulation Results", styles["Section"]),
        add_table([
            ["Metric", "Result"],
            ["Minimum temperature", f"{float(T.min()):.5f} °C"],
            ["Maximum temperature", f"{float(T.max()):.5f} °C"],
            ["Mean temperature", f"{float(T.mean()):.5f} °C"],
        ], [70 * mm, 90 * mm]),
        Paragraph("9. Engineering Notes &amp; Model Limitations", styles["Section"]),
        Paragraph(
            "This is an educational numerical model of 2D conduction in a homogeneous, "
            "isotropic material with constant properties and fixed-temperature "
            "(Dirichlet) boundaries. Convection, radiation, temperature-dependent "
            "properties, contact resistance, and deformation are not included. "
            "The numerical result is not an experimental measurement and should not "
            "be used for safety-critical engineering decisions without independent "
            "verification and validation.",
            styles["SmallNote"],
        ),
    ])

    if data.get("residual") is not None:
        story.insert(-1, Paragraph("10. Steady-State Equation Residual", styles["Section"]))
        story.insert(-1, add_table([
            ["Diagnostic", "Result"],
            ["Maximum absolute residual", f"{data['residual']['residual_max_abs']:.5e} K/m²"],
            ["RMS residual", f"{data['residual']['residual_rms']:.5e} K/m²"],
        ], [70 * mm, 90 * mm]))
        story.insert(-1, Paragraph(
            "Residual is evaluated on interior nodes using the discrete Laplace/Poisson equation. "
            "It measures equation consistency for this grid; it is not an estimate of experimental error "
            "and should be compared only with consistent mesh and scaling.",
            styles["SmallNote"],
        ))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D6DEE5"))
        canvas.line(20 * mm, 13 * mm, A4[0] - 20 * mm, 13 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#687784"))
        canvas.drawString(20 * mm, 8 * mm, "Physics AI Studio · Educational solver")
        canvas.drawRightString(A4[0] - 20 * mm, 8 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    return buffer.getvalue()
