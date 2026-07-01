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
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=24)
app.config["SESSION_REFRESH_EACH_REQUEST"] = False

DATABASE_URL     = os.environ["DATABASE_URL"]
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
FROM_EMAIL       = os.environ.get("FROM_EMAIL", "info@redstonepdm.com")
ACCOUNTS_EMAIL   = os.environ.get("ACCOUNTS_EMAIL", "accounts@redstonepdm.com")
GMAPS_API_KEY    = os.environ.get("GMAPS_API_KEY", "")
PLANNER_URL      = os.environ.get("PLANNER_URL", "https://redstone-planner-production.up.railway.app")
DVLA_API_KEY     = os.environ.get("DVLA_API_KEY", "")
TEST_MODE        = os.environ.get("TEST_MODE", "false").lower() == "true"
TEST_EMAIL       = os.environ.get("TEST_EMAIL", "dave@redstonepdm.com")

UPLOAD_FOLDER = "/tmp/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── Contractor Profiles ───────────────────────────────────────────────────────

CONTRACTORS = {
    "dave_duppa": {
        "name": "Dave Duppa", "email": "daveduppa@redstonepdm.com",
        "phone": "07897509190", "address": "9 Canberra Gardens, Cranfield, MK43 1AQ",
        "utr": None, "ni": None, "sort_code": None, "account_no": None,
        "day_rate": 250, "overtime_rate": 25.0, "redstone_vehicle": True,
        "van_reg": "EA19ECD", "mileage_rate": 0, "redstone_card": True,
        "cis_rate": 0, "password": "Duppa2024!",
    },
    "mark_ashpool": {
        "name": "Mark Ashpool", "email": "markashpool48@gmail.com",
        "phone": "07513628195", "address": "9 Exebridge, Furzton, Milton Keynes, MK4 1LH",
        "utr": "1781674128", "ni": "NZ020247B", "sort_code": "11-04-48", "account_no": "25017867",
        "day_rate": 186, "overtime_rate": 18.6, "redstone_vehicle": False,
        "van_reg": "KR17XHV", "mileage_rate": 0.25, "redstone_card": True,
        "cis_rate": 0.20, "password": "Ashpool2024!",
    },
    "richard_chambers": {
        "name": "Richard Chambers", "email": "rchambers87@hotmail.com",
        "phone": "07595052492", "address": "3 Argonaute Wharf, Brooklands, Milton Keynes, MK10 7LX",
        "utr": "4334475511", "ni": "JZ627889B", "sort_code": "04-00-04", "account_no": "15204776",
        "day_rate": 180, "overtime_rate": 18.0, "redstone_vehicle": True,
        "van_reg": "BP63MBO", "mileage_rate": 0, "redstone_card": True,
        "cis_rate": 0.20, "password": "Chambers2024!",
    },
    "ash_everett": {
        "name": "Ashley Everett", "email": "asheverett03@gmail.com",
        "phone": "07917524608", "address": "30 Mill Close, Elsenham, Bishops Stortford, CM22 6EG",
        "utr": "6310398358", "ni": "JZ081305B", "sort_code": "11-01-66", "account_no": "13761765",
        "day_rate": 186, "overtime_rate": 18.6, "redstone_vehicle": True,
        "van_reg": "YT66NDJ", "mileage_rate": 0, "redstone_card": True,
        "cis_rate": 0.20, "password": "Everett2024!",
    },
    "cassius_kwarteng": {
        "name": "Cassius Kwarteng", "email": "kwrtng@talktalk.net",
        "phone": "07487698681", "address": "2 Hartley, Great Linford, Milton Keynes, MK14 5EB",
        "utr": "7586294311", "ni": "PW606883D", "sort_code": "77-21-10", "account_no": "25644560",
        "day_rate": 180, "overtime_rate": 18.0, "redstone_vehicle": True,
        "van_reg": "YT65TKX", "mileage_rate": 0, "redstone_card": True,
        "cis_rate": 0.20, "password": "Cassius2024!",
    },
    "dave_lefevre": {
        "name": "Dave Lefevre", "email": "bigdavelef@gmail.com",
        "phone": "07766351261", "address": "Flat above 80 Aylesbury Street, Fenny Stratford, Bletchley, MK2 2BA",
        "utr": "8861831155", "ni": "NZ148785C", "sort_code": "60-14-55", "account_no": "60915188",
        "day_rate": 200, "overtime_rate": 20.0, "redstone_vehicle": True,
        "van_reg": "AK17WTV", "mileage_rate": 0, "redstone_card": True,
        "cis_rate": 0.20, "password": "Lefevre2024!",
    },
    "aziz_rehman": {
        "name": "Aziz Rehman", "email": "HRehman@hotmail.co.uk",
        "phone": "07982904246", "address": "118 Trafalgar Road, Moseley, Birmingham, B13 8BX",
        "utr": "5614567336", "ni": "JG075656A", "sort_code": "77-85-59", "account_no": "16656868",
        "day_rate": 200, "overtime_rate": 20.0, "redstone_vehicle": False,
        "van_reg": "HA51ZEZ", "mileage_rate": 0.25, "redstone_card": True,
        "cis_rate": 0.20, "password": "Aziz2024!",
    },
    "james_rutland": {
        "name": "James Rutland", "email": "rutters1983@hotmail.co.uk",
        "phone": "07500900582", "address": "40 Milecastle, Bancroft, Milton Keynes, MK13 0QN",
        "utr": "7891847516", "ni": "JJ092921B", "sort_code": "60-20-34", "account_no": "41002547",
        "day_rate": 180, "overtime_rate": 18.0, "redstone_vehicle": False,
        "van_reg": "R12UTY", "mileage_rate": 0.25, "redstone_card": False,
        "cis_rate": 0.20, "password": "Rutland2024!",
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

        CREATE TABLE IF NOT EXISTS odometer_readings (
            id              SERIAL PRIMARY KEY,
            contractor_key  TEXT NOT NULL,
            van_reg         TEXT,
            reading_date    DATE NOT NULL,
            week_commencing DATE NOT NULL,
            odometer        INTEGER NOT NULL,
            miles_since_last INTEGER,
            job_miles_that_week NUMERIC(8,1),
            variance        NUMERIC(8,1),
            recorded_at     TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS profile_change_requests (
            id              SERIAL PRIMARY KEY,
            contractor_key  TEXT NOT NULL,
            field_name      TEXT NOT NULL,
            old_value       TEXT,
            new_value       TEXT NOT NULL,
            reason          TEXT,
            status          TEXT DEFAULT 'pending',
            requested_at    TIMESTAMPTZ DEFAULT NOW(),
            reviewed_at     TIMESTAMPTZ,
            reviewed_by     TEXT
        );

        CREATE TABLE IF NOT EXISTS contractors_db (
            contractor_key  TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            email           TEXT,
            phone           TEXT,
            address         TEXT,
            utr             TEXT,
            ni              TEXT,
            sort_code       TEXT,
            account_no      TEXT,
            day_rate        NUMERIC(8,2),
            overtime_rate   NUMERIC(8,2),
            redstone_vehicle BOOLEAN DEFAULT TRUE,
            van_reg         TEXT,
            mileage_rate    NUMERIC(5,3) DEFAULT 0,
            redstone_card   BOOLEAN DEFAULT TRUE,
            cis_rate        NUMERIC(5,3) DEFAULT 0.20,
            password        TEXT,
            status          TEXT DEFAULT 'active',
            archived_at     TIMESTAMPTZ,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS vehicles (
            id                    SERIAL PRIMARY KEY,
            van_reg               TEXT UNIQUE NOT NULL,
            make_model            TEXT,
            year                  INTEGER,
            contractor_key        TEXT,
            redstone_vehicle      BOOLEAN DEFAULT TRUE,
            current_mileage       INTEGER DEFAULT 0,
            last_service_mileage  INTEGER DEFAULT 0,
            service_interval_miles INTEGER DEFAULT 12000,
            mot_expiry            DATE,
            mot_status            TEXT DEFAULT 'unknown',
            mot_checked_at        TIMESTAMPTZ,
            notes                 TEXT,
            created_at            TIMESTAMPTZ DEFAULT NOW(),
            updated_at            TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS contractor_weekly_notes (
            id              SERIAL PRIMARY KEY,
            contractor_key  TEXT NOT NULL,
            week_commencing DATE NOT NULL,
            note            TEXT NOT NULL,
            created_by      TEXT DEFAULT 'admin',
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (contractor_key, week_commencing)
        );

        CREATE TABLE IF NOT EXISTS week_schedules (
            id              SERIAL PRIMARY KEY,
            week_commencing DATE UNIQUE NOT NULL,
            status          TEXT DEFAULT 'draft',
            published_at    TIMESTAMPTZ,
            published_by    TEXT,
            reopened_at     TIMESTAMPTZ,
            notes           TEXT,
            created_at      TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # Seed vehicles if empty
    cur.execute("SELECT COUNT(*) as c FROM vehicles")
    if cur.fetchone()["c"] == 0:
        vehicles = [
            ("EA19ECD", "Ford Transit Custom", 2019, "dave_duppa",      True),
            ("KR17XHV", "Ford Transit Custom", 2017, "mark_ashpool",    False),
            ("BP63MBO", "Ford Transit Custom", 2013, "richard_chambers",True),
            ("YT66NDJ", "Ford Transit Custom", 2016, "ash_everett",     True),
            ("YT65TKX", "Ford Transit Custom", 2015, "cassius_kwarteng",True),
            ("AK17WTV", "Ford Transit Custom", 2017, "dave_lefevre",    True),
            ("HA51ZEZ", "VW Caddy",            2001, "aziz_rehman",     False),
            ("R12UTY",  "Ford Ranger",          2012, "james_rutland",  False),
        ]
        for v in vehicles:
            cur.execute("""
                INSERT INTO vehicles (van_reg, make_model, year, contractor_key, redstone_vehicle)
                VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING
            """, v)

    conn.commit()
    cur.close()
    conn.close()


def get_contractor(key):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM contractors_db WHERE contractor_key = %s AND status = 'active'", (key,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return dict(row)
    except Exception as e:
        print(f"DB contractor lookup failed: {e}")
    return CONTRACTORS.get(key)


def get_all_contractors(include_archived=False):
    try:
        conn = get_db()
        cur = conn.cursor()
        if include_archived:
            cur.execute("SELECT * FROM contractors_db ORDER BY status, name")
        else:
            cur.execute("SELECT * FROM contractors_db WHERE status = 'active' ORDER BY name")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {r["contractor_key"]: dict(r) for r in rows}
    except Exception as e:
        print(f"DB contractors lookup failed: {e}")
        return CONTRACTORS


# ── Auth ──────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "contractor_key" not in session:
            return redirect(url_for("login"))
        if session.get("role") == "contractor":
            now = datetime.now()
            login_time = session.get("login_time")
            if login_time:
                logged_in_at = datetime.fromisoformat(login_time)
                today_1am = now.replace(hour=1, minute=0, second=0, microsecond=0)
                if logged_in_at < today_1am and now >= today_1am:
                    session.clear()
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


# ── DVLA MOT Lookup ───────────────────────────────────────────────────────────

def lookup_mot(reg):
    """Check MOT status via DVLA API. Returns dict with expiry, status, etc."""
    if not DVLA_API_KEY:
        return {"status": "unknown", "expiry": None, "error": "No API key"}
    try:
        reg_clean = reg.replace(" ", "").upper()
        url = "https://driver-vehicle-licensing.api.gov.uk/vehicle-enquiry/v1/vehicles"
        headers = {
            "x-api-key": DVLA_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {"registrationNumber": reg_clean}
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        if r.status_code == 200:
            data = r.json()
            mot_expiry_str = data.get("motExpiryDate")  # format: YYYY-MM-DD
            mot_expiry = None
            mot_status = "unknown"
            if mot_expiry_str:
                mot_expiry = datetime.strptime(mot_expiry_str, "%Y-%m-%d").date()
                today = date.today()
                days_left = (mot_expiry - today).days
                if days_left < 0:
                    mot_status = "expired"
                elif days_left <= 30:
                    mot_status = "due_soon"
                else:
                    mot_status = "valid"
            return {
                "status": mot_status,
                "expiry": mot_expiry,
                "days_left": (mot_expiry - date.today()).days if mot_expiry else None,
                "make": data.get("make", ""),
                "colour": data.get("colour", ""),
                "year": data.get("yearOfManufacture"),
            }
        else:
            return {"status": "error", "expiry": None, "error": f"DVLA returned {r.status_code}"}
    except Exception as e:
        return {"status": "error", "expiry": None, "error": str(e)}


# ── Mileage Calculation ───────────────────────────────────────────────────────

def calculate_mileage(origin_address, destination_postcode):
    if not GMAPS_API_KEY:
        return 0, 0
    try:
        url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        params = {"origins": origin_address, "destinations": destination_postcode + ", UK",
                  "units": "imperial", "key": GMAPS_API_KEY}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        element = data["rows"][0]["elements"][0]
        if element["status"] != "OK":
            return 0, 0
        outbound_miles = element["distance"]["value"] / 1609.34
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
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm,
                            leftMargin=15*mm, rightMargin=15*mm)
    styles = getSampleStyleSheet()
    story = []
    label_style   = ParagraphStyle("label", fontSize=8, textColor=REDSTONE_GREY, fontName="Helvetica-Bold", spaceAfter=1)
    value_style   = ParagraphStyle("value", fontSize=10, textColor=REDSTONE_DARK, fontName="Helvetica", spaceAfter=6)
    head_style    = ParagraphStyle("head", fontSize=16, textColor=REDSTONE_DARK, fontName="Helvetica-Bold")
    section_style = ParagraphStyle("section", fontSize=11, textColor=colors.white, fontName="Helvetica-Bold",
                                    backColor=REDSTONE_DARK, leftIndent=4, spaceAfter=0, spaceBefore=8)
    header_data = [[
        Paragraph("Redstone PDM", head_style),
        Paragraph(f"Field Engineer Job Card<br/><font size=9 color=grey>{card['card_date'].strftime('%A, %d %B %Y')}</font>", head_style),
    ]]
    header_table = Table(header_data, colWidths=[85*mm, 95*mm])
    header_table.setStyle(TableStyle([("ALIGN", (1,0),(1,0),"RIGHT"), ("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=2, color=REDSTONE_RED, spaceAfter=8))
    def field_row(label, value):
        return [Paragraph(label, label_style), Paragraph(str(value) if value else "—", value_style)]
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
        ("BACKGROUND",(0,0),(0,-1),REDSTONE_LIGHT), ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0e0e0")),
        ("LEFTPADDING",(0,0),(-1,-1),6), ("RIGHTPADDING",(0,0),(-1,-1),6),
        ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
    ]))
    story.append(details)
    story.append(Paragraph(" LABOUR", section_style))
    story.append(Spacer(1, 4))
    labour = Table([
        field_row("LABOUR TYPE", card["labour_type"]),
        field_row("BASE DAY RATE", f"£{card['base_day_rate']:.2f}"),
        field_row("OVERTIME HOURS", f"{card['overtime_hours']} hrs @ £{card['overtime_rate']:.2f}/hr" if card["overtime_hours"] else "None"),
        field_row("TOTAL LABOUR COST", f"£{card['labour_cost']:.2f}"),
    ], colWidths=[55*mm, 125*mm])
    labour.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(0,-1),REDSTONE_LIGHT), ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0e0e0")),
        ("LEFTPADDING",(0,0),(-1,-1),6), ("RIGHTPADDING",(0,0),(-1,-1),6),
        ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
    ]))
    story.append(labour)
    materials = card.get("materials_json") or []
    if materials:
        story.append(Paragraph(" MATERIALS", section_style))
        story.append(Spacer(1, 4))
        mat_data = [["#","Description","Qty","Unit Cost","Total","Payment"]]
        for i, m in enumerate(materials, 1):
            mat_data.append([str(i), m.get("description",""), str(m.get("qty","")),
                             f"£{float(m.get('unit_cost',0)):.2f}", f"£{float(m.get('total',0)):.2f}",
                             m.get("payment","Redstone Card")])
        mat_table = Table(mat_data, colWidths=[8*mm,60*mm,15*mm,22*mm,22*mm,33*mm])
        mat_table.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),REDSTONE_DARK), ("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"), ("FONTSIZE",(0,0),(-1,-1),8),
            ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0e0e0")),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, REDSTONE_LIGHT]),
            ("LEFTPADDING",(0,0),(-1,-1),4), ("RIGHTPADDING",(0,0),(-1,-1),4),
            ("TOPPADDING",(0,0),(-1,-1),3), ("BOTTOMPADDING",(0,0),(-1,-1),3),
        ]))
        story.append(mat_table)
    if contractor["mileage_rate"] > 0:
        story.append(Paragraph(" TRAVEL & MILEAGE", section_style))
        story.append(Spacer(1, 4))
        travel = Table([
            field_row("TOTAL MILEAGE", f"{card['mileage_miles']} miles (round trip)"),
            field_row("MILEAGE RATE", f"{int(contractor['mileage_rate']*100)}p per mile"),
            field_row("MILEAGE COST", f"£{card['mileage_cost']:.2f}"),
            field_row("ODOMETER READING", str(card.get("odometer","—"))),
        ], colWidths=[55*mm, 125*mm])
        travel.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(0,-1),REDSTONE_LIGHT),
            ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0e0e0")),
            ("LEFTPADDING",(0,0),(-1,-1),6), ("RIGHTPADDING",(0,0),(-1,-1),6),
            ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
        ]))
        story.append(travel)
    if card.get("parking_cost", 0):
        story.append(Paragraph(" PARKING", section_style))
        story.append(Spacer(1, 4))
        parking = Table([field_row("PARKING COST", f"£{card['parking_cost']:.2f}")], colWidths=[55*mm, 125*mm])
        parking.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(0,-1),REDSTONE_LIGHT),
            ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0e0e0")),
            ("LEFTPADDING",(0,0),(-1,-1),6),
            ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
        ]))
        story.append(parking)
    doc.build(story)
    buf.seek(0)
    return buf.read()


