"""
Redstone PDM - Field Engineer Job Card System
==============================================
Module 3: Mobile job card completion, PDF generation, invoice creation.
Contractors log in, complete job cards, system generates PDFs and emails.
"""

import os
import io
import json
import math
import requests
import psycopg2
import psycopg2.extras
from datetime import datetime, date, timedelta
from functools import wraps
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (Mail, Attachment, FileContent,
                                    FileName, FileType, Disposition)
import base64
from flask import (Flask, render_template, request, jsonify,
                   redirect, url_for, session, send_file)
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                 Paragraph, Spacer, Image, HRFlowable)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "redstone-jobcard-2024")

DATABASE_URL    = os.environ["DATABASE_URL"]
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
FROM_EMAIL       = os.environ.get("FROM_EMAIL", "info@redstonepdm.com")
ACCOUNTS_EMAIL   = os.environ.get("ACCOUNTS_EMAIL", "accounts@redstonepdm.com")
GMAPS_API_KEY    = os.environ.get("GMAPS_API_KEY", "")

UPLOAD_FOLDER   = "/tmp/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── Contractor Profiles ───────────────────────────────────────────────────────

CONTRACTORS = {
    "dave_duppa": {
        "name": "Dave Duppa",
        "email": "daveduppa@redstonepdm.com",
        "phone": "07897509190",
        "address": "9 Canberra Gardens, Cranfield, MK43 1AQ",
        "utr": None,
        "ni": None,
        "sort_code": None,
        "account_no": None,
        "day_rate": 250,
        "overtime_rate": 25.0,
        "redstone_vehicle": True,
        "van_reg": "EA19ECD",
        "mileage_rate": 0,
        "redstone_card": True,
        "cis_rate": 0,        # Director - exempt
        "password": "Duppa2024!",
    },
    "mark_ashpool": {
        "name": "Mark Ashpool",
        "email": "markashpool48@gmail.com",
        "phone": "07513628195",
        "address": "9 Exebridge, Furzton, Milton Keynes, MK4 1LH",
        "utr": "1781674128",
        "ni": "NZ020247B",
        "sort_code": "11-04-48",
        "account_no": "25017867",
        "day_rate": 186,
        "overtime_rate": 18.6,
        "redstone_vehicle": False,
        "van_reg": "KR17XHV",
        "mileage_rate": 0.25,
        "redstone_card": True,
        "cis_rate": 0.20,
        "password": "Ashpool2024!",
    },
    "richard_chambers": {
        "name": "Richard Chambers",
        "email": "rchambers87@hotmail.com",
        "phone": "07595052492",
        "address": "3 Argonaute Wharf, Brooklands, Milton Keynes, MK10 7LX",
        "utr": "4334475511",
        "ni": "JZ627889B",
        "sort_code": "04-00-04",
        "account_no": "15204776",
        "day_rate": 180,
        "overtime_rate": 18.0,
        "redstone_vehicle": True,
        "van_reg": "BP63MBO",
        "mileage_rate": 0,
        "redstone_card": True,
        "cis_rate": 0.20,
        "password": "Chambers2024!",
    },
    "ash_everett": {
        "name": "Ashley Everett",
        "email": "asheverett03@gmail.com",
        "phone": "07917524608",
        "address": "30 Mill Close, Elsenham, Bishops Stortford, CM22 6EG",
        "utr": "6310398358",
        "ni": "JZ081305B",
        "sort_code": "11-01-66",
        "account_no": "13761765",
        "day_rate": 186,
        "overtime_rate": 18.6,
        "redstone_vehicle": True,
        "van_reg": "YT66NDJ",
        "mileage_rate": 0,
        "redstone_card": True,
        "cis_rate": 0.20,
        "password": "Everett2024!",
    },
    "cassius_kwarteng": {
        "name": "Cassius Kwarteng",
        "email": "kwrtng@talktalk.net",
        "phone": "07487698681",
        "address": "2 Hartley, Great Linford, Milton Keynes, MK14 5EB",
        "utr": "7586294311",
        "ni": "PW606883D",
        "sort_code": "77-21-10",
        "account_no": "25644560",
        "day_rate": 180,
        "overtime_rate": 18.0,
        "redstone_vehicle": True,
        "van_reg": "YT65TKX",
        "mileage_rate": 0,
        "redstone_card": True,
        "cis_rate": 0.20,
        "password": "Cassius2024!",
    },
    "dave_lefevre": {
        "name": "Dave Lefevre",
        "email": "bigdavelef@gmail.com",
        "phone": "07766351261",
        "address": "Flat above 80 Aylesbury Street, Fenny Stratford, Bletchley, MK2 2BA",
        "utr": "8861831155",
        "ni": "NZ148785C",
        "sort_code": "60-14-55",
        "account_no": "60915188",
        "day_rate": 200,
        "overtime_rate": 20.0,
        "redstone_vehicle": True,
        "van_reg": "AK17WTV",
        "mileage_rate": 0,
        "redstone_card": True,
        "cis_rate": 0.20,
        "password": "Lefevre2024!",
    },
    "aziz_rehman": {
        "name": "Aziz Rehman",
        "email": "HRehman@hotmail.co.uk",
        "phone": "07982904246",
        "address": "118 Trafalgar Road, Moseley, Birmingham, B13 8BX",
        "utr": "5614567336",
        "ni": "JG075656A",
        "sort_code": "77-85-59",
        "account_no": "16656868",
        "day_rate": 200,
        "overtime_rate": 20.0,
        "redstone_vehicle": False,
        "van_reg": "HA51ZEZ",
        "mileage_rate": 0.25,
        "redstone_card": True,
        "cis_rate": 0.20,
        "password": "Aziz2024!",
    },
    "james_rutland": {
        "name": "James Rutland",
        "email": "rutters1983@hotmail.co.uk",
        "phone": "07500900582",
        "address": "40 Milecastle, Bancroft, Milton Keynes, MK13 0QN",
        "utr": "7891847516",
        "ni": "JJ092921B",
        "sort_code": "60-20-34",
        "account_no": "41002547",
        "day_rate": 180,
        "overtime_rate": 18.0,
        "redstone_vehicle": False,
        "van_reg": "R12UTY",
        "mileage_rate": 0.25,
        "redstone_card": False,   # Uses own card - reimburse
        "cis_rate": 0.20,
        "password": "Rutland2024!",
    },
}

# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS job_cards (
            id                  SERIAL PRIMARY KEY,
            contractor_key      TEXT NOT NULL,
            job_id              TEXT NOT NULL,
            card_date           DATE NOT NULL,
            site_name           TEXT,
            postcode            TEXT,
            description_planned TEXT,
            description_actual  TEXT,
            time_start          TEXT,
            time_finish         TEXT,
            hours_on_site       NUMERIC(4,2),
            labour_type         TEXT,
            base_day_rate       NUMERIC(8,2),
            overtime_hours      NUMERIC(4,2) DEFAULT 0,
            overtime_rate       NUMERIC(8,2),
            labour_cost         NUMERIC(8,2),
            mileage_miles       NUMERIC(8,2) DEFAULT 0,
            mileage_cost        NUMERIC(8,2) DEFAULT 0,
            parking_cost        NUMERIC(8,2) DEFAULT 0,
            materials_json      JSONB DEFAULT '[]',
            materials_total     NUMERIC(8,2) DEFAULT 0,
            reimburse_total     NUMERIC(8,2) DEFAULT 0,
            odometer            INTEGER,
            only_job_today      BOOLEAN DEFAULT TRUE,
            invoice_total       NUMERIC(8,2),
            cis_deduction       NUMERIC(8,2),
            net_payment         NUMERIC(8,2),
            status              TEXT DEFAULT 'submitted',
            photo_paths         JSONB DEFAULT '[]',
            parking_photo_path  TEXT,
            receipt_photo_paths JSONB DEFAULT '[]',
            submitted_at        TIMESTAMPTZ DEFAULT NOW(),
            approved_at         TIMESTAMPTZ,
            approved_by         TEXT,
            notes               TEXT
        );

        CREATE TABLE IF NOT EXISTS weekly_summaries (
            id              SERIAL PRIMARY KEY,
            contractor_key  TEXT NOT NULL,
            week_commencing DATE NOT NULL,
            total_labour    NUMERIC(8,2),
            total_mileage   NUMERIC(8,2),
            total_materials NUMERIC(8,2),
            total_parking   NUMERIC(8,2),
            invoice_total   NUMERIC(8,2),
            cis_deduction   NUMERIC(8,2),
            net_payment     NUMERIC(8,2),
            status          TEXT DEFAULT 'pending',
            created_at      TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS contractor_locations (
            contractor_key  TEXT PRIMARY KEY,
            last_location   TEXT,
            last_job_id     TEXT,
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    conn.commit()
    cur.close()
    conn.close()


# ── Auth ──────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "contractor_key" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") != "admin":
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ── Mileage Calculation ───────────────────────────────────────────────────────

def calculate_mileage(origin_address, destination_postcode):
    """Calculate round trip mileage using Google Maps Distance Matrix API."""
    if not GMAPS_API_KEY:
        return 0, 0
    try:
        # Outbound
        url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        params = {
            "origins": origin_address,
            "destinations": destination_postcode + ", UK",
            "units": "imperial",
            "key": GMAPS_API_KEY,
        }
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        element = data["rows"][0]["elements"][0]
        if element["status"] != "OK":
            return 0, 0
        # Distance in metres -> miles
        outbound_m = element["distance"]["value"]
        outbound_miles = outbound_m / 1609.34

        # Return leg
        params["origins"] = destination_postcode + ", UK"
        params["destinations"] = origin_address
        r2 = requests.get(url, params=params, timeout=10)
        data2 = r2.json()
        element2 = data2["rows"][0]["elements"][0]
        return_miles = element2["distance"]["value"] / 1609.34 if element2["status"] == "OK" else outbound_miles

        total = round(outbound_miles + return_miles, 1)
        return total, round(outbound_miles, 1)
    except Exception:
        return 0, 0


# ── PDF Generation ────────────────────────────────────────────────────────────

REDSTONE_DARK  = colors.HexColor("#1a2332")
REDSTONE_RED   = colors.HexColor("#c0392b")
REDSTONE_LIGHT = colors.HexColor("#f5f6f8")
REDSTONE_GREY  = colors.HexColor("#7f8c8d")


def build_job_card_pdf(card, contractor):
    """Generate Field Engineer Job Card PDF. Returns bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=15*mm, bottomMargin=15*mm,
                            leftMargin=15*mm, rightMargin=15*mm)
    styles = getSampleStyleSheet()
    story = []

    label_style = ParagraphStyle("label", fontSize=8, textColor=REDSTONE_GREY,
                                  fontName="Helvetica-Bold", spaceAfter=1)
    value_style = ParagraphStyle("value", fontSize=10, textColor=REDSTONE_DARK,
                                  fontName="Helvetica", spaceAfter=6)
    head_style  = ParagraphStyle("head", fontSize=16, textColor=REDSTONE_DARK,
                                  fontName="Helvetica-Bold")
    sub_style   = ParagraphStyle("sub", fontSize=9, textColor=REDSTONE_GREY,
                                  fontName="Helvetica")
    section_style = ParagraphStyle("section", fontSize=11, textColor=colors.white,
                                    fontName="Helvetica-Bold", backColor=REDSTONE_DARK,
                                    leftIndent=4, spaceAfter=0, spaceBefore=8)

    # Header
    header_data = [[
        Paragraph("Redstone PDM", head_style),
        Paragraph(f"Field Engineer Job Card<br/><font size=9 color=grey>{card['card_date'].strftime('%A, %d %B %Y')}</font>", head_style),
    ]]
    header_table = Table(header_data, colWidths=[85*mm, 95*mm])
    header_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=2, color=REDSTONE_RED, spaceAfter=8))

    def field_row(label, value):
        return [Paragraph(label, label_style), Paragraph(str(value) if value else "—", value_style)]

    # Job details
    story.append(Paragraph(" JOB DETAILS", section_style))
    story.append(Spacer(1, 4))
    details = Table([
        field_row("JOB NUMBER", card["job_id"]),
        field_row("ENGINEER NAME", contractor["name"]),
        field_row("DATE", card["card_date"].strftime("%A, %d %B %Y")),
        field_row("SITE / LOCATION", f"{card['site_name']} {card['postcode']}"),
        field_row("DESCRIPTION OF WORKS PLANNED", card["description_planned"]),
        field_row("DESCRIPTION OF WORKS CARRIED OUT", card["description_actual"]),
        field_row("TIME ON SITE", f"{card['time_start']} — {card['time_finish']}  ({card['hours_on_site']} hrs)"),
    ], colWidths=[55*mm, 125*mm])
    details.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), REDSTONE_LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(details)

    # Labour
    story.append(Paragraph(" LABOUR", section_style))
    story.append(Spacer(1, 4))
    labour = Table([
        field_row("LABOUR TYPE", card["labour_type"]),
        field_row("BASE DAY RATE", f"£{card['base_day_rate']:.2f}"),
        field_row("OVERTIME HOURS", f"{card['overtime_hours']} hrs @ £{card['overtime_rate']:.2f}/hr" if card["overtime_hours"] else "None"),
        field_row("TOTAL LABOUR COST", f"£{card['labour_cost']:.2f}"),
    ], colWidths=[55*mm, 125*mm])
    labour.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), REDSTONE_LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(labour)

    # Materials
    materials = card.get("materials_json") or []
    if materials:
        story.append(Paragraph(" MATERIALS", section_style))
        story.append(Spacer(1, 4))
        mat_data = [["#", "Description", "Qty", "Unit Cost", "Total", "Payment"]]
        for i, m in enumerate(materials, 1):
            mat_data.append([
                str(i),
                m.get("description", ""),
                str(m.get("qty", "")),
                f"£{float(m.get('unit_cost', 0)):.2f}",
                f"£{float(m.get('total', 0)):.2f}",
                m.get("payment", "Redstone Card"),
            ])
        mat_table = Table(mat_data, colWidths=[8*mm, 60*mm, 15*mm, 22*mm, 22*mm, 33*mm])
        mat_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), REDSTONE_DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, REDSTONE_LIGHT]),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(mat_table)

    # Travel / mileage
    if contractor["mileage_rate"] > 0:
        story.append(Paragraph(" TRAVEL & MILEAGE", section_style))
        story.append(Spacer(1, 4))
        travel = Table([
            field_row("TOTAL MILEAGE", f"{card['mileage_miles']} miles (round trip)"),
            field_row("MILEAGE RATE", f"{int(contractor['mileage_rate']*100)}p per mile"),
            field_row("MILEAGE COST", f"£{card['mileage_cost']:.2f}"),
            field_row("ODOMETER READING", str(card.get("odometer", "—"))),
        ], colWidths=[55*mm, 125*mm])
        travel.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), REDSTONE_LIGHT),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(travel)

    # Parking
    if card.get("parking_cost", 0):
        story.append(Paragraph(" PARKING", section_style))
        story.append(Spacer(1, 4))
        parking = Table([
            field_row("PARKING COST", f"£{card['parking_cost']:.2f}"),
        ], colWidths=[55*mm, 125*mm])
        parking.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), REDSTONE_LIGHT),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(parking)

    doc.build(story)
    buf.seek(0)
    return buf.read()


def build_invoice_pdf(card, contractor):
    """Generate Reverse Self-Billing Invoice PDF. Returns bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=15*mm, bottomMargin=15*mm,
                            leftMargin=15*mm, rightMargin=15*mm)
    styles = getSampleStyleSheet()
    story = []

    label_style = ParagraphStyle("label", fontSize=8, textColor=REDSTONE_GREY,
                                  fontName="Helvetica-Bold")
    value_style = ParagraphStyle("value", fontSize=10, textColor=REDSTONE_DARK,
                                  fontName="Helvetica")
    head_style  = ParagraphStyle("head", fontSize=16, textColor=REDSTONE_DARK,
                                  fontName="Helvetica-Bold")
    total_style = ParagraphStyle("total", fontSize=14, textColor=REDSTONE_DARK,
                                  fontName="Helvetica-Bold", alignment=TA_RIGHT)

    # Header
    story.append(Paragraph("Redstone PDM", head_style))
    story.append(Paragraph("Reverse Self-Billing Invoice", ParagraphStyle(
        "sub", fontSize=12, textColor=REDSTONE_GREY, fontName="Helvetica")))
    story.append(HRFlowable(width="100%", thickness=2, color=REDSTONE_RED, spaceAfter=8))

    # Parties
    parties = Table([
        [
            Paragraph(f"<b>Engineer:</b> {contractor['name']}<br/>"
                      f"{contractor['address']}<br/>"
                      f"UTR: {contractor.get('utr', '—')}<br/>"
                      f"NI: {contractor.get('ni', '—')}<br/>"
                      f"Bank: {contractor.get('sort_code', '—')} / {contractor.get('account_no', '—')}",
                      value_style),
            Paragraph("<b>Bill to:</b><br/>Redstone PDM Ltd<br/>9 Canberra Gardens<br/>Cranfield<br/>MK43 1AQ<br/>"
                      "VAT Reg: 248 5387 69<br/>Company: 10070131",
                      value_style),
        ]
    ], colWidths=[90*mm, 90*mm])
    story.append(parties)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e0e0e0"), spaceAfter=8))

    # Job summary
    def row(label, value):
        return [Paragraph(f"<b>{label}</b>", label_style),
                Paragraph(str(value) if value else "—", value_style)]

    summary = Table([
        row("JOB NUMBER", card["job_id"]),
        row("DATE", card["card_date"].strftime("%A, %d %B %Y")),
        row("SITE / LOCATION", f"{card['site_name']} {card['postcode']}"),
        row("DESCRIPTION OF WORKS", card["description_actual"]),
    ], colWidths=[55*mm, 125*mm])
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), REDSTONE_LIGHT),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(summary)
    story.append(Spacer(1, 8))

    # Cost breakdown
    cost_data = [["Item", "Amount"]]
    cost_data.append(["Labour", f"£{card['labour_cost']:.2f}"])
    if card.get("mileage_cost", 0):
        cost_data.append([f"Mileage ({card['mileage_miles']} miles @ {int(contractor['mileage_rate']*100)}p/mile)",
                          f"£{card['mileage_cost']:.2f}"])
    if card.get("parking_cost", 0):
        cost_data.append(["Parking", f"£{card['parking_cost']:.2f}"])
    if card.get("reimburse_total", 0):
        cost_data.append(["Materials (To Be Reimbursed)", f"£{card['reimburse_total']:.2f}"])

    cost_table = Table(cost_data, colWidths=[140*mm, 40*mm])
    cost_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), REDSTONE_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, REDSTONE_LIGHT]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(cost_table)
    story.append(Spacer(1, 4))

    # Totals
    totals_data = [
        ["Gross Invoice Value", f"£{card['invoice_total']:.2f}"],
    ]
    if contractor["cis_rate"] > 0:
        totals_data.append([f"CIS Deduction ({int(contractor['cis_rate']*100)}%)",
                            f"-£{card['cis_deduction']:.2f}"])
        totals_data.append(["Net Payment to Contractor", f"£{card['net_payment']:.2f}"])

    totals_table = Table(totals_data, colWidths=[140*mm, 40*mm])
    totals_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BACKGROUND", (-1, -1), (-1, -1), REDSTONE_DARK),
        ("TEXTCOLOR", (-1, -1), (-1, -1), colors.white),
        ("BACKGROUND", (0, -1), (0, -1), REDSTONE_DARK),
        ("TEXTCOLOR", (0, -1), (0, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEABOVE", (0, 0), (-1, 0), 1, REDSTONE_RED),
    ]))
    story.append(totals_table)

    # EEBS notice
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Payment will be processed via EEBS (pay intermediary) in accordance with IR35 regulations. "
        "CIS deductions are calculated on labour elements only. "
        "This is a self-billing invoice raised by Redstone PDM Ltd on behalf of the above engineer.",
        ParagraphStyle("note", fontSize=7, textColor=REDSTONE_GREY, fontName="Helvetica")))

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(to_addresses, subject, body_html, attachments=None):
    """Send email via SendGrid with optional PDF attachments."""
    if not SENDGRID_API_KEY:
        print("No SendGrid API key — email skipped")
        return False
    try:
        if isinstance(to_addresses, str):
            to_addresses = [to_addresses]

        message = Mail(
            from_email=FROM_EMAIL,
            to_emails=to_addresses,
            subject=subject,
            html_content=body_html,
        )

        if attachments:
            for filename, data in attachments:
                encoded = base64.b64encode(data).decode()
                attachment = Attachment(
                    FileContent(encoded),
                    FileName(filename),
                    FileType("application/pdf"),
                    Disposition("attachment"),
                )
                message.add_attachment(attachment)

        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"Email sent: {response.status_code}")
        return response.status_code in (200, 202)
    except Exception as e:
        print(f"Email error: {e}")
        return False


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "contractor_key" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        # Admin login
        if request.form.get("username") == "admin" and \
           request.form.get("password") == os.environ.get("ADMIN_PASSWORD", "redstone2024"):
            session["role"] = "admin"
            session["contractor_key"] = "admin"
            return redirect(url_for("admin_dashboard"))

        # Contractor login — match by name
        password = request.form.get("password", "")
        name_input = request.form.get("name", "").strip().lower()
        for key, c in CONTRACTORS.items():
            if c["name"].lower() == name_input and c["password"] == password:
                session["contractor_key"] = key
                session["role"] = "contractor"
                return redirect(url_for("dashboard"))
        error = "Name or password not recognised."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    if session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))

    key = session["contractor_key"]
    contractor = CONTRACTORS[key]

    # Get allocated jobs for this contractor from planner
    conn = get_db()
    cur = conn.cursor()

    # Get this week's allocated jobs
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    cur.execute("""
        SELECT a.id as alloc_id, a.job_id, a.day_date, a.notes as alloc_notes,
               j.pub_name, j.postcode, j.description, j.trade_type, j.due_date,
               j.tab, j.sub_tab,
               jc.id as card_id, jc.status as card_status
        FROM allocations a
        JOIN jobs j ON j.job_id = a.job_id
        LEFT JOIN job_cards jc ON jc.job_id = a.job_id
            AND jc.contractor_key = %s
            AND jc.card_date = a.day_date
        WHERE a.contractor = %s
        AND a.day_date BETWEEN %s AND %s
        ORDER BY a.day_date, a.id
    """, (key, contractor["name"], week_start, week_end))
    jobs = cur.fetchall()

    # Get recent submitted cards
    cur.execute("""
        SELECT * FROM job_cards
        WHERE contractor_key = %s
        ORDER BY submitted_at DESC LIMIT 10
    """, (key,))
    recent_cards = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("dashboard.html",
                           contractor=contractor,
                           jobs=jobs,
                           recent_cards=recent_cards,
                           week_start=week_start,
                           today=today)