def build_invoice_pdf(card, contractor):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm,
                            leftMargin=15*mm, rightMargin=15*mm)
    styles = getSampleStyleSheet()
    story = []
    label_style = ParagraphStyle("label", fontSize=8, textColor=REDSTONE_GREY, fontName="Helvetica-Bold")
    value_style = ParagraphStyle("value", fontSize=10, textColor=REDSTONE_DARK, fontName="Helvetica")
    head_style  = ParagraphStyle("head", fontSize=16, textColor=REDSTONE_DARK, fontName="Helvetica-Bold")
    story.append(Paragraph("Redstone PDM", head_style))
    story.append(Paragraph("Reverse Self-Billing Invoice", ParagraphStyle("sub", fontSize=12, textColor=REDSTONE_GREY, fontName="Helvetica")))
    story.append(HRFlowable(width="100%", thickness=2, color=REDSTONE_RED, spaceAfter=8))
    parties = Table([[
        Paragraph(f"<b>Engineer:</b> {contractor['name']}<br/>{contractor['address']}<br/>"
                  f"UTR: {contractor.get('utr','—')}<br/>NI: {contractor.get('ni','—')}<br/>"
                  f"Bank: {contractor.get('sort_code','—')} / {contractor.get('account_no','—')}", value_style),
        Paragraph("<b>Bill to:</b><br/>Redstone PDM Ltd<br/>9 Canberra Gardens<br/>Cranfield<br/>MK43 1AQ<br/>"
                  "VAT Reg: 248 5387 69<br/>Company: 10070131", value_style),
    ]], colWidths=[90*mm, 90*mm])
    story.append(parties)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e0e0e0"), spaceAfter=8))
    def row(label, value):
        return [Paragraph(f"<b>{label}</b>", label_style), Paragraph(str(value) if value else "—", value_style)]
    summary = Table([
        row("JOB NUMBER", card["job_id"]),
        row("DATE", card["card_date"].strftime("%A, %d %B %Y")),
        row("SITE / LOCATION", f"{card['site_name']} {card['postcode']}"),
        row("DESCRIPTION OF WORKS", card["description_actual"]),
    ], colWidths=[55*mm, 125*mm])
    summary.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(0,-1),REDSTONE_LIGHT), ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0e0e0")),
        ("LEFTPADDING",(0,0),(-1,-1),6), ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
    ]))
    story.append(summary)
    story.append(Spacer(1, 8))
    cost_data = [["Item","Amount"]]
    cost_data.append(["Labour", f"£{card['labour_cost']:.2f}"])
    if card.get("mileage_cost", 0):
        cost_data.append([f"Mileage ({card['mileage_miles']} miles @ {int(contractor['mileage_rate']*100)}p/mile)", f"£{card['mileage_cost']:.2f}"])
    if card.get("parking_cost", 0):
        cost_data.append(["Parking", f"£{card['parking_cost']:.2f}"])
    if card.get("reimburse_total", 0):
        cost_data.append(["Materials (To Be Reimbursed)", f"£{card['reimburse_total']:.2f}"])
    cost_table = Table(cost_data, colWidths=[140*mm, 40*mm])
    cost_table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),REDSTONE_DARK), ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"), ("FONTSIZE",(0,0),(-1,-1),9),
        ("ALIGN",(1,0),(1,-1),"RIGHT"), ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0e0e0")),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, REDSTONE_LIGHT]),
        ("LEFTPADDING",(0,0),(-1,-1),6), ("RIGHTPADDING",(0,0),(-1,-1),6),
        ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
    ]))
    story.append(cost_table)
    story.append(Spacer(1, 4))
    totals_data = [["Gross Invoice Value", f"£{card['invoice_total']:.2f}"]]
    if contractor["cis_rate"] > 0:
        totals_data.append([f"CIS Deduction ({int(contractor['cis_rate']*100)}%)", f"-£{card['cis_deduction']:.2f}"])
        totals_data.append(["Net Payment to Contractor", f"£{card['net_payment']:.2f}"])
    totals_table = Table(totals_data, colWidths=[140*mm, 40*mm])
    totals_table.setStyle(TableStyle([
        ("FONTNAME",(0,0),(-1,-1),"Helvetica-Bold"), ("FONTSIZE",(0,0),(-1,-1),10),
        ("ALIGN",(1,0),(1,-1),"RIGHT"),
        ("BACKGROUND",(-1,-1),(-1,-1),REDSTONE_DARK), ("TEXTCOLOR",(-1,-1),(-1,-1),colors.white),
        ("BACKGROUND",(0,-1),(0,-1),REDSTONE_DARK), ("TEXTCOLOR",(0,-1),(0,-1),colors.white),
        ("TOPPADDING",(0,0),(-1,-1),5), ("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("LEFTPADDING",(0,0),(-1,-1),6), ("RIGHTPADDING",(0,0),(-1,-1),6),
        ("LINEABOVE",(0,0),(-1,0),1,REDSTONE_RED),
    ]))
    story.append(totals_table)
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
    if not SENDGRID_API_KEY:
        print("No SendGrid API key — email skipped")
        return False
    try:
        if isinstance(to_addresses, str):
            to_addresses = [to_addresses]
        if TEST_MODE:
            print(f"TEST MODE: redirecting email (was to {to_addresses}) to {TEST_EMAIL}")
            subject = f"[TEST] {subject}"
            to_addresses = [TEST_EMAIL]
        message = Mail(from_email=FROM_EMAIL, to_emails=to_addresses,
                       subject=subject, html_content=body_html)
        if attachments:
            for filename, data in attachments:
                encoded = base64.b64encode(data).decode()
                attachment = Attachment(FileContent(encoded), FileName(filename),
                                        FileType("application/pdf"), Disposition("attachment"))
                message.add_attachment(attachment)
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"EMAIL SENT: status={response.status_code} to={to_addresses}")
        return response.status_code in (200, 202)
    except Exception as e:
        print(f"EMAIL ERROR: {type(e).__name__}: {e}")
        import traceback; traceback.print_exc()
        return False


# ── Routes: Public ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "contractor_key" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        name_or_user = request.form.get("name", "") or request.form.get("username", "")
        if name_or_user.lower().strip() == "admin" and \
           request.form.get("password") == os.environ.get("ADMIN_PASSWORD", "redstone2024"):
            session["role"] = "admin"
            session["contractor_key"] = "admin"
            session.permanent = False
            return redirect(url_for("admin_home"))
        password = request.form.get("password", "")
        name_input = request.form.get("name", "").strip().lower()
        all_contractors = get_all_contractors()
        for key, c in all_contractors.items():
            if c["name"].lower() == name_input and c.get("password") == password:
                session["contractor_key"] = key
                session["role"] = "contractor"
                session.permanent = True
                session["login_time"] = datetime.now().isoformat()
                return redirect(url_for("dashboard"))
        error = "Name or password not recognised."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Routes: Engineer ──────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    if session.get("role") == "admin":
        return redirect(url_for("admin_home"))
    key = session["contractor_key"]
    contractor = CONTRACTORS[key]
    conn = get_db()
    cur = conn.cursor()
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    # Only show jobs if this week is published
    cur.execute("SELECT status FROM week_schedules WHERE week_commencing = %s", (week_start,))
    sched = cur.fetchone()
    week_published = sched and sched["status"] == "published"

    jobs = []
    if week_published:
        cur.execute("""
            SELECT a.id as alloc_id, a.job_id, a.day_date, a.notes as alloc_notes,
                   j.pub_name, j.postcode, j.description, j.trade_type, j.due_date,
                   j.tab, j.sub_tab,
                   jc.id as card_id, jc.status as card_status
            FROM allocations a
            JOIN jobs j ON j.job_id = a.job_id
            LEFT JOIN job_cards jc ON jc.job_id = a.job_id
                AND jc.contractor_key = %s AND jc.card_date = a.day_date
            WHERE a.contractor = %s
            AND a.day_date BETWEEN %s AND %s
            ORDER BY a.day_date, a.id
        """, (key, contractor["name"], week_start, week_end))
        jobs = cur.fetchall()

    cur.execute("""
        SELECT * FROM job_cards WHERE contractor_key = %s
        ORDER BY submitted_at DESC LIMIT 10
    """, (key,))
    recent_cards = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("dashboard.html", contractor=contractor, jobs=jobs,
                           recent_cards=recent_cards, week_start=week_start,
                           today=today, week_published=week_published)