@app.route("/job/<job_id>/<card_date>")
@login_required
def job_card_form(job_id, card_date):
    key = session["contractor_key"]
    contractor = CONTRACTORS[key]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM jobs WHERE job_id = %s", (job_id,))
    job = cur.fetchone()

    # Check if card already submitted
    cur.execute("""
        SELECT * FROM job_cards
        WHERE job_id = %s AND contractor_key = %s AND card_date = %s
    """, (job_id, key, card_date))
    existing_card = cur.fetchone()
    cur.close()
    conn.close()

    if not job:
        return "Job not found", 404

    # Auto-calculate mileage if contractor is paid mileage
    mileage_miles = 0
    if contractor["mileage_rate"] > 0 and job.get("postcode"):
        mileage_miles, _ = calculate_mileage(contractor["address"], job["postcode"])

    return render_template("job_card.html",
                           contractor=contractor,
                           job=job,
                           card_date=card_date,
                           mileage_miles=mileage_miles,
                           existing_card=existing_card,
                           gmaps_key=GMAPS_API_KEY)


@app.route("/job/<job_id>/<card_date>/submit", methods=["POST"])
@login_required
def submit_job_card(job_id, card_date):
    key = session["contractor_key"]
    contractor = CONTRACTORS[key]

    # Parse form data
    time_start    = request.form.get("time_start", "")
    time_finish   = request.form.get("time_finish", "")
    hours         = float(request.form.get("hours_on_site", 0) or 0)
    overtime_h    = float(request.form.get("overtime_hours", 0) or 0)
    odometer      = request.form.get("odometer") or None
    only_job      = request.form.get("only_job_today") == "yes"
    desc_actual   = request.form.get("description_actual", "")
    desc_planned  = request.form.get("description_planned", "")
    mileage_miles = float(request.form.get("total_miles", 0) or 0)
    card_date_str = request.form.get("card_date", card_date)

    # Parse journey legs
    journey_json = request.form.get("journey_json", "[]")
    try:
        journey_legs = json.loads(journey_json)
    except Exception:
        journey_legs = []

    # Recalculate billable miles server-side — exclude nextjob legs
    billable_miles = sum(
        float(l.get("miles", 0))
        for l in journey_legs
        if l.get("type") != "nextjob"
    )
    # Override client-submitted total with server-calculated value
    if journey_legs:
        mileage_miles = round(billable_miles, 1)

    # Parse parking charges
    parking = 0.0
    parking_items = []
    park_count = int(request.form.get("parking_count", 0))
    reimburse_parking = 0.0
    for i in range(1, park_count + 1):
        desc = request.form.get(f"park_desc_{i}", "").strip()
        cost = float(request.form.get(f"park_cost_{i}", 0) or 0)
        payment = request.form.get(f"park_payment_{i}", "Redstone Card")
        if cost > 0:
            parking_items.append({"description": desc, "cost": cost, "payment": payment})
            parking += cost
            if payment != "Redstone Card":
                reimburse_parking += cost

    # Labour cost: full day rate + overtime
    labour_cost = float(contractor["day_rate"]) + (overtime_h * float(contractor["overtime_rate"]))

    # Mileage cost
    mileage_cost = round(mileage_miles * contractor["mileage_rate"], 2)

    # Materials
    materials = []
    reimburse_total = 0.0
    mat_count = int(request.form.get("material_count", 0))
    for i in range(1, mat_count + 1):
        desc = request.form.get(f"mat_desc_{i}", "").strip()
        if not desc:
            continue
        qty       = float(request.form.get(f"mat_qty_{i}", 1) or 1)
        unit_cost = float(request.form.get(f"mat_cost_{i}", 0) or 0)
        payment   = request.form.get(f"mat_payment_{i}", "Redstone Card")
        total     = round(qty * unit_cost, 2)
        materials.append({
            "description": desc,
            "qty": qty,
            "unit_cost": unit_cost,
            "total": total,
            "payment": payment,
        })
        if payment != "Redstone Card":
            reimburse_total += total

    materials_total = sum(m["total"] for m in materials)

    # Invoice total = labour + mileage + parking (reimburse only) + reimbursable materials
    reimburse_total_all = reimburse_total + reimburse_parking
    invoice_total = labour_cost + mileage_cost + reimburse_total_all
    # Redstone card parking is a company cost not on contractor invoice
    redstone_parking = parking - reimburse_parking
    cis_deduction = round(labour_cost * contractor["cis_rate"], 2)
    net_payment   = round(invoice_total - cis_deduction, 2)

    # Handle file uploads
    def save_files(field_name):
        paths = []
        files = request.files.getlist(field_name)
        for f in files:
            if f and f.filename:
                fname = secure_filename(f"{job_id}_{card_date}_{key}_{f.filename}")
                fpath = os.path.join(UPLOAD_FOLDER, fname)
                f.save(fpath)
                paths.append(fpath)
        return paths

    photo_paths        = save_files("completion_photos")
    parking_photos     = save_files("parking_photo")
    receipt_photos     = save_files("receipt_photos")
    parking_photo_path = parking_photos[0] if parking_photos else None

    # Get job info for PDFs
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM jobs WHERE job_id = %s", (job_id,))
    job = cur.fetchone()

    card = {
        "job_id": job_id,
        "card_date": datetime.strptime(card_date, "%Y-%m-%d").date(),
        "site_name": job["pub_name"] if job else "",
        "postcode": job["postcode"] if job else "",
        "description_planned": desc_planned or (job["description"] if job else ""),
        "description_actual": desc_actual,
        "time_start": time_start,
        "time_finish": time_finish,
        "hours_on_site": hours,
        "labour_type": f"Full Day + {overtime_h}hrs OT" if overtime_h else "Full Day",
        "base_day_rate": contractor["day_rate"],
        "overtime_hours": overtime_h,
        "overtime_rate": contractor["overtime_rate"],
        "labour_cost": labour_cost,
        "mileage_miles": mileage_miles,
        "mileage_cost": mileage_cost,
        "parking_cost": parking,
        "materials_json": materials,
        "materials_total": materials_total,
        "reimburse_total": reimburse_total,
        "odometer": odometer,
        "only_job_today": only_job,
        "invoice_total": invoice_total,
        "cis_deduction": cis_deduction,
        "net_payment": net_payment,
        "photo_paths": photo_paths,
        "parking_photo_path": parking_photo_path,
        "receipt_photo_paths": receipt_photos,
    }

    # Save to database
    cur.execute("""
        INSERT INTO job_cards (
            contractor_key, job_id, card_date, site_name, postcode,
            description_planned, description_actual, time_start, time_finish,
            hours_on_site, labour_type, base_day_rate, overtime_hours, overtime_rate,
            labour_cost, mileage_miles, mileage_cost, parking_cost,
            materials_json, materials_total, reimburse_total, odometer,
            only_job_today, invoice_total, cis_deduction, net_payment,
            photo_paths, parking_photo_path, receipt_photo_paths, status
        ) VALUES (
            %(contractor_key)s, %(job_id)s, %(card_date)s, %(site_name)s, %(postcode)s,
            %(description_planned)s, %(description_actual)s, %(time_start)s, %(time_finish)s,
            %(hours_on_site)s, %(labour_type)s, %(base_day_rate)s, %(overtime_hours)s, %(overtime_rate)s,
            %(labour_cost)s, %(mileage_miles)s, %(mileage_cost)s, %(parking_cost)s,
            %(materials_json)s, %(materials_total)s, %(reimburse_total)s, %(odometer)s,
            %(only_job_today)s, %(invoice_total)s, %(cis_deduction)s, %(net_payment)s,
            %(photo_paths)s, %(parking_photo_path)s, %(receipt_photo_paths)s, 'submitted'
        )
        ON CONFLICT DO NOTHING
        RETURNING id
    """, {
        **card,
        "contractor_key": key,
        "materials_json": json.dumps(materials),
        "photo_paths": json.dumps(photo_paths),
        "receipt_photo_paths": json.dumps(receipt_photos),
    })
    result = cur.fetchone()
    conn.commit()

    # Save last known location for this contractor (for next job card start point)
    try:
        loc_conn = get_db()
        loc_cur = loc_conn.cursor()
        loc_cur.execute("""
            INSERT INTO contractor_locations (contractor_key, last_location, last_job_id, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (contractor_key) DO UPDATE
            SET last_location = EXCLUDED.last_location,
                last_job_id = EXCLUDED.last_job_id,
                updated_at = EXCLUDED.updated_at
        """, (key, job.get("postcode", "") + " " + job.get("pub_name", ""), job_id))
        loc_conn.commit()
        loc_cur.close()
        loc_conn.close()
    except Exception as e:
        print(f"Could not save last location: {e}")

    # Generate PDFs
    job_card_pdf  = build_job_card_pdf(card, contractor)
    invoice_pdf   = build_invoice_pdf(card, contractor)

    filename_base = f"{contractor['name'].replace(' ','_')}_{job_id}_{card_date}"

    # Email to accounts + contractor
    send_email(
        to_addresses=[ACCOUNTS_EMAIL, contractor["email"]],
        subject=f"Redstone PDM — Invoice: {contractor['name']} | {job_id} | {card_date}",
        body_html=f"""
            <p>Please find attached the self-billing invoice for:</p>
            <ul>
                <li><b>Engineer:</b> {contractor['name']}</li>
                <li><b>Job:</b> {job_id} — {card.get('site_name', '')}</li>
                <li><b>Date:</b> {card_date}</li>
                <li><b>Invoice Total:</b> £{invoice_total:.2f}</li>
                <li><b>CIS Deduction:</b> £{cis_deduction:.2f}</li>
                <li><b>Net Payment:</b> £{net_payment:.2f}</li>
            </ul>
            <p>This invoice has been saved to the Redstone PDM platform for your records.</p>
        """,
        attachments=[
            (f"{filename_base}_invoice.pdf", invoice_pdf),
        ]
    )

    # Job card saved to platform only (not emailed)
    if result:
        card_id = result["id"]
        # Store PDF in DB or filesystem for lookup
        pdf_path = os.path.join(UPLOAD_FOLDER, f"{filename_base}_jobcard.pdf")
        with open(pdf_path, "wb") as f:
            f.write(job_card_pdf)
        cur.execute("UPDATE job_cards SET notes = %s WHERE id = %s",
                    (pdf_path, card_id))
        conn.commit()

    cur.close()
    conn.close()

    return redirect(url_for("card_submitted", job_id=job_id, card_date=card_date))