@app.route("/job/<job_id>/<card_date>")
@login_required
def job_card_form(job_id, card_date):
    key = session["contractor_key"]
    contractor = CONTRACTORS[key]
    job_id = str(job_id)  # ensure string, never int
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM jobs WHERE job_id::text = %s", (job_id,))
    job = cur.fetchone()
    cur.execute("""
        SELECT * FROM job_cards
        WHERE job_id = %s AND contractor_key = %s AND card_date = %s
    """, (job_id, key, card_date))
    existing_card = cur.fetchone()

    # Get MOT expiry for this contractor's van
    cur.execute("SELECT mot_expiry, mot_status FROM vehicles WHERE contractor_key = %s", (key,))
    vehicle = cur.fetchone()
    cur.close()
    conn.close()
    if not job:
        return "Job not found", 404
    mileage_miles = 0
    if contractor["mileage_rate"] > 0 and job.get("postcode"):
        mileage_miles, _ = calculate_mileage(contractor["address"], job["postcode"])
    return render_template("job_card.html", contractor=contractor, job=job,
                           card_date=card_date, mileage_miles=mileage_miles,
                           existing_card=existing_card, gmaps_key=GMAPS_API_KEY,
                           vehicle=vehicle)


@app.route("/job/<job_id>/<card_date>/submit", methods=["POST"])
@login_required
def submit_job_card(job_id, card_date):
    key = session["contractor_key"]
    contractor = CONTRACTORS[key]
    time_start   = request.form.get("time_start", "")
    time_finish  = request.form.get("time_finish", "")
    hours        = float(request.form.get("hours_on_site", 0) or 0)
    overtime_h   = float(request.form.get("overtime_hours", 0) or 0)
    odometer     = request.form.get("odometer") or None
    only_job     = request.form.get("only_job_today") == "yes"
    desc_actual  = request.form.get("description_actual", "")
    desc_planned = request.form.get("description_planned", "")
    mileage_miles = float(request.form.get("total_miles", 0) or 0)
    card_date_str = request.form.get("card_date", card_date)
    journey_json  = request.form.get("journey_json", "[]")
    try:
        journey_legs = json.loads(journey_json)
    except Exception:
        journey_legs = []
    billable_miles = sum(float(l.get("miles",0)) for l in journey_legs if l.get("type") != "nextjob")
    if journey_legs:
        mileage_miles = round(billable_miles, 1)
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
    # ── Labour calculation by job type ──────────────────────────────────────
    # Detect job type from job_id prefix
    job_prefix = str(job_id)[:4] if job_id else "1000"
    is_ppm = job_prefix == "2000"  # PPM jobs always full day rate
    # 1000/3000 = reactive hourly, 2000 = PPM full day, 5000/8000 = quoted hourly

    if is_ppm:
        # PPM: full day rate + any logged overtime
        base_labour   = float(contractor["day_rate"])
        labour_type   = "PPM Full Day"
    else:
        # Reactive (1000/3000) and Quoted (5000): hourly rate = day_rate ÷ 10
        hourly_rate   = float(contractor["day_rate"]) / 10
        base_labour   = round(hours * hourly_rate, 2)
        labour_type   = f"Hourly ({hours}hrs × £{hourly_rate:.2f}/hr)"

    # Overtime: anything logged above 8hrs on site
    overtime_cost = round(overtime_h * float(contractor["overtime_rate"]), 2)
    labour_cost   = round(base_labour + overtime_cost, 2)
    mileage_cost  = round(mileage_miles * contractor["mileage_rate"], 2)
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
        materials.append({"description": desc, "qty": qty, "unit_cost": unit_cost, "total": total, "payment": payment})
        if payment != "Redstone Card":
            reimburse_total += total
    materials_total = sum(m["total"] for m in materials)
    reimburse_total_all = reimburse_total + reimburse_parking
    invoice_total = labour_cost + mileage_cost + reimburse_total_all
    cis_deduction = round(labour_cost * contractor["cis_rate"], 2)
    net_payment   = round(invoice_total - cis_deduction, 2)
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
        "time_start": time_start, "time_finish": time_finish,
        "hours_on_site": hours, "labour_type": f"{labour_type} + {overtime_h}hrs OT" if overtime_h else labour_type,
        "base_day_rate": contractor["day_rate"], "overtime_hours": overtime_h,
        "overtime_rate": contractor["overtime_rate"], "labour_cost": labour_cost,
        "mileage_miles": mileage_miles, "mileage_cost": mileage_cost,
        "parking_cost": parking, "materials_json": materials,
        "materials_total": materials_total, "reimburse_total": reimburse_total,
        "odometer": odometer, "only_job_today": only_job,
        "invoice_total": invoice_total, "cis_deduction": cis_deduction,
        "net_payment": net_payment, "photo_paths": photo_paths,
        "parking_photo_path": parking_photo_path, "receipt_photo_paths": receipt_photos,
    }
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
            %(contractor_key)s,%(job_id)s,%(card_date)s,%(site_name)s,%(postcode)s,
            %(description_planned)s,%(description_actual)s,%(time_start)s,%(time_finish)s,
            %(hours_on_site)s,%(labour_type)s,%(base_day_rate)s,%(overtime_hours)s,%(overtime_rate)s,
            %(labour_cost)s,%(mileage_miles)s,%(mileage_cost)s,%(parking_cost)s,
            %(materials_json)s,%(materials_total)s,%(reimburse_total)s,%(odometer)s,
            %(only_job_today)s,%(invoice_total)s,%(cis_deduction)s,%(net_payment)s,
            %(photo_paths)s,%(parking_photo_path)s,%(receipt_photo_paths)s,'submitted'
        ) ON CONFLICT DO NOTHING RETURNING id
    """, {**card, "contractor_key": key, "materials_json": json.dumps(materials),
          "photo_paths": json.dumps(photo_paths), "receipt_photo_paths": json.dumps(receipt_photos)})
    result = cur.fetchone()
    conn.commit()
    try:
        loc_cur = conn.cursor()
        # If contractor travelled home, clear location so next card starts from home
        went_home = any(l.get("type") in ("home",) for l in journey_legs)
        if went_home:
            # Reset to home address
            new_location = contractor["address"]
            new_job_id = None
        else:
            new_location = job.get("postcode","") + " " + job.get("pub_name","")
            new_job_id = job_id
        loc_cur.execute("""
            INSERT INTO contractor_locations (contractor_key, last_location, last_job_id, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (contractor_key) DO UPDATE
            SET last_location=EXCLUDED.last_location, last_job_id=EXCLUDED.last_job_id, updated_at=EXCLUDED.updated_at
        """, (key, new_location, new_job_id))
        conn.commit()
        loc_cur.close()
    except Exception as e:
        print(f"Could not save last location: {e}")
    # Update vehicle mileage if odometer submitted
    if odometer:
        try:
            conn.cursor().execute(
                "UPDATE vehicles SET current_mileage=%s, updated_at=NOW() WHERE contractor_key=%s",
                (int(odometer), key))
            conn.commit()
        except Exception:
            pass
    job_card_pdf = build_job_card_pdf(card, contractor)
    invoice_pdf  = build_invoice_pdf(card, contractor)
    filename_base = f"{contractor['name'].replace(' ','_')}_{job_id}_{card_date}"
    send_email(
        to_addresses=[ACCOUNTS_EMAIL, contractor["email"]],
        subject=f"Redstone PDM — Invoice: {contractor['name']} | {job_id} | {card_date}",
        body_html=f"""
            <p>Please find attached the self-billing invoice for:</p>
            <ul>
                <li><b>Engineer:</b> {contractor['name']}</li>
                <li><b>Job:</b> {job_id} — {card.get('site_name','')}</li>
                <li><b>Date:</b> {card_date}</li>
                <li><b>Invoice Total:</b> £{invoice_total:.2f}</li>
                <li><b>CIS Deduction:</b> £{cis_deduction:.2f}</li>
                <li><b>Net Payment:</b> £{net_payment:.2f}</li>
            </ul>
        """,
        attachments=[(f"{filename_base}_invoice.pdf", invoice_pdf)]
    )
    if result:
        card_id = result["id"]
        pdf_path = os.path.join(UPLOAD_FOLDER, f"{filename_base}_jobcard.pdf")
        with open(pdf_path, "wb") as f:
            f.write(job_card_pdf)
        cur.execute("UPDATE job_cards SET notes=%s WHERE id=%s", (pdf_path, card_id))
        conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("card_submitted", job_id=job_id, card_date=card_date))


@app.route("/submitted/<job_id>/<card_date>")
@login_required
def card_submitted(job_id, card_date):
    key = session["contractor_key"]
    contractor = CONTRACTORS[key]
    return render_template("submitted.html", contractor=contractor, job_id=job_id, card_date=card_date)


@app.route("/profile")
@login_required
def profile():
    key = session["contractor_key"]
    contractor = CONTRACTORS[key]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM profile_change_requests WHERE contractor_key=%s ORDER BY requested_at DESC LIMIT 10", (key,))
    changes = cur.fetchall()
    cur.execute("SELECT mot_expiry, mot_status, current_mileage, make_model FROM vehicles WHERE contractor_key=%s", (key,))
    vehicle = cur.fetchone()
    cur.close()
    conn.close()
    return render_template("profile.html", contractor=contractor, changes=changes, vehicle=vehicle)


@app.route("/profile/request_change", methods=["POST"])
@login_required
def request_profile_change():
    key = session["contractor_key"]
    contractor = CONTRACTORS[key]
    data = request.get_json()
    field = data.get("field")
    new_value = data.get("new_value", "").strip()
    reason = data.get("reason", "").strip()
    if not field or not new_value:
        return jsonify({"ok": False, "error": "Missing field or value"})
    field_map = {
        "address": ("Home Address", contractor.get("address", "")),
        "phone": ("Phone Number", contractor.get("phone", "")),
        "email": ("Email Address", contractor.get("email", "")),
        "account_no": ("Bank Account Number", contractor.get("account_no", "")),
        "sort_code": ("Sort Code", contractor.get("sort_code", "")),
    }
    if field not in field_map:
        return jsonify({"ok": False, "error": "Invalid field"})
    label, old_value = field_map[field]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO profile_change_requests (contractor_key,field_name,old_value,new_value,reason) VALUES (%s,%s,%s,%s,%s)",
                (key, label, old_value, new_value, reason))
    conn.commit()
    send_email(to_addresses=[ACCOUNTS_EMAIL],
               subject=f"Profile Change Request — {contractor['name']} — {label}",
               body_html=f"<p><b>{contractor['name']}</b> requested change: {label} → {new_value}</p>")
    cur.close()
    conn.close()
    return jsonify({"ok": True})


# ── Routes: Admin Home ────────────────────────────────────────────────────────

@app.route("/admin")
@admin_required
def admin_home():
    conn = get_db()
    cur = conn.cursor()
    pending_cards = 0
    pending_changes = 0
    mot_alerts = 0
    week_status = "draft"
    try:
        cur.execute("SELECT COUNT(*) as c FROM job_cards WHERE status='submitted'")
        pending_cards = cur.fetchone()["c"]
    except Exception: conn.rollback()
    try:
        cur.execute("SELECT COUNT(*) as c FROM profile_change_requests WHERE status='pending'")
        pending_changes = cur.fetchone()["c"]
    except Exception: conn.rollback()
    try:
        cur.execute("SELECT COUNT(*) as c FROM vehicles WHERE mot_status IN ('expired','due_soon')")
        mot_alerts = cur.fetchone()["c"]
    except Exception: conn.rollback()
    try:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        cur.execute("SELECT status FROM week_schedules WHERE week_commencing=%s", (week_start,))
        sched = cur.fetchone()
        week_status = sched["status"] if sched else "draft"
    except Exception: conn.rollback()
    cur.close()
    conn.close()
    return render_template("admin_home.html",
                           pending_cards=pending_cards,
                           pending_changes=pending_changes,
                           mot_alerts=mot_alerts,
                           week_status=week_status,
                           planner_url=PLANNER_URL)


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    return redirect(url_for("admin_home"))


# ── Routes: Admin Job Cards ───────────────────────────────────────────────────

@app.route("/admin/jobcards")
@admin_required
def admin_jobcards():
    conn = get_db()
    cur = conn.cursor()
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    engineer_overview = []
    cards = []
    overdue = []
    missing_cards = []

    try:
        cur.execute("""
            SELECT
                a.contractor,
                COUNT(DISTINCT a.id) as allocated,
                COUNT(DISTINCT jc.id) as submitted,
                SUM(jc.invoice_total) as week_total,
                SUM(jc.net_payment) as week_net
            FROM allocations a
            LEFT JOIN job_cards jc ON jc.job_id = a.job_id
                AND jc.contractor_key IN (
                    SELECT contractor_key FROM contractors_db WHERE name = a.contractor
                )
                AND jc.card_date = a.day_date
            WHERE a.day_date BETWEEN %s AND %s
            GROUP BY a.contractor
            ORDER BY a.contractor
        """, (week_start, week_start + timedelta(days=6)))
        engineer_overview = cur.fetchall()
    except Exception as e:
        print(f"engineer_overview query failed: {e}")
        conn.rollback()

    try:
        cur.execute("""
            SELECT jc.*, j.pub_name, j.description as job_description
            FROM job_cards jc
            LEFT JOIN jobs j ON j.job_id = jc.job_id
            ORDER BY jc.submitted_at DESC LIMIT 100
        """)
        cards = cur.fetchall()
    except Exception as e:
        print(f"cards query failed: {e}")
        conn.rollback()

    try:
        now = datetime.now()
        saturday_6pm = week_start + timedelta(days=5, hours=18)
        cur.execute("""
            SELECT a.contractor, a.job_id, a.day_date, j.pub_name,
                   jc.id as card_id, jc.submitted_at
            FROM allocations a
            JOIN jobs j ON j.job_id = a.job_id
            LEFT JOIN job_cards jc ON jc.job_id = a.job_id
                AND jc.card_date = a.day_date
            WHERE a.day_date BETWEEN %s AND %s
            AND jc.id IS NULL
            ORDER BY a.day_date
        """, (week_start, week_start + timedelta(days=6)))
        missing_cards = cur.fetchall()
        for mc in missing_cards:
            day_dt = datetime.combine(mc["day_date"], datetime.min.time())
            hrs_since = (now - day_dt).total_seconds() / 3600
            flag = None
            if now >= saturday_6pm:
                flag = "saturday"
            elif hrs_since > 24:
                flag = "24hr"
            if flag:
                overdue.append({**dict(mc), "flag": flag, "hrs_since": round(hrs_since,1)})
    except Exception as e:
        print(f"overdue query failed: {e}")
        conn.rollback()

    cur.close()
    conn.close()
    return render_template("admin_jobcards.html", cards=cards,
                           engineer_overview=engineer_overview,
                           overdue=overdue,
                           week_start=week_start,
                           contractors=CONTRACTORS)


@app.route("/admin/approve/<int:card_id>", methods=["POST"])
@admin_required
def approve_card(card_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE job_cards SET status='approved', approved_at=NOW(), approved_by='admin' WHERE id=%s", (card_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@app.route("/card/<int:card_id>/jobcard.pdf")
@login_required
def download_job_card(card_id):
    """Download job card PDF — accessible by admin or the contractor who owns it."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM job_cards WHERE id=%s", (card_id,))
    card = cur.fetchone()
    cur.close()
    conn.close()
    if not card:
        return "Not found", 404
    # Allow admin or the owning contractor
    role = session.get("role")
    key  = session.get("contractor_key")
    if role != "admin" and card["contractor_key"] != key:
        return redirect(url_for("login"))
    contractor = CONTRACTORS.get(card["contractor_key"], {})
    pdf = build_job_card_pdf(card, contractor)
    return send_file(io.BytesIO(pdf), mimetype="application/pdf", download_name=f"jobcard_{card_id}.pdf")


# ── Routes: Admin Contractors ─────────────────────────────────────────────────

@app.route("/admin/contractors")
@admin_required
def admin_contractors():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM contractors_db ORDER BY status, name")
    contractors = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("admin_contractors.html", contractors=contractors)


@app.route("/admin/contractors/add", methods=["POST"])
@admin_required
def admin_add_contractor():
    import re
    data = request.form
    key = re.sub(r'[^a-z0-9]', '_', data.get("name","").lower().strip())
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO contractors_db (contractor_key,name,email,phone,address,utr,ni,sort_code,account_no,
            day_rate,overtime_rate,redstone_vehicle,van_reg,mileage_rate,redstone_card,cis_rate,password,status)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'active')
        ON CONFLICT (contractor_key) DO UPDATE SET name=EXCLUDED.name, email=EXCLUDED.email, updated_at=NOW()
    """, (key, data.get("name"), data.get("email"), data.get("phone"), data.get("address"),
          data.get("utr"), data.get("ni"), data.get("sort_code"), data.get("account_no"),
          float(data.get("day_rate") or 0), float(data.get("day_rate") or 0)/10,
          data.get("redstone_vehicle")=="yes", data.get("van_reg"),
          0.25 if data.get("redstone_vehicle")!="yes" else 0,
          data.get("redstone_card")=="yes", float(data.get("cis_rate") or 0.20), data.get("password")))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("admin_contractors"))


@app.route("/admin/contractors/<key>/edit", methods=["POST"])
@admin_required
def admin_edit_contractor(key):
    data = request.form
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE contractors_db SET name=%s,email=%s,phone=%s,address=%s,utr=%s,ni=%s,
            sort_code=%s,account_no=%s,day_rate=%s,overtime_rate=%s,
            redstone_vehicle=%s,van_reg=%s,mileage_rate=%s,redstone_card=%s,
            cis_rate=%s,password=%s,updated_at=NOW()
        WHERE contractor_key=%s
    """, (data.get("name"), data.get("email"), data.get("phone"), data.get("address"),
          data.get("utr"), data.get("ni"), data.get("sort_code"), data.get("account_no"),
          float(data.get("day_rate") or 0), float(data.get("day_rate") or 0)/10,
          data.get("redstone_vehicle")=="yes", data.get("van_reg"),
          0.25 if data.get("redstone_vehicle")!="yes" else 0,
          data.get("redstone_card")=="yes", float(data.get("cis_rate") or 0.20),
          data.get("password"), key))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@app.route("/admin/contractors/<key>/archive", methods=["POST"])