@app.route("/submitted/<job_id>/<card_date>")
@login_required
def card_submitted(job_id, card_date):
    key = session["contractor_key"]
    contractor = CONTRACTORS[key]
    return render_template("submitted.html", contractor=contractor,
                           job_id=job_id, card_date=card_date)


@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT jc.*, j.pub_name, j.description as job_description
        FROM job_cards jc
        LEFT JOIN jobs j ON j.job_id = jc.job_id
        ORDER BY jc.submitted_at DESC
        LIMIT 50
    """)
    cards = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("admin.html", cards=cards, contractors=CONTRACTORS)


@app.route("/admin/approve/<int:card_id>", methods=["POST"])
@admin_required
def approve_card(card_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE job_cards SET status = 'approved', approved_at = NOW(), approved_by = 'admin'
        WHERE id = %s
    """, (card_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@app.route("/card/<int:card_id>/jobcard.pdf")
@admin_required
def download_job_card(card_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM job_cards WHERE id = %s", (card_id,))
    card = cur.fetchone()
    cur.close()
    conn.close()
    if not card:
        return "Not found", 404
    contractor = CONTRACTORS.get(card["contractor_key"], {})
    pdf = build_job_card_pdf(card, contractor)
    return send_file(io.BytesIO(pdf), mimetype="application/pdf",
                     download_name=f"jobcard_{card_id}.pdf")


@app.route("/api/last_location")
@login_required
def api_last_location():
    """Return contractor's last known location if set today, else their home address."""
    key = session["contractor_key"]
    contractor = CONTRACTORS[key]
    today = date.today()

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT last_location, last_job_id, updated_at
        FROM contractor_locations
        WHERE contractor_key = %s
    """, (key,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    # Only use last location if it was set today
    if row and row["updated_at"] and row["updated_at"].date() == today and row["last_location"]:
        return jsonify({
            "location": row["last_location"],
            "job_id": row["last_job_id"],
            "from_last_job": True
        })

    return jsonify({
        "location": contractor["address"],
        "job_id": None,
        "from_last_job": False
    })


@app.route("/api/mileage")
@login_required
def api_mileage():
    key = session["contractor_key"]
    contractor = CONTRACTORS[key]
    origin = request.args.get("from", "")
    dest   = request.args.get("to", "")
    return_to_site = request.args.get("return_to_site", "false") == "true"
    site   = request.args.get("site", "")

    if not origin or not dest:
        return jsonify({"miles": 0, "cost": 0})

    try:
        if not GMAPS_API_KEY:
            return jsonify({"miles": 0, "cost": 0, "error": "No API key configured"})

        def get_miles(a, b):
            url = "https://maps.googleapis.com/maps/api/distancematrix/json"
            params = {
                "origins": a,
                "destinations": b,
                "units": "imperial",
                "region": "gb",
                "key": GMAPS_API_KEY
            }
            r = requests.get(url, params=params, timeout=10)
            data = r.json()
            status = data.get("status", "UNKNOWN")
            if status != "OK":
                print(f"Distance Matrix API error: {status} — {data.get('error_message', '')}")
                return 0, f"API error: {status} — {data.get('error_message', '')}"
            el = data["rows"][0]["elements"][0]
            el_status = el.get("status", "UNKNOWN")
            print(f"Distance Matrix {a} -> {b}: {el_status}")
            if el_status != "OK":
                return 0, f"Route not found: {el_status}"
            miles = round(el["distance"]["value"] / 1609.34, 1)
            return miles, None

        miles, err = get_miles(origin, dest)
        if err:
            return jsonify({"miles": 0, "cost": 0, "error": err})

        # Materials run: merchant → site return leg
        if return_to_site and site:
            extra, err2 = get_miles(dest, site)
            if not err2:
                miles += extra

        cost = round(miles * contractor["mileage_rate"], 2)
        print(f"Mileage API: {origin} -> {dest} = {miles} miles, £{cost}")
        return jsonify({"miles": miles, "cost": cost})
    except Exception as e:
        print(f"Mileage API exception: {e}")
        return jsonify({"miles": 0, "cost": 0, "error": str(e)})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False)