@admin_required
def admin_archive_contractor(key):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE contractors_db SET status='archived', archived_at=NOW() WHERE contractor_key=%s", (key,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@app.route("/admin/contractors/<key>/restore", methods=["POST"])
@admin_required
def admin_restore_contractor(key):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE contractors_db SET status='active', archived_at=NULL WHERE contractor_key=%s", (key,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


# ── Routes: Admin Profile Changes ─────────────────────────────────────────────

@app.route("/admin/profile_changes")
@admin_required
def admin_profile_changes():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM profile_change_requests WHERE status='pending' ORDER BY requested_at DESC")
    changes = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("admin_profile_changes.html", changes=changes, contractors=CONTRACTORS)


@app.route("/admin/profile_changes/<int:change_id>/<action>", methods=["POST"])
@admin_required
def review_profile_change(change_id, action):
    if action not in ("approve", "reject"):
        return jsonify({"ok": False})
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE profile_change_requests SET status=%s, reviewed_at=NOW(), reviewed_by='admin'
        WHERE id=%s RETURNING contractor_key, field_name, new_value
    """, (action + "d", change_id))
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if row and action == "approve":
        contractor = CONTRACTORS.get(row["contractor_key"], {})
        send_email(to_addresses=[contractor.get("email","")],
                   subject="Redstone PDM — Profile Change Approved",
                   body_html=f"<p>Hi {contractor.get('name','')}, your {row['field_name']} update to {row['new_value']} has been approved.</p>")
    return jsonify({"ok": True})


# ── Routes: Admin Vehicles ────────────────────────────────────────────────────

@app.route("/admin/vehicles")
@admin_required
def admin_vehicles():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT v.*, c.name as driver_name
        FROM vehicles v
        LEFT JOIN contractors_db c ON c.contractor_key = v.contractor_key
        ORDER BY v.redstone_vehicle DESC, c.name
    """)
    vehicles = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("admin_vehicles.html", vehicles=vehicles)


@app.route("/admin/vehicles/<int:vid>/refresh_mot", methods=["POST"])
@admin_required
def refresh_mot(vid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT van_reg FROM vehicles WHERE id=%s", (vid,))
    v = cur.fetchone()
    if not v:
        return jsonify({"ok": False, "error": "Not found"})
    result = lookup_mot(v["van_reg"])
    cur.execute("""
        UPDATE vehicles SET mot_expiry=%s, mot_status=%s, mot_checked_at=NOW()
        WHERE id=%s
    """, (result.get("expiry"), result.get("status","unknown"), vid))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True, **result, "expiry": str(result.get("expiry")) if result.get("expiry") else None})


@app.route("/admin/vehicles/refresh_all_mot", methods=["POST"])
@admin_required
def refresh_all_mot():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, van_reg FROM vehicles")
    vehicles = cur.fetchall()
    updated = 0
    for v in vehicles:
        result = lookup_mot(v["van_reg"])
        cur.execute("UPDATE vehicles SET mot_expiry=%s, mot_status=%s, mot_checked_at=NOW() WHERE id=%s",
                    (result.get("expiry"), result.get("status","unknown"), v["id"]))
        updated += 1
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True, "updated": updated})


@app.route("/admin/vehicles/<int:vid>/update", methods=["POST"])
@admin_required
def update_vehicle(vid):
    data = request.form
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE vehicles SET make_model=%s, year=%s, last_service_mileage=%s,
            service_interval_miles=%s, notes=%s, updated_at=NOW()
        WHERE id=%s
    """, (data.get("make_model"), data.get("year") or None,
          data.get("last_service_mileage") or 0,
          data.get("service_interval_miles") or 12000,
          data.get("notes"), vid))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


# ── Routes: Vehicle Add/Delete ───────────────────────────────────────────────

@app.route("/admin/vehicles/add", methods=["POST"])
@admin_required
def add_vehicle():
    data = request.form
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO vehicles (van_reg, make_model, year, contractor_key, redstone_vehicle,
            current_mileage, last_service_mileage, service_interval_miles, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (van_reg) DO UPDATE SET
            make_model=EXCLUDED.make_model, year=EXCLUDED.year,
            contractor_key=EXCLUDED.contractor_key,
            redstone_vehicle=EXCLUDED.redstone_vehicle,
            updated_at=NOW()
    """, (
        data.get("van_reg","").upper().replace(" ",""),
        data.get("make_model"),
        data.get("year") or None,
        data.get("contractor_key") or None,
        data.get("redstone_vehicle") == "yes",
        data.get("current_mileage") or 0,
        data.get("last_service_mileage") or 0,
        data.get("service_interval_miles") or 12000,
        data.get("notes") or None,
    ))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@app.route("/admin/vehicles/<int:vid>/delete", methods=["POST"])
@admin_required
def delete_vehicle(vid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM vehicles WHERE id=%s", (vid,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


# ── Routes: Week Schedule (Publish/Lock) ──────────────────────────────────────

@app.route("/admin/schedule/publish", methods=["POST"])
@admin_required
def publish_week():
    data = request.get_json()
    week_commencing = data.get("week_commencing")
    if not week_commencing:
        return jsonify({"ok": False, "error": "Missing week"})
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO week_schedules (week_commencing, status, published_at, published_by)
        VALUES (%s, 'published', NOW(), 'admin')
        ON CONFLICT (week_commencing) DO UPDATE
        SET status='published', published_at=NOW(), published_by='admin'
    """, (week_commencing,))
    conn.commit()

    # Send schedule emails to all engineers
    week_dt = datetime.strptime(week_commencing, "%Y-%m-%d").date()
    week_end = week_dt + timedelta(days=4)
    cur.execute("""
        SELECT a.contractor, a.job_id, a.day_date, j.pub_name, j.postcode, j.description
        FROM allocations a
        JOIN jobs j ON j.job_id = a.job_id
        WHERE a.day_date BETWEEN %s AND %s
        ORDER BY a.contractor, a.day_date
    """, (week_dt, week_end))
    allocs = cur.fetchall()

    # Group by contractor
    from collections import defaultdict
    by_contractor = defaultdict(list)
    for a in allocs:
        by_contractor[a["contractor"]].append(a)

    all_contractors = get_all_contractors()
    for cname, jobs in by_contractor.items():
        # Find contractor by name
        c = next((v for v in all_contractors.values() if v["name"] == cname), None)
        if not c or not c.get("email"):
            continue
        rows = "".join(f"<tr><td style='padding:6px;border:1px solid #ddd'>{j['day_date'].strftime('%A %d %b')}</td>"
                       f"<td style='padding:6px;border:1px solid #ddd'>{j['pub_name']}</td>"
                       f"<td style='padding:6px;border:1px solid #ddd'>{j['postcode']}</td>"
                       f"<td style='padding:6px;border:1px solid #ddd'>{j['description'][:60]}...</td></tr>"
                       for j in jobs)
        send_email(
            to_addresses=[c["email"]],
            subject=f"Redstone PDM — Your Schedule w/c {week_dt.strftime('%d %b %Y')}",
            body_html=f"""
                <p>Hi {c['name']},</p>
                <p>Your schedule for the week commencing <b>{week_dt.strftime('%d %B %Y')}</b> is now confirmed.</p>
                <table style='border-collapse:collapse;width:100%'>
                    <tr style='background:#1a2332;color:white'>
                        <th style='padding:8px'>Day</th><th style='padding:8px'>Site</th>
                        <th style='padding:8px'>Postcode</th><th style='padding:8px'>Works</th>
                    </tr>
                    {rows}
                </table>
                <p>Log in to <a href='https://redstone-pdm-jobcard.up.railway.app'>Redstone PDM</a> to complete your job cards.</p>
                <p>Redstone PDM</p>
            """
        )

    cur.close()
    conn.close()
    return jsonify({"ok": True})


@app.route("/admin/schedule/reopen", methods=["POST"])
@admin_required
def reopen_week():
    data = request.get_json()
    week_commencing = data.get("week_commencing")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE week_schedules SET status='draft', reopened_at=NOW()
        WHERE week_commencing=%s
    """, (week_commencing,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/schedule_status")
def api_schedule_status():
    """Called by planner to check publish status of a week."""
    week = request.args.get("week")
    if not week:
        return jsonify({"status": "draft"})
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT status FROM week_schedules WHERE week_commencing=%s", (week,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return jsonify({"status": row["status"] if row else "draft"})


# ── Routes: EEBS Payroll Summary ──────────────────────────────────────────────

@app.route("/admin/payroll")
@admin_required
def admin_payroll():
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    selected_week = request.args.get("week", str(week_start))
    try:
        sel_dt = datetime.strptime(selected_week, "%Y-%m-%d").date()
    except Exception:
        sel_dt = week_start
    week_end = sel_dt + timedelta(days=6)

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            jc.contractor_key,
            COUNT(jc.id) as job_count,
            SUM(jc.labour_cost) as total_labour,
            SUM(jc.mileage_cost) as total_mileage,
            SUM(jc.parking_cost) as total_parking,
            SUM(jc.reimburse_total) as total_reimburse,
            SUM(jc.invoice_total) as gross_total,
            SUM(jc.cis_deduction) as total_cis,
            SUM(jc.net_payment) as net_total
        FROM job_cards jc
        WHERE jc.card_date BETWEEN %s AND %s
        AND jc.status IN ('submitted','approved')
        GROUP BY jc.contractor_key
        ORDER BY jc.contractor_key
    """, (sel_dt, week_end))
    summaries = cur.fetchall()

    # Get past weeks for selector
    cur.execute("SELECT DISTINCT date_trunc('week', card_date)::date as wc FROM job_cards ORDER BY wc DESC LIMIT 12")
    past_weeks = cur.fetchall()
    cur.close()
    conn.close()

    # Enrich with contractor names
    all_contractors = get_all_contractors()
    enriched = []
    grand = {"gross": 0, "cis": 0, "net": 0, "labour": 0, "mileage": 0}
    for s in summaries:
        c = all_contractors.get(s["contractor_key"]) or CONTRACTORS.get(s["contractor_key"]) or {}
        enriched.append({**dict(s), "name": c.get("name", s["contractor_key"]),
                         "cis_rate": c.get("cis_rate", 0.20)})
        grand["gross"]   += float(s["gross_total"] or 0)
        grand["cis"]     += float(s["total_cis"] or 0)
        grand["net"]     += float(s["net_total"] or 0)
        grand["labour"]  += float(s["total_labour"] or 0)
        grand["mileage"] += float(s["total_mileage"] or 0)

    return render_template("admin_payroll.html", summaries=enriched, grand=grand,
                           selected_week=sel_dt, week_end=week_end, past_weeks=past_weeks)


# ── API: Odometer / Mileage / Location ───────────────────────────────────────

@app.route("/api/odometer_needed")
@login_required
def api_odometer_needed():
    key = session["contractor_key"]
    contractor = CONTRACTORS[key]
    if not contractor.get("redstone_vehicle") or contractor.get("mileage_rate", 0) > 0:
        return jsonify({"needed": False})
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM odometer_readings WHERE contractor_key=%s AND week_commencing=%s", (key, week_start))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return jsonify({"needed": row is None, "week_commencing": week_start.strftime("%d %B %Y"),
                    "van_reg": contractor.get("van_reg","")})


@app.route("/api/odometer_submit", methods=["POST"])
@login_required
def api_odometer_submit():
    key = session["contractor_key"]
    contractor = CONTRACTORS[key]
    data = request.get_json()
    reading = data.get("reading")
    if not reading:
        return jsonify({"ok": False, "error": "No reading provided"})
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT odometer FROM odometer_readings WHERE contractor_key=%s ORDER BY week_commencing DESC LIMIT 1", (key,))
    last = cur.fetchone()
    miles_since_last = int(reading) - last["odometer"] if last and last["odometer"] else None
    cur.execute("""
        INSERT INTO odometer_readings (contractor_key,van_reg,reading_date,week_commencing,odometer,miles_since_last)
        VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING
    """, (key, contractor.get("van_reg"), today, week_start, int(reading), miles_since_last))
    # Also update vehicles table
    cur.execute("UPDATE vehicles SET current_mileage=%s, updated_at=NOW() WHERE contractor_key=%s",
                (int(reading), key))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/last_location")
@login_required
def api_last_location():
    key = session["contractor_key"]
    contractor = CONTRACTORS[key]
    today = date.today()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT last_location, last_job_id, updated_at FROM contractor_locations WHERE contractor_key=%s", (key,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row and row["updated_at"] and row["last_location"]:
        try:
            last_date = row["updated_at"].date()
        except Exception:
            last_date = None
        if last_date == today:
            return jsonify({"location": row["last_location"], "job_id": row["last_job_id"], "from_last_job": True})
    return jsonify({"location": contractor["address"], "job_id": None, "from_last_job": False})


@app.route("/api/mileage")
@login_required
def api_mileage():
    key = session["contractor_key"]
    contractor = CONTRACTORS[key]
    origin = request.args.get("from","")
    dest   = request.args.get("to","")
    return_to_site = request.args.get("return_to_site","false") == "true"
    site   = request.args.get("site","")
    if not origin or not dest:
        return jsonify({"miles": 0, "cost": 0})
    try:
        if not GMAPS_API_KEY:
            return jsonify({"miles": 0, "cost": 0, "error": "No API key configured"})
        def get_miles(a, b):
            url = "https://maps.googleapis.com/maps/api/distancematrix/json"
            params = {"origins": a, "destinations": b, "units": "imperial", "region": "gb", "key": GMAPS_API_KEY}
            r = requests.get(url, params=params, timeout=10)
            data = r.json()
            if data.get("status") != "OK":
                return 0, f"API error: {data.get('status')}"
            el = data["rows"][0]["elements"][0]
            if el.get("status") != "OK":
                return 0, f"Route not found: {el.get('status')}"
            return round(el["distance"]["value"] / 1609.34, 1), None
        miles, err = get_miles(origin, dest)
        if err:
            return jsonify({"miles": 0, "cost": 0, "error": err})
        if return_to_site and site:
            extra, err2 = get_miles(dest, site)
            if not err2:
                miles += extra
        cost = round(miles * contractor["mileage_rate"], 2)
        return jsonify({"miles": miles, "cost": cost})
    except Exception as e:
        return jsonify({"miles": 0, "cost": 0, "error": str(e)})


# ── Routes: Weekly Notes ─────────────────────────────────────────────────────

@app.route("/admin/notes")
@admin_required
def admin_notes():
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    conn = get_db()
    cur = conn.cursor()
    # Get all notes for this week
    cur.execute("""
        SELECT n.*, c.name as contractor_name
        FROM contractor_weekly_notes n
        JOIN contractors_db c ON c.contractor_key = n.contractor_key
        WHERE n.week_commencing = %s
        ORDER BY c.name
    """, (week_start,))
    notes = cur.fetchall()
    cur.execute("SELECT contractor_key, name FROM contractors_db WHERE status='active' ORDER BY name")
    contractors = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("admin_notes.html", notes=notes, contractors=contractors,
                           week_start=week_start)


@app.route("/admin/notes/save", methods=["POST"])
@admin_required
def save_note():
    data = request.get_json()
    contractor_key = data.get("contractor_key")
    note = data.get("note", "").strip()
    week_commencing = data.get("week_commencing")
    if not contractor_key or not week_commencing:
        return jsonify({"ok": False, "error": "Missing fields"})
    conn = get_db()
    cur = conn.cursor()
    if note:
        cur.execute("""
            INSERT INTO contractor_weekly_notes (contractor_key, week_commencing, note)
            VALUES (%s, %s, %s)
            ON CONFLICT (contractor_key, week_commencing) DO UPDATE
            SET note = EXCLUDED.note, updated_at = NOW()
        """, (contractor_key, week_commencing, note))
    else:
        cur.execute("""
            DELETE FROM contractor_weekly_notes
            WHERE contractor_key = %s AND week_commencing = %s
        """, (contractor_key, week_commencing))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/my_note")
@login_required
def api_my_note():
    """Return this week's note for the logged-in contractor."""
    key = session["contractor_key"]
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT note FROM contractor_weekly_notes
            WHERE contractor_key = %s AND week_commencing = %s
        """, (key, week_start))
        row = cur.fetchone()
    except Exception:
        conn.rollback()
        row = None
    cur.close()
    conn.close()
    return jsonify({"note": row["note"] if row else None,
                    "week_commencing": str(week_start)})


@app.context_processor
def inject_globals():
    return {"now": datetime.now}


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False)
