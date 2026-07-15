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
from collections import defaultdict
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
            notes               TEXT,
            query_note          TEXT,
            revision            INTEGER DEFAULT 0,
            expected_payment_date DATE,
            paid_at             TIMESTAMPTZ,
            reimburse_parking   NUMERIC(8,2) DEFAULT 0,
            parking_items_json  JSONB DEFAULT '[]'
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

        CREATE TABLE IF NOT EXISTS planner_weekly_notes (
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

    for col_sql in [
        "ALTER TABLE job_cards ADD COLUMN IF NOT EXISTS query_note TEXT",
        "ALTER TABLE job_cards ADD COLUMN IF NOT EXISTS revision INTEGER DEFAULT 0",
        "ALTER TABLE job_cards ADD COLUMN IF NOT EXISTS expected_payment_date DATE",
        "ALTER TABLE job_cards ADD COLUMN IF NOT EXISTS paid_at TIMESTAMPTZ",
        "ALTER TABLE job_cards ADD COLUMN IF NOT EXISTS reimburse_parking NUMERIC(8,2) DEFAULT 0",
        "ALTER TABLE job_cards ADD COLUMN IF NOT EXISTS parking_items_json JSONB DEFAULT '[]'",
      "ALTER TABLE job_cards ADD COLUMN IF NOT EXISTS journey_json JSONB DEFAULT '[]'",
        "ALTER TABLE job_cards ADD COLUMN IF NOT EXISTS admin_materials_json JSONB DEFAULT '[]'",
        "ALTER TABLE job_cards ADD COLUMN IF NOT EXISTS admin_materials_total NUMERIC(8,2) DEFAULT 0",
        "CREATE TABLE IF NOT EXISTS survey_forms (id SERIAL PRIMARY KEY, job_id TEXT NOT NULL, contractor TEXT, contractor_key TEXT, visit_date DATE, time_arrived TEXT, time_departed TEXT, manager_on_duty TEXT, scope_of_works TEXT, measurements TEXT, condition_notes TEXT, recommended_approach TEXT, access_notes TEXT, parking_notes TEXT, materials_spec_json JSONB DEFAULT '[]', photo_paths JSONB DEFAULT '[]', survey_mileage NUMERIC(6,2) DEFAULT 0, status TEXT DEFAULT 'surveyed', query_note TEXT, quote_labour_json JSONB DEFAULT '[]', quote_subcontractor_json JSONB DEFAULT '[]', quote_materials_json JSONB DEFAULT '[]', quote_plant_json JSONB DEFAULT '[]', quote_prelim_json JSONB DEFAULT '[]', quote_subtotal NUMERIC(10,2) DEFAULT 0, quote_total NUMERIC(10,2) DEFAULT 0, outcome TEXT, outcome_reason TEXT, submitted_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), pub_name TEXT, postcode TEXT, trade_type TEXT)",
        "ALTER TABLE survey_forms ADD COLUMN IF NOT EXISTS quote_subcontractor_json JSONB DEFAULT '[]'",
    ]:
        try:
            cur.execute(col_sql)
            conn.commit()
        except Exception:
            conn.rollback()

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
    if not DVLA_API_KEY:
        return {"status": "unknown", "expiry": None, "error": "No API key"}
    try:
        reg_clean = reg.replace(" ", "").upper()
        url = "https://driver-vehicle-licensing.api.gov.uk/vehicle-enquiry/v1/vehicles"
        headers = {"x-api-key": DVLA_API_KEY, "Content-Type": "application/json"}
        payload = {"registrationNumber": reg_clean}
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        if r.status_code == 200:
            data = r.json()
            mot_expiry_str = data.get("motExpiryDate")
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
                "status": mot_status, "expiry": mot_expiry,
                "days_left": (mot_expiry - date.today()).days if mot_expiry else None,
                "make": data.get("make", ""), "colour": data.get("colour", ""),
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


# ── PDF Colours ───────────────────────────────────────────────────────────────

REDSTONE_DARK  = colors.HexColor("#1a2332")
REDSTONE_RED   = colors.HexColor("#c0392b")
REDSTONE_LIGHT = colors.HexColor("#f5f6f8")
REDSTONE_GREY  = colors.HexColor("#7f8c8d")


# ── Job Card PDF (admin operational document) ─────────────────────────────────

def build_job_card_pdf(card, contractor):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm,
                            leftMargin=15*mm, rightMargin=15*mm)
    story = []
    label_style   = ParagraphStyle("label", fontSize=8, textColor=REDSTONE_GREY, fontName="Helvetica-Bold", spaceAfter=1)
    value_style   = ParagraphStyle("value", fontSize=10, textColor=REDSTONE_DARK, fontName="Helvetica", spaceAfter=6)
    head_style    = ParagraphStyle("head", fontSize=16, textColor=REDSTONE_DARK, fontName="Helvetica-Bold")
    section_style = ParagraphStyle("section", fontSize=11, textColor=colors.white, fontName="Helvetica-Bold",
                                    backColor=REDSTONE_DARK, leftIndent=4, spaceAfter=0, spaceBefore=8)
    header_data = [[
        Paragraph("Redstone PDM", head_style),
        Paragraph("Field Engineer Job Card", head_style),
    ]]
    header_table = Table(header_data, colWidths=[85*mm, 95*mm])
    header_table.setStyle(TableStyle([("ALIGN", (1,0),(1,0),"RIGHT"), ("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=2, color=REDSTONE_RED, spaceBefore=6, spaceAfter=6))
    date_style = ParagraphStyle("date", fontSize=10, textColor=REDSTONE_GREY, fontName="Helvetica", alignment=TA_CENTER, spaceAfter=10)
    card_date = card['card_date']
    if hasattr(card_date, 'strftime'):
        date_str = card_date.strftime('%A, %d %B %Y')
    else:
        date_str = str(card_date)
    story.append(Paragraph(date_str, date_style))

    def field_row(label, value):
        return [Paragraph(label, label_style), Paragraph(str(value) if value else "\u2014", value_style)]

    story.append(Spacer(1, 4))
    story.append(Paragraph(" JOB DETAILS", section_style))
    story.append(Spacer(1, 4))
    details = Table([
        field_row("JOB NUMBER", card["job_id"]),
        field_row("ENGINEER NAME", contractor["name"]),
        field_row("DATE", date_str),
        field_row("SITE / LOCATION", f"{card['site_name']} {card['postcode']}"),
        field_row("DESCRIPTION OF WORKS PLANNED", card["description_planned"]),
        field_row("DESCRIPTION OF WORKS CARRIED OUT", card["description_actual"]),
        field_row("TIME ON SITE", f"{card['time_start']} \u2014 {card['time_finish']}  ({card['hours_on_site']} hrs)"),
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
        field_row("BASE DAY RATE", f"\u00a3{card['base_day_rate']:.2f}"),
        field_row("OVERTIME HOURS", f"{card['overtime_hours']} hrs @ \u00a3{card['overtime_rate']:.2f}/hr" if card["overtime_hours"] else "None"),
        field_row("TOTAL LABOUR COST", f"\u00a3{card['labour_cost']:.2f}"),
    ], colWidths=[55*mm, 125*mm])
    labour.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(0,-1),REDSTONE_LIGHT), ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0e0e0")),
        ("LEFTPADDING",(0,0),(-1,-1),6), ("RIGHTPADDING",(0,0),(-1,-1),6),
        ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
    ]))
    story.append(labour)

    materials = card.get("materials_json") or []
    if isinstance(materials, str):
        try:
            materials = json.loads(materials)
        except Exception:
            materials = []

    if materials:
        story.append(Paragraph(" MATERIALS", section_style))
        story.append(Spacer(1, 4))
        mat_data = [["#", "Description", "Qty", "Unit Cost", "Total", "Payment"]]
        mat_grand_total = 0.0
        for i, m in enumerate(materials, 1):
            line_total = float(m.get("total", 0))
            mat_grand_total += line_total
            mat_data.append([str(i), m.get("description",""), str(m.get("qty","")),
                             f"\u00a3{float(m.get('unit_cost',0)):.2f}", f"\u00a3{line_total:.2f}",
                             m.get("payment","Redstone Card")])
        mat_data.append(["", "TOTAL MATERIALS", "", "", f"\u00a3{mat_grand_total:.2f}", ""])
        mat_table = Table(mat_data, colWidths=[8*mm,60*mm,15*mm,22*mm,22*mm,33*mm])
        mat_table.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),REDSTONE_DARK), ("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"), ("FONTSIZE",(0,0),(-1,-1),8),
            ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0e0e0")),
            ("ROWBACKGROUNDS",(0,1),(-1,-2),[colors.white, REDSTONE_LIGHT]),
            ("BACKGROUND",(0,-1),(-1,-1),REDSTONE_LIGHT),
            ("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),
            ("LEFTPADDING",(0,0),(-1,-1),4), ("RIGHTPADDING",(0,0),(-1,-1),4),
            ("TOPPADDING",(0,0),(-1,-1),3), ("BOTTOMPADDING",(0,0),(-1,-1),3),
        ]))
        story.append(mat_table)

    if contractor.get("mileage_rate", 0) > 0:
        story.append(Paragraph(" TRAVEL & MILEAGE", section_style))
        story.append(Spacer(1, 4))
        travel = Table([
            field_row("TOTAL MILEAGE", f"{card['mileage_miles']} miles (round trip)"),
            field_row("MILEAGE RATE", f"{int(float(contractor['mileage_rate'])*100)}p per mile"),
            field_row("MILEAGE COST", f"\u00a3{card['mileage_cost']:.2f}"),
            field_row("ODOMETER READING", str(card.get("odometer", "\u2014"))),
        ], colWidths=[55*mm, 125*mm])
        travel.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(0,-1),REDSTONE_LIGHT),
            ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0e0e0")),
            ("LEFTPADDING",(0,0),(-1,-1),6), ("RIGHTPADDING",(0,0),(-1,-1),6),
            ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
        ]))
        story.append(travel)

    parking_cost = float(card.get("parking_cost", 0) or 0)
    if parking_cost > 0:
        story.append(Paragraph(" PARKING", section_style))
        story.append(Spacer(1, 4))
        parking_items_stored = card.get("parking_items_json") or []
        if isinstance(parking_items_stored, str):
            try:
                parking_items_stored = json.loads(parking_items_stored)
            except Exception:
                parking_items_stored = []

        if parking_items_stored:
            park_data = [["Description", "Amount", "Payment", "Status"]]
            for p in parking_items_stored:
                cost = float(p.get("cost", 0))
                if p.get("is_fine") and p.get("fine_approved") == True:
                    status_label = "Fine \u2014 approved, reimburse"
                elif p.get("is_fine"):
                    status_label = "Fine \u2014 pending approval"
                elif p.get("payment") == "Redstone Card":
                    status_label = "Company expense"
                else:
                    status_label = "Own card \u2014 reimburse"
                park_data.append([
                    p.get("description", ""),
                    f"\u00a3{cost:.2f}",
                    p.get("payment", ""),
                    status_label
                ])
            reimburse_parking = float(card.get("reimburse_parking", 0) or 0)
            redstone_parking = parking_cost - reimburse_parking
            if redstone_parking > 0:
                park_data.append(["Redstone Card Total", f"\u00a3{redstone_parking:.2f}", "", "Company expense"])
            if reimburse_parking > 0:
                park_data.append(["Own Card Total (Reimburse)", f"\u00a3{reimburse_parking:.2f}", "", "On invoice"])
            park_data.append(["TOTAL PARKING", f"\u00a3{parking_cost:.2f}", "", ""])
            park_table = Table(park_data, colWidths=[60*mm, 25*mm, 40*mm, 55*mm])
            park_table.setStyle(TableStyle([
                ("BACKGROUND",(0,0),(-1,0),REDSTONE_DARK), ("TEXTCOLOR",(0,0),(-1,0),colors.white),
                ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"), ("FONTSIZE",(0,0),(-1,-1),8),
                ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0e0e0")),
                ("ROWBACKGROUNDS",(0,1),(-1,-3),[colors.white, REDSTONE_LIGHT]),
                ("BACKGROUND",(0,-1),(-1,-1),REDSTONE_LIGHT),
                ("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),
                ("LEFTPADDING",(0,0),(-1,-1),4), ("RIGHTPADDING",(0,0),(-1,-1),4),
                ("TOPPADDING",(0,0),(-1,-1),3), ("BOTTOMPADDING",(0,0),(-1,-1),3),
            ]))
            story.append(park_table)
        else:
            parking_tbl = Table([field_row("PARKING COST", f"\u00a3{parking_cost:.2f}")], colWidths=[55*mm, 125*mm])
            parking_tbl.setStyle(TableStyle([
                ("BACKGROUND",(0,0),(0,-1),REDSTONE_LIGHT),
                ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0e0e0")),
                ("LEFTPADDING",(0,0),(-1,-1),6),
                ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
            ]))
            story.append(parking_tbl)

    story.append(Spacer(1, 8))
    story.append(Paragraph(" JOB COST SUMMARY", section_style))
    story.append(Spacer(1, 4))
    grand_labour  = float(card.get("labour_cost", 0))
    grand_mileage = float(card.get("mileage_cost", 0))
    grand_park    = float(card.get("parking_cost", 0))
    grand_mats    = float(card.get("materials_total", 0))
    grand_total   = grand_labour + grand_mileage + grand_park + grand_mats
    grand_data = [["Labour", f"\u00a3{grand_labour:.2f}"]]
    if grand_mileage > 0:
        grand_data.append(["Mileage", f"\u00a3{grand_mileage:.2f}"])
    if grand_park > 0:
        grand_data.append(["Parking (total)", f"\u00a3{grand_park:.2f}"])
    if grand_mats > 0:
        grand_data.append(["Materials (total)", f"\u00a3{grand_mats:.2f}"])
    grand_data.append(["TOTAL JOB COST", f"\u00a3{grand_total:.2f}"])
    grand_table = Table(grand_data, colWidths=[140*mm, 40*mm])
    grand_table.setStyle(TableStyle([
        ("ALIGN",(1,0),(1,-1),"RIGHT"),
        ("FONTSIZE",(0,0),(-1,-1),9),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0e0e0")),
        ("ROWBACKGROUNDS",(0,0),(-1,-2),[colors.white, REDSTONE_LIGHT]),
        ("BACKGROUND",(0,-1),(-1,-1),REDSTONE_DARK),
        ("TEXTCOLOR",(0,-1),(-1,-1),colors.white),
        ("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),
        ("FONTSIZE",(0,-1),(-1,-1),11),
        ("TOPPADDING",(0,0),(-1,-1),5), ("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("LEFTPADDING",(0,0),(-1,-1),6), ("RIGHTPADDING",(0,0),(-1,-1),6),
        ("LINEABOVE",(0,-1),(-1,-1),1.5,REDSTONE_RED),
    ]))
    story.append(grand_table)
    doc.build(story)
    buf.seek(0)
    return buf.read()


# ── Invoice PDF (contractor financial document) ───────────────────────────────

def build_invoice_pdf(card, contractor):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm,
                            leftMargin=15*mm, rightMargin=15*mm)
    story = []

    label_style   = ParagraphStyle("label", fontSize=8, textColor=REDSTONE_GREY, fontName="Helvetica-Bold")
    value_style   = ParagraphStyle("value", fontSize=10, textColor=REDSTONE_DARK, fontName="Helvetica")
    head_style    = ParagraphStyle("head", fontSize=16, textColor=REDSTONE_DARK, fontName="Helvetica-Bold")
    section_style = ParagraphStyle("section", fontSize=11, textColor=colors.white, fontName="Helvetica-Bold",
                                    backColor=REDSTONE_DARK, leftIndent=4, spaceAfter=0, spaceBefore=8)
    small_red     = ParagraphStyle("smallred", fontSize=7, textColor=REDSTONE_RED, fontName="Helvetica")
    small_grey    = ParagraphStyle("smallgrey", fontSize=7, textColor=REDSTONE_GREY, fontName="Helvetica")

    story.append(Paragraph("Redstone PDM", head_style))
    story.append(Paragraph("Reverse Self-Billing Invoice", ParagraphStyle(
        "sub", fontSize=12, textColor=REDSTONE_GREY, fontName="Helvetica", spaceBefore=4, spaceAfter=8)))
    story.append(HRFlowable(width="100%", thickness=2, color=REDSTONE_RED, spaceBefore=4, spaceAfter=12))

    eng_style = ParagraphStyle("eng", fontSize=9, textColor=REDSTONE_DARK,
                               fontName="Helvetica", leading=16, spaceAfter=0)
    eng_label = ParagraphStyle("engl", fontSize=8, textColor=REDSTONE_GREY,
                               fontName="Helvetica-Bold", leading=14, spaceAfter=0)
    bill_style = ParagraphStyle("bill", fontSize=9, textColor=REDSTONE_DARK,
                                fontName="Helvetica", leading=16, spaceAfter=0)

    eng_block = [
        Paragraph("<b>Engineer</b>", eng_label),
        Spacer(1, 3),
        Paragraph(contractor['name'], ParagraphStyle("ename", fontSize=11,
                  textColor=REDSTONE_DARK, fontName="Helvetica-Bold", leading=14)),
        Spacer(1, 6),
        Paragraph(contractor.get('address','').replace(', ', '<br/>'), eng_style),
        Spacer(1, 6),
        Paragraph(f"<b>Tel:</b>  {contractor.get('phone','--')}", eng_style),
        Paragraph(f"<b>Email:</b>  {contractor.get('email','--')}", eng_style),
        Spacer(1, 6),
        Paragraph(f"<b>UTR:</b>  {contractor.get('utr','--')}", eng_style),
        Paragraph(f"<b>NI:</b>  {contractor.get('ni','--')}", eng_style),
        Paragraph(f"<b>Bank:</b>  {contractor.get('sort_code','--')} / {contractor.get('account_no','--')}", eng_style),
    ]

    bill_block = [
        Paragraph("<b>Bill to</b>", eng_label),
        Spacer(1, 3),
        Paragraph("Redstone PDM Ltd", ParagraphStyle("bname", fontSize=11,
                  textColor=REDSTONE_DARK, fontName="Helvetica-Bold", leading=14)),
        Spacer(1, 6),
        Paragraph("9 Canberra Gardens<br/>Cranfield<br/>Bedfordshire<br/>MK43 1AQ", bill_style),
        Spacer(1, 6),
        Paragraph("<b>VAT Reg:</b>  248 5387 69", bill_style),
        Paragraph("<b>Company:</b>  10070131", bill_style),
    ]

    parties = Table([[eng_block, bill_block]], colWidths=[95*mm, 85*mm])
    parties.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("LINEAFTER", (0,0), (0,-1), 0.5, colors.HexColor("#e0e0e0")),
        ("LEFTPADDING", (1,0), (1,-1), 16),
    ]))
    story.append(parties)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e0e0e0"), spaceAfter=8))

    def row(label, value):
        return [Paragraph(f"<b>{label}</b>", label_style), Paragraph(str(value) if value else "\u2014", value_style)]

    card_date = card["card_date"]
    if hasattr(card_date, 'strftime'):
        date_str = card_date.strftime("%A, %d %B %Y")
    else:
        date_str = str(card_date)

    summary = Table([
        row("JOB NUMBER", card["job_id"]),
        row("DATE", date_str),
        row("SITE / LOCATION", f"{card['site_name']} {card['postcode']}"),
        row("DESCRIPTION OF WORKS", card["description_actual"]),
    ], colWidths=[55*mm, 125*mm])
    summary.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(0,-1),REDSTONE_LIGHT),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0e0e0")),
        ("LEFTPADDING",(0,0),(-1,-1),6),
        ("TOPPADDING",(0,0),(-1,-1),4),
        ("BOTTOMPADDING",(0,0),(-1,-1),4),
    ]))
    story.append(summary)
    story.append(Spacer(1, 10))
    story.append(Paragraph(" INVOICE LINES", section_style))
    story.append(Spacer(1, 4))

    # Parse materials
    materials_list = card.get("materials_json") or []
    if isinstance(materials_list, str):
        try:
            materials_list = json.loads(materials_list)
        except Exception:
            materials_list = []

    # Parse parking items
    parking_items_raw = card.get("parking_items_json") or []
    if isinstance(parking_items_raw, str):
        try:
            parking_items_raw = json.loads(parking_items_raw)
        except Exception:
            parking_items_raw = []

    own_mats     = [m for m in materials_list if m.get("payment", "") != "Redstone Card"]
    redstone_mats = [m for m in materials_list if m.get("payment", "") == "Redstone Card"]
    own_park_items      = [p for p in parking_items_raw if not p.get("is_fine") and p.get("payment") != "Redstone Card"]
    red_park_items      = [p for p in parking_items_raw if p.get("payment") == "Redstone Card" and not p.get("is_fine")]
    approved_fine_items = [p for p in parking_items_raw if p.get("is_fine") and p.get("fine_approved") == True]
    pending_fine_items  = [p for p in parking_items_raw if p.get("is_fine") and p.get("fine_approved") != True]

    reimburse_parking = float(card.get("reimburse_parking", 0) or 0)
    parking_cost_total = float(card.get("parking_cost", 0) or 0)
    redstone_parking = parking_cost_total - reimburse_parking

    cost_data = [["Item", "Amount"]]
    cost_data.append(["Labour", f"\u00a3{float(card['labour_cost']):.2f}"])

    mileage_cost = float(card.get("mileage_cost", 0) or 0)
    if mileage_cost > 0:
        mileage_rate_pct = int(float(contractor.get("mileage_rate", 0)) * 100)
        cost_data.append([
            f"Mileage ({card['mileage_miles']} miles @ {mileage_rate_pct}p/mile)",
            f"\u00a3{mileage_cost:.2f}"
        ])

    # Own-card materials (reimbursable) — these appear on invoice
    for m in own_mats:
        cost_data.append([
            Paragraph(
                f"Materials \u2014 {m.get('description','')} (x{m.get('qty',1)})<br/>"
                f"<font color='#c0392b' size='7'>Own card \u2014 reimbursable</font>",
                ParagraphStyle("mi", fontSize=9, fontName="Helvetica", leading=13)),
            f"\u00a3{float(m.get('total',0)):.2f}"
        ])

    # Redstone card materials noted but greyed — NOT reimbursed on invoice
    if redstone_mats:
        red_mat_total = sum(float(m.get("total", 0)) for m in redstone_mats)
        cost_data.append([
            Paragraph(
                f"Materials ({len(redstone_mats)} item(s) on Redstone card)<br/>"
                f"<font color='#888888' size='7'>Company expense \u2014 not reimbursed on this invoice</font>",
                ParagraphStyle("rmi", fontSize=9, fontName="Helvetica", leading=13)),
            Paragraph(f"<font color='#aaaaaa'>\u00a3{red_mat_total:.2f}</font>",
                      ParagraphStyle("rmiv", fontSize=9, fontName="Helvetica"))
        ])

    # Own-card parking (reimbursable) — on invoice
    for p in own_park_items:
        cost_data.append([
            Paragraph(
                f"Parking \u2014 {p.get('description','')}<br/>"
                f"<font color='#c0392b' size='7'>Own card \u2014 reimbursable</font>",
                ParagraphStyle("pi", fontSize=9, fontName="Helvetica", leading=13)),
            f"\u00a3{float(p.get('cost',0)):.2f}"
        ])

    # If no itemised parking but there is a reimburse_parking total, show it
    if not own_park_items and reimburse_parking > 0:
        cost_data.append([
            Paragraph(
                "Parking (Own Card)<br/>"
                "<font color='#c0392b' size='7'>Own card \u2014 reimbursable</font>",
                ParagraphStyle("pi2", fontSize=9, fontName="Helvetica", leading=13)),
            f"\u00a3{reimburse_parking:.2f}"
        ])

    # Redstone card parking noted but greyed
    if red_park_items:
        red_park_total = sum(float(p.get("cost", 0)) for p in red_park_items)
        cost_data.append([
            Paragraph(
                "Parking (Redstone Card)<br/>"
                "<font color='#888888' size='7'>Company expense \u2014 not reimbursed on this invoice</font>",
                ParagraphStyle("rpi", fontSize=9, fontName="Helvetica", leading=13)),
            Paragraph(f"<font color='#aaaaaa'>\u00a3{red_park_total:.2f}</font>",
                      ParagraphStyle("rpiv", fontSize=9, fontName="Helvetica"))
        ])
    elif redstone_parking > 0 and not parking_items_raw:
        cost_data.append([
            Paragraph(
                "Parking (Redstone Card)<br/>"
                "<font color='#888888' size='7'>Company expense \u2014 not reimbursed on this invoice</font>",
                ParagraphStyle("rpi2", fontSize=9, fontName="Helvetica", leading=13)),
            Paragraph(f"<font color='#aaaaaa'>\u00a3{redstone_parking:.2f}</font>",
                      ParagraphStyle("rpi2v", fontSize=9, fontName="Helvetica"))
        ])

    # Parking fines — not on invoice, noted for transparency
    for p in approved_fine_items:
        cost_data.append([
            Paragraph(
                f"Parking Fine \u2014 {p.get('description','')}<br/>"
                f"<font color='#c0392b' size='7'>Fine approved \u2014 reimbursable</font>",
                ParagraphStyle("afi", fontSize=9, fontName="Helvetica", leading=13)),
            f"\u00a3{float(p.get('cost',0)):.2f}"
        ])

    for p in pending_fine_items:
        cost_data.append([
            Paragraph(
                f"Parking Fine \u2014 {p.get('description','')}<br/>"
                f"<font color='#856404' size='7'>Pending approval \u2014 not included in invoice total</font>",
                ParagraphStyle("pfi", fontSize=9, fontName="Helvetica", leading=13)),
            Paragraph(f"<font color='#aaaaaa'>\u00a3{float(p.get('cost',0)):.2f}</font>",
                      ParagraphStyle("pfiv", fontSize=9, fontName="Helvetica"))
        ])

    cost_table = Table(cost_data, colWidths=[140*mm, 40*mm])
    cost_table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),REDSTONE_DARK),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("FONTSIZE",(0,0),(-1,-1),9),
        ("ALIGN",(1,0),(1,-1),"RIGHT"),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0e0e0")),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, REDSTONE_LIGHT]),
        ("LEFTPADDING",(0,0),(-1,-1),6),
        ("RIGHTPADDING",(0,0),(-1,-1),6),
        ("TOPPADDING",(0,0),(-1,-1),5),
        ("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ]))
    story.append(cost_table)
    story.append(Spacer(1, 6))

    # Totals
    invoice_total = float(card.get("invoice_total", 0))
    cis_deduction = float(card.get("cis_deduction", 0))
    net_payment   = float(card.get("net_payment", 0))
    cis_rate      = float(contractor.get("cis_rate", 0))

    totals_data = [["Gross Invoice", f"\u00a3{invoice_total:.2f}"]]
    if cis_rate > 0:
        totals_data.append([
            f"CIS Deduction ({int(cis_rate*100)}%)\non labour only",
            f"-\u00a3{cis_deduction:.2f}"
        ])
        totals_data.append(["Net Payment to Contractor", f"\u00a3{net_payment:.2f}"])

    ts = [
        ("FONTNAME",(0,0),(-1,-1),"Helvetica-Bold"),
        ("FONTSIZE",(0,0),(-1,-1),10),
        ("ALIGN",(1,0),(1,-1),"RIGHT"),
        ("TOPPADDING",(0,0),(-1,-1),6),
        ("BOTTOMPADDING",(0,0),(-1,-1),6),
        ("LEFTPADDING",(0,0),(-1,-1),6),
        ("RIGHTPADDING",(0,0),(-1,-1),6),
        ("LINEABOVE",(0,0),(-1,0),1.5,REDSTONE_RED),
        ("BACKGROUND",(0,0),(-1,0),REDSTONE_LIGHT),
    ]
    if cis_rate > 0:
        ts += [
            ("TEXTCOLOR",(0,1),(-1,1),REDSTONE_RED),
            ("FONTSIZE",(0,1),(0,1),8),
            ("BACKGROUND",(0,-1),(-1,-1),REDSTONE_DARK),
            ("TEXTCOLOR",(0,-1),(-1,-1),colors.white),
            ("FONTSIZE",(0,-1),(-1,-1),11),
        ]
    else:
        ts += [
            ("BACKGROUND",(0,-1),(-1,-1),REDSTONE_DARK),
            ("TEXTCOLOR",(0,-1),(-1,-1),colors.white),
            ("FONTSIZE",(0,-1),(-1,-1),11),
        ]

    totals_table = Table(totals_data, colWidths=[140*mm, 40*mm])
    totals_table.setStyle(TableStyle(ts))
    story.append(totals_table)
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "Payment will be processed via EEBS (pay intermediary) in accordance with IR35 regulations. "
        "CIS deductions are calculated on labour elements only and do not apply to expense reimbursements or materials. "
        "This is a self-billing invoice raised by Redstone PDM Ltd on behalf of the above engineer.",
        ParagraphStyle("note", fontSize=7, textColor=REDSTONE_GREY, fontName="Helvetica")))

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(to_addresses, subject, body_html, attachments=None):
    if not SENDGRID_API_KEY:
        print("No SendGrid API key -- email skipped")
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
            AND j.tab NOT IN ('QUOTEREQUEST', 'QUOTE')
            ORDER BY a.day_date, a.id
        """, (key, contractor["name"], week_start, week_end))
        jobs = cur.fetchall()

    cur.execute("""
        SELECT * FROM job_cards WHERE contractor_key = %s
        ORDER BY submitted_at DESC LIMIT 20
    """, (key,))
    recent_cards = cur.fetchall()

    queried_count = sum(1 for c in recent_cards if c["status"] == "queried")

    try:
        cur.execute("""
            SELECT a.job_id, a.day_date, j.pub_name, j.postcode, j.description,
                   j.trade_type, j.tab, j.display_id
            FROM allocations a
            JOIN jobs j ON j.job_id = a.job_id
            LEFT JOIN survey_forms sf ON (sf.job_id = j.job_id OR sf.job_id = j.display_id)
                AND sf.contractor_key = %s
                AND sf.status NOT IN ('queried')
            WHERE a.contractor = %s
            AND j.tab IN ('QUOTEREQUEST', 'QUOTE')
            AND sf.id IS NULL
            ORDER BY a.day_date DESC LIMIT 20
        """, (key, contractor["name"],))
        survey_jobs = cur.fetchall()
    except Exception:
        conn.rollback()
        survey_jobs = []

    cur.close()
    conn.close()
    return render_template("dashboard.html", contractor=contractor, jobs=jobs,
                           recent_cards=recent_cards, week_start=week_start,
                           today=today, week_published=week_published,
                           queried_count=queried_count, survey_jobs=survey_jobs)


@app.route("/job/<job_id>/<card_date>")
@login_required
def job_card_form(job_id, card_date):
    key = session["contractor_key"]
    contractor = CONTRACTORS[key]
    job_id = str(job_id)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM jobs WHERE job_id::text = %s", (job_id,))
    job = cur.fetchone()
    cur.execute("""
        SELECT * FROM job_cards
        WHERE job_id = %s AND contractor_key = %s AND card_date = %s
    """, (job_id, key, card_date))
    existing_card = cur.fetchone()
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
    redstone_parking = 0.0
    for i in range(1, park_count + 1):
        desc = request.form.get(f"park_desc_{i}", "").strip()
        cost = float(request.form.get(f"park_cost_{i}", 0) or 0)
        payment = request.form.get(f"park_payment_{i}", "Redstone Card")
        is_fine = request.form.get(f"park_is_fine_{i}") == "yes"
        if cost > 0:
            parking_items.append({"description": desc, "cost": cost, "payment": payment, "is_fine": is_fine})
            parking += cost
            if is_fine:
                pass  # fines excluded from reimburse_parking until admin approves
            elif payment == "Redstone Card":
                redstone_parking += cost
            else:
                reimburse_parking += cost

    # Labour calculation by job type
    job_prefix = str(job_id)[:4] if job_id else "1000"
    is_ppm = job_prefix == "2000"

    if is_ppm:
        base_labour = float(contractor["day_rate"])
        labour_type = "PPM Full Day"
    else:
        hourly_rate = float(contractor["day_rate"]) / 10
        base_labour = round(hours * hourly_rate, 2)
        labour_type = f"Hourly ({hours}hrs x \u00a3{hourly_rate:.2f}/hr)"

    overtime_cost = round(overtime_h * float(contractor["overtime_rate"]), 2)
    labour_cost   = round(base_labour + overtime_cost, 2)
    mileage_cost  = round(mileage_miles * float(contractor.get("mileage_rate", 0)), 2)

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
    cis_deduction = round(labour_cost * float(contractor.get("cis_rate", 0)), 2)
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
        "hours_on_site": hours,
        "labour_type": f"{labour_type} + {overtime_h}hrs OT" if overtime_h else labour_type,
        "base_day_rate": contractor["day_rate"], "overtime_hours": overtime_h,
        "overtime_rate": contractor["overtime_rate"], "labour_cost": labour_cost,
        "mileage_miles": mileage_miles, "mileage_cost": mileage_cost,
        "parking_cost": parking,
        "reimburse_parking": reimburse_parking,
        "parking_items_json": parking_items,
        "materials_json": materials,
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
            photo_paths, parking_photo_path, receipt_photo_paths, status,
            reimburse_parking, parking_items_json, journey_json
        ) VALUES (
            %(contractor_key)s,%(job_id)s,%(card_date)s,%(site_name)s,%(postcode)s,
            %(description_planned)s,%(description_actual)s,%(time_start)s,%(time_finish)s,
            %(hours_on_site)s,%(labour_type)s,%(base_day_rate)s,%(overtime_hours)s,%(overtime_rate)s,
            %(labour_cost)s,%(mileage_miles)s,%(mileage_cost)s,%(parking_cost)s,
            %(materials_json)s,%(materials_total)s,%(reimburse_total)s,%(odometer)s,
            %(only_job_today)s,%(invoice_total)s,%(cis_deduction)s,%(net_payment)s,
            %(photo_paths)s,%(parking_photo_path)s,%(receipt_photo_paths)s,'submitted',
            %(reimburse_parking)s,%(parking_items_json)s,%(journey_json)s
        ) ON CONFLICT DO NOTHING RETURNING id
    """, {**card, "contractor_key": key,
          "materials_json": json.dumps(materials),
          "photo_paths": json.dumps(photo_paths),
          "receipt_photo_paths": json.dumps(receipt_photos),
          "parking_items_json": json.dumps(parking_items),
          "journey_json": json.dumps(journey_legs)})
    result = cur.fetchone()
    conn.commit()

    try:
        loc_cur = conn.cursor()
        has_next_job_leg = any(l.get("type") == "nextjob" for l in journey_legs)
        if has_next_job_leg:
            new_location = job.get("postcode","") + " " + job.get("pub_name","")
            new_job_id = job_id
        else:
            new_location = contractor["address"]
            new_job_id = None
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
        subject=f"Redstone PDM -- Invoice: {contractor['name']} | {job_id} | {card_date}",
        body_html=f"""
            <p>Please find attached the self-billing invoice for:</p>
            <ul>
                <li><b>Engineer:</b> {contractor['name']}</li>
                <li><b>Job:</b> {job_id} -- {card.get('site_name','')}</li>
                <li><b>Date:</b> {card_date}</li>
                <li><b>Invoice Total:</b> \u00a3{invoice_total:.2f}</li>
                <li><b>CIS Deduction:</b> \u00a3{cis_deduction:.2f}</li>
                <li><b>Net Payment:</b> \u00a3{net_payment:.2f}</li>
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
               subject=f"Profile Change Request -- {contractor['name']} -- {label}",
               body_html=f"<p><b>{contractor['name']}</b> requested change: {label} to {new_value}</p>")
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
    week_end = week_start + timedelta(days=6)

    cards = []
    overdue = []
    engineer_overview = []

    all_contractors = get_all_contractors()

    # Pull all job cards for this week
    try:
        cur.execute("""
            SELECT
                jc.contractor_key, jc.status,
                jc.labour_cost, jc.mileage_cost, jc.mileage_miles,
                jc.parking_cost, jc.reimburse_parking,
                jc.materials_total, jc.reimburse_total,
                jc.invoice_total
            FROM job_cards jc
            WHERE jc.card_date BETWEEN %s AND %s
        """, (week_start, week_end))
        week_cards = cur.fetchall()
    except Exception as e:
        print(f"week_cards query failed: {e}")
        conn.rollback()
        week_cards = []

    # Pull allocation counts per contractor name
    alloc_rows = {}
    try:
        cur.execute("""
            SELECT a.contractor, COUNT(DISTINCT a.id) as allocated
            FROM allocations a
            WHERE a.day_date BETWEEN %s AND %s
            GROUP BY a.contractor
        """, (week_start, week_end))
        alloc_rows = {r["contractor"]: r["allocated"] for r in cur.fetchall()}
    except Exception as e:
        print(f"alloc_rows query failed: {e}")
        conn.rollback()

    # Aggregate stats per contractor_key
    stats_by_key = defaultdict(lambda: {
        "submitted": 0, "pending": 0, "queried": 0, "approved": 0, "paid": 0,
        "total_labour": 0.0, "total_mileage": 0.0, "total_miles": 0.0,
        "total_parking": 0.0, "reimburse_parking": 0.0,
        "total_mats": 0.0, "reimburse_total": 0.0,
        "gross_invoice": 0.0,
    })
    for wc in week_cards:
        k = wc["contractor_key"]
        s = stats_by_key[k]
        s["submitted"] += 1
        st = wc["status"]
        if st == "submitted":   s["pending"] += 1
        elif st == "queried":   s["queried"] += 1
        elif st == "approved":  s["approved"] += 1
        elif st == "paid":      s["paid"] += 1
        s["total_labour"]      += float(wc["labour_cost"] or 0)
        s["total_mileage"]     += float(wc["mileage_cost"] or 0)
        s["total_miles"]       += float(wc["mileage_miles"] or 0)
        s["total_parking"]     += float(wc["parking_cost"] or 0)
        s["reimburse_parking"] += float(wc["reimburse_parking"] or 0)
        s["total_mats"]        += float(wc["materials_total"] or 0)
        s["reimburse_total"]   += float(wc["reimburse_total"] or 0)
        s["gross_invoice"]     += float(wc["invoice_total"] or 0)

    for key, c in all_contractors.items():
        s = stats_by_key.get(key, {})
        allocated    = alloc_rows.get(c["name"], 0)
        submitted    = s.get("submitted", 0)
        has_activity = submitted > 0

        gross_invoice    = s.get("gross_invoice", 0.0)
        total_mats       = s.get("total_mats", 0.0)
        reimburse_total  = s.get("reimburse_total", 0.0)
        total_parking    = s.get("total_parking", 0.0)
        reimburse_park   = s.get("reimburse_parking", 0.0)

        own_spend      = reimburse_total + reimburse_park
        redstone_spend = (total_mats - reimburse_total) + (total_parking - reimburse_park)
        total_cost     = gross_invoice + redstone_spend

        engineer_overview.append({
            "contractor":    c["name"],
            "contractor_key": key,
            "allocated":     allocated,
            "submitted":     submitted,
            "pending":       s.get("pending", 0),
            "queried":       s.get("queried", 0),
            "approved":      s.get("approved", 0),
            "total_labour":  s.get("total_labour", 0.0),
            "total_mileage": s.get("total_mileage", 0.0),
            "total_miles":   s.get("total_miles", 0.0),
            "total_mats":    total_mats,
            "total_parking": total_parking,
            "redstone_spend": redstone_spend,
            "own_spend":     own_spend,
            "gross_invoice": gross_invoice,
            "total_cost":    total_cost,
            "has_activity":  has_activity,
        })

    engineer_overview.sort(key=lambda x: x["contractor"])

    # All job cards
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

    # Overdue cards
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
        """, (week_start, week_end))
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
                overdue.append({**dict(mc), "flag": flag, "hrs_since": round(hrs_since, 1)})
    except Exception as e:
        print(f"overdue query failed: {e}")
        conn.rollback()

    # Quotes (5000 prefix)
    quotes = []
    try:
        cur.execute("""
            SELECT DISTINCT a.job_id, a.contractor, a.day_date,
                   j.pub_name, j.postcode, j.description, j.trade_type,
                   j.tab, j.tab_label, j.location_code
            FROM allocations a
            JOIN jobs j ON j.job_id = a.job_id
            WHERE (j.job_id LIKE '5000%%' OR j.tab IN ('QUOTE','QUOTEREQUEST'))
            ORDER BY a.day_date DESC
            LIMIT 100
        """)
        quotes = cur.fetchall()
    except Exception as e:
        print(f"quotes query failed: {e}")
        conn.rollback()

    cur.close()
    conn.close()

    # Serialise quotes for JS
    quotes_list = []
    for q in quotes:
        d = dict(q)
        for k, v in d.items():
            if hasattr(v, 'isoformat'):
                d[k] = v.isoformat()
            elif hasattr(v, 'strftime'):
                d[k] = str(v)
        quotes_list.append(d)

    return render_template("admin_jobcards.html",
                           cards=cards,
                           engineer_overview=engineer_overview,
                           overdue=overdue,
                           week_start=week_start,
                           contractors=all_contractors,
                           quotes=quotes,
                           quotes_json=json.dumps(quotes_list))


@app.route("/admin/approve/<int:card_id>", methods=["POST"])
@admin_required
def approve_card(card_id):
    data = request.get_json() or {}
    approved_fines = data.get("approved_fines", [])  # list of fine indices approved by admin

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM job_cards WHERE id=%s", (card_id,))
    card = cur.fetchone()
    if not card:
        cur.close(); conn.close()
        return jsonify({"ok": False, "error": "Not found"}), 404

    # Expected payment date
    card_dt = card["card_date"]
    days_to_friday = (4 - card_dt.weekday()) % 7
    week_friday = card_dt + timedelta(days=days_to_friday)
    expected_pay = week_friday + timedelta(days=30)

    # Process parking fines — stamp each with admin decision
    parking_items = card.get("parking_items_json") or []
    if isinstance(parking_items, str):
        try:
            parking_items = json.loads(parking_items)
        except Exception:
            parking_items = []

    fine_addition = 0.0
    for i, p in enumerate(parking_items):
        if p.get("is_fine"):
            if i in approved_fines:
                p["fine_approved"] = True
                fine_addition += float(p.get("cost", 0))
            else:
                p["fine_approved"] = False

    # Recalculate invoice total if fines were approved
    new_reimburse_parking = float(card["reimburse_parking"] or 0) + fine_addition
    new_invoice_total     = float(card["invoice_total"] or 0) + fine_addition
    contractor = get_contractor(card["contractor_key"]) or CONTRACTORS.get(card["contractor_key"], {})
    cis_rate      = float(contractor.get("cis_rate", 0))
    labour_cost   = float(card["labour_cost"] or 0)
    cis_deduction = round(labour_cost * cis_rate, 2)
    new_net_payment = round(new_invoice_total - cis_deduction, 2)

    cur.execute("""
        UPDATE job_cards SET
            status='approved',
            approved_at=NOW(),
            approved_by='admin',
            expected_payment_date=%s,
            parking_items_json=%s,
            reimburse_parking=%s,
            invoice_total=%s,
            cis_deduction=%s,
            net_payment=%s
        WHERE id=%s
    """, (
        expected_pay,
        json.dumps(parking_items),
        new_reimburse_parking,
        new_invoice_total,
        cis_deduction,
        new_net_payment,
        card_id
    ))
    conn.commit()

    # Regenerate and resend invoice PDF if fines added to it
    if fine_addition > 0:
        updated_card = dict(card)
        updated_card["parking_items_json"] = parking_items
        updated_card["reimburse_parking"]  = new_reimburse_parking
        updated_card["invoice_total"]      = new_invoice_total
        updated_card["cis_deduction"]      = cis_deduction
        updated_card["net_payment"]        = new_net_payment
        try:
            invoice_pdf = build_invoice_pdf(updated_card, contractor)
            filename_base = f"{contractor['name'].replace(' ','_')}_{card['job_id']}_{card['card_date']}_approved"
            send_email(
                to_addresses=[ACCOUNTS_EMAIL, contractor.get("email", "")],
                subject=f"Redstone PDM -- Approved Invoice (parking fine included): {contractor['name']} | {card['job_id']}",
                body_html=f"""
                    <p>Job card approved. Parking fine(s) have been approved and added to the invoice.</p>
                    <ul>
                        <li><b>Engineer:</b> {contractor['name']}</li>
                        <li><b>Job:</b> {card['job_id']} &mdash; {card.get('site_name', '')}</li>
                        <li><b>Fine addition:</b> &pound;{fine_addition:.2f}</li>
                        <li><b>Revised Invoice Total:</b> &pound;{new_invoice_total:.2f}</li>
                        <li><b>CIS Deduction:</b> &pound;{cis_deduction:.2f}</li>
                        <li><b>Net Payment:</b> &pound;{new_net_payment:.2f}</li>
                    </ul>
                """,
                attachments=[(f"{filename_base}_invoice.pdf", invoice_pdf)]
            )
        except Exception as e:
            print(f"Could not send approval email: {e}")

    cur.close()
    conn.close()
    return jsonify({
        "ok": True,
        "expected_payment_date": str(expected_pay) if expected_pay else None,
        "fine_addition": fine_addition,
        "new_invoice_total": new_invoice_total,
        "new_net_payment": new_net_payment
    })



@app.route("/admin/query/<int:card_id>", methods=["POST"])
@admin_required
def query_card(card_id):
    data = request.get_json()
    note = data.get("note", "").strip()
    if not note:
        return jsonify({"ok": False, "error": "Query note required"})
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE job_cards SET status='queried', query_note=%s WHERE id=%s
        RETURNING contractor_key, job_id, site_name
    """, (note, card_id))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@app.route("/admin/mark_paid/<int:card_id>", methods=["POST"])
@admin_required
def mark_paid(card_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE job_cards SET status='paid', paid_at=NOW() WHERE id=%s", (card_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@app.route("/card/<int:card_id>/detail")
@login_required
def card_detail(card_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT jc.*, j.pub_name, j.description as job_description, j.trade_type
        FROM job_cards jc
        LEFT JOIN jobs j ON j.job_id = jc.job_id
        WHERE jc.id=%s
    """, (card_id,))
    card = cur.fetchone()
    cur.close()
    conn.close()
    if not card:
        return jsonify({"error": "Not found"}), 404
    if session.get("role") != "admin" and card["contractor_key"] != session.get("contractor_key"):
        return jsonify({"error": "Forbidden"}), 403
    d = dict(card)
    for k, v in d.items():
        if hasattr(v, 'isoformat'):
            d[k] = v.isoformat()
        elif hasattr(v, 'strftime'):
            d[k] = str(v)
    return jsonify(d)


@app.route("/card/<int:card_id>/jobcard.pdf")
@login_required
def download_job_card(card_id):
    """Admin gets job card PDF. Contractor gets their invoice PDF."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM job_cards WHERE id=%s", (card_id,))
    card = cur.fetchone()
    cur.close()
    conn.close()
    if not card:
        return "Not found", 404

    role = session.get("role")
    key  = session.get("contractor_key")

    if role != "admin" and card["contractor_key"] != key:
        return redirect(url_for("login"))

    contractor = get_contractor(card["contractor_key"]) or CONTRACTORS.get(card["contractor_key"], {})

    if role == "admin":
        pdf = build_job_card_pdf(card, contractor)
        filename = f"jobcard_{card_id}.pdf"
    else:
        pdf = build_invoice_pdf(card, contractor)
        filename = f"invoice_{card_id}.pdf"

    return send_file(io.BytesIO(pdf), mimetype="application/pdf", download_name=filename)


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
          float(data.get("mileage_rate") or 0),
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
          float(data.get("mileage_rate") or 0),
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
                   subject="Redstone PDM -- Profile Change Approved",
                   body_html=f"<p>Hi {contractor.get('name','')}, your {row['field_name']} update to {row['new_value']} has been approved.</p>")
    return jsonify({"ok": True})


# ── Routes: Admin Surveys ────────────────────────────────────────────────────

@app.route("/admin/surveys")
@admin_required
def admin_surveys():
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT sf.*, c.name as contractor,
                   COALESCE(j.display_id, sf.job_id) as display_id
            FROM survey_forms sf
            LEFT JOIN contractors_db c ON c.contractor_key = sf.contractor_key
            LEFT JOIN jobs j ON j.job_id = sf.job_id OR j.display_id = sf.job_id
            ORDER BY sf.submitted_at DESC
        """)
        surveys = cur.fetchall()
    except Exception as e:
        conn.rollback()
        surveys = []
    cur.close()
    conn.close()
    return render_template("admin_surveys.html", surveys=surveys)


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


# ── Routes: Week Schedule ─────────────────────────────────────────────────────

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

    by_contractor = defaultdict(list)
    for a in allocs:
        by_contractor[a["contractor"]].append(a)

    all_contractors = get_all_contractors()
    for cname, jobs in by_contractor.items():
        c = next((v for v in all_contractors.values() if v["name"] == cname), None)
        if not c or not c.get("email"):
            continue
        rows = "".join(
            f"<tr><td style='padding:6px;border:1px solid #ddd'>{j['day_date'].strftime('%A %d %b')}</td>"
            f"<td style='padding:6px;border:1px solid #ddd'>{j['pub_name']}</td>"
            f"<td style='padding:6px;border:1px solid #ddd'>{j['postcode']}</td>"
            f"<td style='padding:6px;border:1px solid #ddd'>{j['description'][:60]}...</td></tr>"
            for j in jobs)
        send_email(
            to_addresses=[c["email"]],
            subject=f"Redstone PDM -- Your Schedule w/c {week_dt.strftime('%d %b %Y')}",
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


# ── Routes: Payroll ───────────────────────────────────────────────────────────

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

    cur.execute("SELECT DISTINCT date_trunc('week', card_date)::date as wc FROM job_cards ORDER BY wc DESC LIMIT 12")
    past_weeks = cur.fetchall()
    cur.close()
    conn.close()

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


# ── Routes: Contractor Invoice History ────────────────────────────────────────

@app.route("/my_invoices")
@login_required
def my_invoices():
    if session.get("role") == "admin":
        return redirect(url_for("admin_home"))
    key = session["contractor_key"]
    contractor = CONTRACTORS.get(key) or get_contractor(key) or {}
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM job_cards
        WHERE contractor_key=%s
        ORDER BY submitted_at DESC
    """, (key,))
    invoices = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("my_invoices.html", contractor=contractor, invoices=invoices)


@app.route("/card/<int:card_id>/edit")
@login_required
def edit_card(card_id):
    key = session["contractor_key"]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM job_cards WHERE id=%s AND contractor_key=%s AND status='queried'", (card_id, key))
    card = cur.fetchone()
    if not card:
        return redirect(url_for("my_invoices"))
    cur.execute("SELECT * FROM jobs WHERE job_id=%s", (card["job_id"],))
    job = cur.fetchone()
    cur.close()
    conn.close()
    if not job:
        return redirect(url_for("my_invoices"))
    contractor = CONTRACTORS.get(key) or get_contractor(key) or {}
    return render_template("job_card.html", contractor=contractor, job=job,
                           card_date=str(card["card_date"]),
                           existing_card=None,
                           edit_card=card,
                           gmaps_key=GMAPS_API_KEY)


@app.route("/card/<int:card_id>/resubmit", methods=["POST"])
@login_required
def resubmit_card(card_id):
    key = session["contractor_key"]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM job_cards WHERE id=%s AND contractor_key=%s AND status='queried'", (card_id, key))
    old_card = cur.fetchone()
    if not old_card:
        return redirect(url_for("my_invoices"))

    revision = (old_card["revision"] or 0) + 1
    contractor = CONTRACTORS.get(key) or get_contractor(key) or {}
    time_start   = request.form.get("time_start", "")
    time_finish  = request.form.get("time_finish", "")
    hours        = float(request.form.get("hours_on_site", 0) or 0)
    overtime_h   = float(request.form.get("overtime_hours", 0) or 0)
    desc_actual  = request.form.get("description_actual", "")
    desc_planned = request.form.get("description_planned", "")
    mileage_miles = float(request.form.get("total_miles", 0) or 0)

    job_id = old_card["job_id"]
    job_prefix = str(job_id)[:4]
    is_ppm = job_prefix == "2000"
    if is_ppm:
        base_labour = float(contractor["day_rate"])
        labour_type = "PPM Full Day"
    else:
        hourly_rate = float(contractor["day_rate"]) / 10
        base_labour = round(hours * hourly_rate, 2)
        labour_type = f"Hourly ({hours}hrs x \u00a3{hourly_rate:.2f}/hr)"
    overtime_cost = round(overtime_h * float(contractor["overtime_rate"]), 2)
    labour_cost = round(base_labour + overtime_cost, 2)
    mileage_cost = round(mileage_miles * float(contractor.get("mileage_rate", 0)), 2)

    parking = 0.0
    reimburse_parking = 0.0
    parking_items = []
    park_count = int(request.form.get("parking_count", 0))
    for i in range(1, park_count + 1):
        desc = request.form.get(f"park_desc_{i}", "")
        cost = float(request.form.get(f"park_cost_{i}", 0) or 0)
        payment = request.form.get(f"park_payment_{i}", "Redstone Card")
        is_fine = request.form.get(f"park_is_fine_{i}") == "yes"
        if cost > 0:
            parking_items.append({"description": desc, "cost": cost, "payment": payment, "is_fine": is_fine})
            parking += cost
            if is_fine:
                pass  # fines excluded until admin approves
            elif payment != "Redstone Card":
                reimburse_parking += cost

    materials = []
    reimburse_total = 0.0
    mat_count = int(request.form.get("material_count", 0))
    for i in range(1, mat_count + 1):
        desc = request.form.get(f"mat_desc_{i}", "")
        if not desc:
            continue
        qty = float(request.form.get(f"mat_qty_{i}", 1) or 1)
        unit_cost = float(request.form.get(f"mat_cost_{i}", 0) or 0)
        payment = request.form.get(f"mat_payment_{i}", "Redstone Card")
        total = round(qty * unit_cost, 2)
        materials.append({"description": desc, "qty": qty, "unit_cost": unit_cost, "total": total, "payment": payment})
        if payment != "Redstone Card":
            reimburse_total += total

    materials_total = sum(m["total"] for m in materials)
    reimburse_total_all = reimburse_total + reimburse_parking
    invoice_total = labour_cost + mileage_cost + reimburse_total_all
    cis_deduction = round(labour_cost * float(contractor.get("cis_rate", 0.20)), 2)
    net_payment = round(invoice_total - cis_deduction, 2)

    cur.execute("""
        UPDATE job_cards SET
            status='submitted', query_note=NULL, revision=%s,
            description_actual=%s, description_planned=%s,
            time_start=%s, time_finish=%s, hours_on_site=%s,
            labour_type=%s, overtime_hours=%s, labour_cost=%s,
            mileage_miles=%s, mileage_cost=%s, parking_cost=%s,
            reimburse_parking=%s, parking_items_json=%s,
            materials_json=%s, materials_total=%s, reimburse_total=%s,
            invoice_total=%s, cis_deduction=%s, net_payment=%s,
            submitted_at=NOW()
        WHERE id=%s
    """, (revision, desc_actual, desc_planned, time_start, time_finish, hours,
          labour_type, overtime_h, labour_cost, mileage_miles, mileage_cost,
          parking, reimburse_parking, json.dumps(parking_items),
          json.dumps(materials), materials_total, reimburse_total,
          invoice_total, cis_deduction, net_payment, card_id))
    conn.commit()

    cur.execute("SELECT * FROM job_cards WHERE id=%s", (card_id,))
    updated = cur.fetchone()
    cur.close()
    conn.close()

    card_dict = dict(updated)
    card_dict["parking_items_json"] = parking_items
    card_dict["materials_json"] = materials

    invoice_pdf = build_invoice_pdf(card_dict, contractor)
    filename_base = f"{contractor['name'].replace(' ','_')}_{job_id}_rev{revision}"
    send_email(
        to_addresses=[ACCOUNTS_EMAIL, contractor["email"]],
        subject=f"Redstone PDM -- REVISED Invoice v{revision}: {contractor['name']} | {job_id}",
        body_html=f"""
            <p><strong>REVISED INVOICE (v{revision})</strong></p>
            <p>Engineer: {contractor['name']}<br>
            Job: {job_id}<br>
            Invoice Total: \u00a3{invoice_total:.2f}<br>
            Net Payment: \u00a3{net_payment:.2f}</p>
        """,
        attachments=[(f"{filename_base}_invoice.pdf", invoice_pdf)]
    )
    return redirect(url_for("my_invoices"))


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
    if row and row["updated_at"] and row["last_location"] and row["last_job_id"]:
        try:
            last_date = row["updated_at"].date()
        except Exception:
            last_date = None
        if last_date == today and row["last_job_id"] is not None:
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
        cost = round(miles * float(contractor.get("mileage_rate", 0)), 2)
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


@app.route("/api/my_planner_note")
@login_required
def api_my_planner_note():
    """Returns the planner note written for this contractor for the current week.
    Separate from contractor_weekly_notes — written by the planner app, read-only here."""
    key = session["contractor_key"]
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT note FROM planner_weekly_notes
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


@app.route("/card/<int:card_id>/admin_materials", methods=["POST"])
@admin_required
def save_admin_materials(card_id):
    data = request.json or {}
    mats = data.get("admin_materials", [])
    admin_total = sum(float(m.get("total", 0) or 0) for m in mats)
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE job_cards SET admin_materials_json=%s, admin_materials_total=%s WHERE id=%s",
            (psycopg2.extras.Json(mats), admin_total, card_id)
        )
        conn.commit()
        cur.execute(
            "SELECT invoice_total, materials_total, reimburse_total, parking_cost, reimburse_parking, admin_materials_total FROM job_cards WHERE id=%s",
            (card_id,)
        )
        row = cur.fetchone()
        if row:
            gross_invoice   = float(row["invoice_total"] or 0)
            total_mats      = float(row["materials_total"] or 0)
            reimburse_total = float(row["reimburse_total"] or 0)
            total_parking   = float(row["parking_cost"] or 0)
            reimburse_park  = float(row["reimburse_parking"] or 0)
            admin_mat_total = float(row["admin_materials_total"] or 0)
            redstone_spend  = (total_mats - reimburse_total) + (total_parking - reimburse_park) + admin_mat_total
            total_cost      = gross_invoice + redstone_spend
        else:
            total_cost = 0.0
        return jsonify({"ok": True, "total": round(admin_total, 2), "total_cost_to_business": round(total_cost, 2)})
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)})
    finally:
        cur.close()
        conn.close()


@app.context_processor
def inject_globals():
    return {"now": datetime.now}


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False)


# ── Survey Routes ─────────────────────────────────────────────────────────────

@app.route("/survey/<job_id>/<day_date>")
@login_required
def survey_form(job_id, day_date):
    """Engineer survey form for a 5000-series quote request job."""
    key = session["contractor_key"]
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM jobs WHERE job_id = %s OR display_id = %s", (job_id, job_id))
    job = cur.fetchone()
    if not job:
        cur.close(); conn.close()
        return "Job not found", 404

    actual_job_id = job["job_id"] if job else job_id
    cur.execute("""
        SELECT sf.*, c.name as contractor
        FROM survey_forms sf
        JOIN contractors_db c ON c.contractor_key = sf.contractor_key
        WHERE (sf.job_id = %s OR sf.job_id = %s) AND sf.contractor_key = %s
        ORDER BY sf.submitted_at DESC LIMIT 1
    """, (job_id, actual_job_id, key))
    existing = cur.fetchone()

    cur.execute("SELECT name FROM contractors_db WHERE contractor_key = %s", (key,))
    contractor = cur.fetchone()
    cur.close(); conn.close()

    return render_template("survey_form.html",
        job=job,
        existing=existing,
        contractor=contractor,
        today=date.today().isoformat(),
        day_date=day_date,
    )


@app.route("/survey/submit", methods=["POST"])
@login_required
def submit_survey():
    """Submit or resubmit an engineer's survey form."""
    key = session["contractor_key"]
    job_id = request.form.get("job_id")
    survey_id = request.form.get("survey_id")

    conn = get_db()
    cur = conn.cursor()

    try:
        # Save uploaded photos
        import uuid as _uuid
        photo_paths = []
        i = 0
        while True:
            photo = request.files.get(f"photo_{i}")
            if not photo:
                break
            ext = photo.filename.rsplit('.', 1)[-1].lower() if '.' in photo.filename else 'jpg'
            fname = f"survey_{job_id}_{key}_{_uuid.uuid4().hex[:8]}.{ext}"
            save_path = os.path.join(app.config.get("UPLOAD_FOLDER", "uploads"), fname)
            photo.save(save_path)
            captions = json.loads(request.form.get("captions", "[]"))
            photo_paths.append({"path": fname, "caption": captions[i] if i < len(captions) else ""})
            i += 1

        mats = json.loads(request.form.get("materials_spec_json", "[]"))

        # Get job info for denormalisation
        cur.execute("SELECT pub_name, postcode, trade_type FROM jobs WHERE job_id = %s", (job_id,))
        job_row = cur.fetchone()
        pub_name = job_row["pub_name"] if job_row else ""
        postcode = job_row["postcode"] if job_row else ""
        trade_type = job_row["trade_type"] if job_row else ""

        # Get contractor name
        cur.execute("SELECT name FROM contractors_db WHERE contractor_key = %s", (key,))
        c_row = cur.fetchone()
        contractor_name = c_row["name"] if c_row else key

        new_status = "resubmitted" if survey_id else "surveyed"

        if survey_id:
            # Update existing — append new photos to existing ones
            cur.execute("SELECT photo_paths FROM survey_forms WHERE id = %s", (survey_id,))
            old = cur.fetchone()
            existing_photos = list(old["photo_paths"] or []) if old else []
            all_photos = existing_photos + photo_paths

            cur.execute("""
                UPDATE survey_forms SET
                    visit_date=%s, time_arrived=%s, time_departed=%s,
                    manager_on_duty=%s, scope_of_works=%s, measurements=%s,
                    condition_notes=%s, recommended_approach=%s,
                    access_notes=%s, parking_notes=%s,
                    survey_mileage=%s, materials_spec_json=%s,
                    photo_paths=%s, status=%s, updated_at=NOW()
                WHERE id=%s AND contractor_key=%s
            """, (
                request.form.get("visit_date"), request.form.get("time_arrived"),
                request.form.get("time_departed"), request.form.get("manager_on_duty"),
                request.form.get("scope_of_works"), request.form.get("measurements"),
                request.form.get("condition_notes"), request.form.get("recommended_approach"),
                request.form.get("access_notes"), request.form.get("parking_notes"),
                request.form.get("survey_mileage", 0),
                psycopg2.extras.Json(mats),
                psycopg2.extras.Json(all_photos),
                new_status, survey_id, key
            ))
        else:
            cur.execute("""
                INSERT INTO survey_forms (
                    job_id, contractor_key, contractor, visit_date, time_arrived, time_departed,
                    manager_on_duty, scope_of_works, measurements, condition_notes,
                    recommended_approach, access_notes, parking_notes,
                    survey_mileage, materials_spec_json, photo_paths,
                    status, pub_name, postcode, trade_type
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                job_id, key, contractor_name,
                request.form.get("visit_date"), request.form.get("time_arrived"),
                request.form.get("time_departed"), request.form.get("manager_on_duty"),
                request.form.get("scope_of_works"), request.form.get("measurements"),
                request.form.get("condition_notes"), request.form.get("recommended_approach"),
                request.form.get("access_notes"), request.form.get("parking_notes"),
                request.form.get("survey_mileage", 0),
                psycopg2.extras.Json(mats),
                psycopg2.extras.Json(photo_paths),
                "surveyed", pub_name, postcode, trade_type
            ))

        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)})
    finally:
        cur.close()
        conn.close()


# ── Admin Survey Routes ───────────────────────────────────────────────────────

# admin_surveys route defined above


@app.route("/admin/survey/<int:survey_id>")
@admin_required
def admin_survey_detail(survey_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT sf.*, c.name as contractor,
               COALESCE(j.display_id, sf.job_id) as display_id
        FROM survey_forms sf
        LEFT JOIN contractors_db c ON c.contractor_key = sf.contractor_key
        LEFT JOIN jobs j ON j.job_id = sf.job_id OR j.display_id = sf.job_id
        WHERE sf.id = %s
    """, (survey_id,))
    s = cur.fetchone()
    cur.close(); conn.close()
    if not s:
        return jsonify({"error": "Not found"}), 404
    row = dict(s)
    # Serialise dates
    for k in ["visit_date", "submitted_at", "updated_at"]:
        if row.get(k):
            row[k] = str(row[k])
    return jsonify(row)


@app.route("/admin/survey/<int:survey_id>/query", methods=["POST"])
@admin_required
def admin_survey_query(survey_id):
    data = request.json or {}
    note = data.get("query_note", "")
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE survey_forms SET status='queried', query_note=%s, updated_at=NOW()
            WHERE id=%s
        """, (note, survey_id))
        conn.commit()

        # Notify engineer
        cur.execute("SELECT contractor_key, job_id, pub_name FROM survey_forms WHERE id=%s", (survey_id,))
        sf = cur.fetchone()
        if sf:
            cur.execute("SELECT email, name FROM contractors_db WHERE contractor_key=%s", (sf["contractor_key"],))
            eng = cur.fetchone()
            if eng and eng["email"]:
                body = f"""<div style="font-family:Segoe UI,sans-serif;max-width:600px;margin:0 auto">
                  <div style="background:#1a2332;padding:16px 20px;border-radius:8px 8px 0 0">
                    <span style="color:white;font-size:18px;font-weight:700">Redstone <span style="color:#c0392b">PDM</span></span>
                  </div>
                  <div style="background:white;padding:20px;border:1px solid #e0e0e0;border-radius:0 0 8px 8px">
                    <p style="font-size:15px;color:#1a2332">Hi {eng['name'].split()[0]},</p>
                    <p style="color:#555;font-size:13px;margin:12px 0">Your survey for <strong>{sf['pub_name']}</strong> ({sf['job_id']}) has been queried by the office:</p>
                    <div style="background:#fff8e1;border:1px solid #ffc107;border-radius:8px;padding:14px;font-size:13px;color:#5c3d00;margin:12px 0">{note}</div>
                    <p style="font-size:13px;color:#555">Please log in to Redstone PDM, open the survey and resubmit with the corrections.</p>
                  </div>
                </div>"""
                send_email(eng["email"], f"Redstone PDM — Survey Query: {sf['pub_name']}", body)

        return jsonify({"ok": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)})
    finally:
        cur.close(); conn.close()


@app.route("/admin/survey/<int:survey_id>/quote", methods=["POST"])
@admin_required
def admin_save_quote(survey_id):
    data = request.json or {}
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE survey_forms SET
                status=%s,
                quote_labour_json=%s, quote_subcontractor_json=%s,
                quote_materials_json=%s,
                quote_plant_json=%s, quote_prelim_json=%s,
                quote_subtotal=%s, quote_total=%s,
                updated_at=NOW()
            WHERE id=%s
        """, (
            data.get("status", "quote-draft"),
            psycopg2.extras.Json(data.get("quote_labour_json", [])),
            psycopg2.extras.Json(data.get("quote_subcontractor_json", [])),
            psycopg2.extras.Json(data.get("quote_materials_json", [])),
            psycopg2.extras.Json(data.get("quote_plant_json", [])),
            psycopg2.extras.Json(data.get("quote_prelim_json", [])),
            data.get("quote_subtotal", 0),
            data.get("quote_total", 0),
            survey_id
        ))
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)})
    finally:
        cur.close(); conn.close()


@app.route("/admin/survey/<int:survey_id>/scope", methods=["POST"])
@admin_required
def admin_save_scope(survey_id):
    data = request.json or {}
    scope = data.get("scope_of_works", "")
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE survey_forms SET scope_of_works=%s, updated_at=NOW() WHERE id=%s", (scope, survey_id))
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)})
    finally:
        cur.close(); conn.close()


@app.route("/admin/survey/<int:survey_id>/measurements", methods=["POST"])
@admin_required
def admin_save_measurements(survey_id):
    data = request.json or {}
    measurements = data.get("measurements", "")
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE survey_forms SET measurements=%s, updated_at=NOW() WHERE id=%s", (measurements, survey_id))
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)})
    finally:
        cur.close(); conn.close()


@app.route("/admin/survey/<int:survey_id>/outcome", methods=["POST"])
@admin_required
def admin_survey_outcome(survey_id):
    data = request.json or {}
    outcome = data.get("outcome")
    reason = data.get("reason", "")
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE survey_forms SET
                status=%s, outcome=%s, outcome_reason=%s, updated_at=NOW()
            WHERE id=%s
        """, (outcome, outcome, reason, survey_id))
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)})
    finally:
        cur.close(); conn.close()


@app.route("/admin/survey/<int:survey_id>/pdf")
@admin_required
def admin_survey_pdf(survey_id):
    """Generate a branded Redstone quote PDF."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT sf.*,
               COALESCE(j.display_id, sf.job_id) as display_id,
               COALESCE(sf.quote_subcontractor_json, '[]'::jsonb) as quote_subcontractor_json
        FROM survey_forms sf
        LEFT JOIN jobs j ON j.job_id = sf.job_id OR j.display_id = sf.job_id
        WHERE sf.id = %s
    """, (survey_id,))
    s = cur.fetchone()
    cur.close(); conn.close()
    if not s:
        return "Not found", 404

    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER
    import io

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)

    RED    = colors.HexColor('#c0392b')
    DARK   = colors.HexColor('#1a2332')
    GREY   = colors.HexColor('#888888')
    LGREY  = colors.HexColor('#f5f6f8')
    styles = getSampleStyleSheet()
    MARKUP = 0.20
    VAT_RATE = 0.20

    def sty(name, **kw):
        return ParagraphStyle(name, parent=styles['Normal'], **kw)

    h1   = sty('h1', fontSize=20, fontName='Helvetica-Bold', textColor=DARK)
    h2   = sty('h2', fontSize=11, fontName='Helvetica-Bold', textColor=DARK)
    sub  = sty('sub', fontSize=9, textColor=GREY)
    body = sty('body', fontSize=9, textColor=DARK, leading=14)
    red_label = sty('rl', fontSize=8, fontName='Helvetica-Bold', textColor=RED, spaceAfter=2)
    right_bold = sty('rb', fontSize=11, fontName='Helvetica-Bold', textColor=DARK, alignment=TA_RIGHT)

    elems = []

    # Header
    header_data = [[
        Paragraph('<font color="#c0392b"><b>Redstone</b></font><b> PDM Ltd</b>', sty('hb', fontSize=16, fontName='Helvetica-Bold', textColor=DARK)),
        Paragraph(f'<b>QUOTE</b><br/><font size="9" color="#888888">{s["display_id"] or s["job_id"]}</font>', sty('qt', fontSize=14, fontName='Helvetica-Bold', textColor=DARK, alignment=TA_RIGHT))
    ]]
    header_tbl = Table(header_data, colWidths=[90*mm, 80*mm])
    header_tbl.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LINEBELOW', (0,0), (-1,0), 1.5, RED),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
    ]))
    elems.append(header_tbl)
    elems.append(Spacer(1, 8*mm))

    # Site info
    info_data = [
        [Paragraph('<b>Site</b>', red_label), Paragraph(s["pub_name"] or "—", body),
         Paragraph('<b>Postcode</b>', red_label), Paragraph(s["postcode"] or "—", body)],
        [Paragraph('<b>Trade</b>', red_label), Paragraph(s["trade_type"] or "—", body),
         Paragraph('<b>Date</b>', red_label), Paragraph(s["visit_date"].strftime('%d/%m/%Y') if hasattr(s["visit_date"], 'strftime') else str(s["visit_date"] or '—'), body)],
    ]
    info_tbl = Table(info_data, colWidths=[25*mm, 65*mm, 25*mm, 55*mm])
    info_tbl.setStyle(TableStyle([
        ('VALIGN', (0,0),(-1,-1),'TOP'),
        ('BACKGROUND', (0,0),(-1,-1), LGREY),
        ('ROWBACKGROUNDS', (0,0),(-1,-1), [LGREY, colors.white]),
        ('TOPPADDING', (0,0),(-1,-1), 5),
        ('BOTTOMPADDING', (0,0),(-1,-1), 5),
        ('LEFTPADDING', (0,0),(-1,-1), 6),
    ]))
    elems.append(info_tbl)
    elems.append(Spacer(1, 6*mm))

    # Scope
    if s["scope_of_works"]:
        elems.append(Paragraph("Description of Works", h2))
        elems.append(Spacer(1,2*mm))
        elems.append(Paragraph(s["scope_of_works"].replace('\n','<br/>'), body))
        elems.append(Spacer(1,5*mm))

    # Line items
    sections = [
        ("Labour", s["quote_labour_json"] or [], False),
        ("Subcontractor", s.get("quote_subcontractor_json") or [], True),
        ("Materials", s["quote_materials_json"] or [], True),
        ("Plant & Equipment", s["quote_plant_json"] or [], False),
        ("Prelim / Mobilisation", s["quote_prelim_json"] or [], False),
    ]

    labour_total = materials_total = plant_total = prelim_total = 0
    line_rows = [["Description", "Qty", "Unit Cost", "Total"]]

    subcon_total = 0
    for section_name, lines, apply_markup in sections:
        if not lines:
            continue
        line_rows.append([Paragraph(f"<b>{section_name}</b>", sty('sh', fontSize=9, fontName='Helvetica-Bold', textColor=RED)), "", "", ""])
        for line in lines:
            qty = float(line.get("qty", 0) or 0)
            uc  = float(line.get("unit_cost", 0) or 0)
            tot = qty * uc
            if section_name == "Labour":
                labour_total += tot
            elif section_name == "Subcontractor":
                subcon_total += tot
            elif section_name == "Materials":
                materials_total += tot
            elif section_name == "Plant & Equipment":
                plant_total += tot
            else:
                prelim_total += tot
            line_rows.append([
                Paragraph(line.get("description", ""), body),
                f"{qty:g}",
                f"£{uc:.2f}",
                f"£{tot:.2f}",
            ])

    subcon_markup = subcon_total * MARKUP
    materials_markup = materials_total * MARKUP
    total = labour_total + subcon_total + subcon_markup + materials_total + materials_markup + plant_total + prelim_total

    if labour_total:
        line_rows.append(["", "", Paragraph("<b>Labour</b>", sty('st', fontSize=9, fontName='Helvetica-Bold', textColor=DARK)), f"£{labour_total:.2f}"])
    if subcon_total:
        line_rows.append(["", "", Paragraph("<b>Subcontractor</b>", sty('st', fontSize=9, fontName='Helvetica-Bold', textColor=DARK)), f"£{(subcon_total + subcon_markup):.2f}"])
    if materials_total:
        line_rows.append(["", "", Paragraph("<b>Materials</b>", sty('st', fontSize=9, fontName='Helvetica-Bold', textColor=DARK)), f"£{(materials_total + materials_markup):.2f}"])
    if plant_total:
        line_rows.append(["", "", Paragraph("<b>Plant & Equipment</b>", sty('st', fontSize=9, fontName='Helvetica-Bold', textColor=DARK)), f"£{plant_total:.2f}"])
    if prelim_total:
        line_rows.append(["", "", Paragraph("<b>Prelim / Mobilisation</b>", sty('st', fontSize=9, fontName='Helvetica-Bold', textColor=DARK)), f"£{prelim_total:.2f}"])
    line_rows.append(["", "", Paragraph("<b>TOTAL (ex VAT)</b>", sty('tot', fontSize=10, fontName='Helvetica-Bold', textColor=DARK)), Paragraph(f"<b>£{total:.2f}</b>", sty('totv', fontSize=10, fontName='Helvetica-Bold', textColor=DARK))])

    tbl = Table(line_rows, colWidths=[95*mm, 20*mm, 30*mm, 25*mm])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,0), DARK),
        ('TEXTCOLOR', (0,0),(-1,0), colors.white),
        ('FONTNAME', (0,0),(-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0),(-1,0), 9),
        ('ROWBACKGROUNDS', (0,1),(-1,-4), [colors.white, LGREY]),
        ('LINEABOVE', (0,-3),(-1,-3), 1, GREY),
        ('LINEABOVE', (0,-1),(-1,-1), 2, DARK),
        ('ALIGN', (1,0),(-1,-1), 'RIGHT'),
        ('VALIGN', (0,0),(-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0),(-1,-1), 5),
        ('BOTTOMPADDING', (0,0),(-1,-1), 5),
        ('LEFTPADDING', (0,0),(-1,-1), 6),
        ('RIGHTPADDING', (0,0),(-1,-1), 6),
    ]))
    elems.append(tbl)
    elems.append(Spacer(1, 6*mm))

    # Footer note


    # Inc VAT total
    vat_amount = total * VAT_RATE
    total_inc_vat = total + vat_amount
    elems.append(Spacer(1, 3*mm))
    vat_data = [
        ["", Paragraph("Total (ex VAT)", sty('vl', fontSize=10, textColor=GREY, alignment=TA_RIGHT)), Paragraph(f"£{total:.2f}", sty('vv', fontSize=10, textColor=DARK, alignment=TA_RIGHT))],
        ["", Paragraph(f"VAT (20%)", sty('vl', fontSize=10, textColor=GREY, alignment=TA_RIGHT)), Paragraph(f"£{vat_amount:.2f}", sty('vv', fontSize=10, textColor=DARK, alignment=TA_RIGHT))],
        ["", Paragraph("<b>Total (inc VAT)</b>", sty('vl2', fontSize=11, fontName='Helvetica-Bold', textColor=DARK, alignment=TA_RIGHT)), Paragraph(f"<b>£{total_inc_vat:.2f}</b>", sty('vv2', fontSize=11, fontName='Helvetica-Bold', textColor=RED, alignment=TA_RIGHT))],
    ]
    vat_tbl = Table(vat_data, colWidths=[95*mm, 50*mm, 25*mm])
    vat_tbl.setStyle(TableStyle([
        ('LINEABOVE', (1,2),(-1,2), 1.5, DARK),
        ('TOPPADDING', (0,0),(-1,-1), 4),
        ('BOTTOMPADDING', (0,0),(-1,-1), 4),
        ('VALIGN', (0,0),(-1,-1), 'MIDDLE'),
    ]))
    elems.append(vat_tbl)
    elems.append(Spacer(1, 8*mm))

    # Terms & Conditions
    elems.append(PageBreak())
    elems.append(Paragraph("<b>Terms & Conditions</b>", sty('tch', fontSize=10, fontName='Helvetica-Bold', textColor=DARK)))
    elems.append(Spacer(1, 4*mm))

    tcs = [
        ("1. Payment Terms", "Payment is due within 30 days from the invoice date unless otherwise agreed in writing."),
        ("2. Late Payment", "We reserve the right to charge interest on overdue accounts at 8% above the Bank of England base rate, in accordance with the Late Payment of Commercial Debts (Interest) Act 1998. Reasonable recovery costs may also be applied."),
        ("3. Suspension of Works", "We reserve the right to suspend ongoing or future works where invoices remain unpaid beyond agreed terms, without liability for delays caused."),
        ("4. Retention of Title", "All materials, goods and installed items remain the property of Redstone until full payment has been received."),
        ("5. Variations & Additional Works", "Any additional works requested outside the original scope may be charged separately and invoiced accordingly."),
        ("6. Materials & Procurement", "Materials supplied are charged as per invoice and may include handling, procurement and logistics costs."),
        ("7. Access & Delays", "Where works are delayed due to lack of access, client-side issues or third-party delays, additional costs may be incurred."),
        ("8. Snagging / Defects", "Any defects must be reported within a reasonable period following completion. We will rectify workmanship issues in line with the agreed scope."),
        ("9. Liability", "Our liability is limited to the value of the works carried out under this invoice. We are not liable for indirect or consequential losses."),
        ("10. Acceptance of Terms", "Payment of this invoice constitutes acceptance of these terms and conditions."),
        ("11. Purchase Orders", "A valid Purchase Order (PO) must be provided prior to commencement of works where applicable."),
        ("12. Out of Hours Works", "Out-of-hours / night works are charged at agreed premium rates."),
        ("13. Waste Disposal", "Waste removal and disposal will be charged unless explicitly included."),
    ]

    tc_style = sty('tc', fontSize=7.5, textColor=colors.HexColor('#444444'), leading=11)
    tc_bold  = sty('tcb', fontSize=7.5, fontName='Helvetica-Bold', textColor=DARK, leading=11)

    for title, text in tcs:
        tc_row = [[Paragraph(title, tc_bold), Paragraph(text, tc_style)]]
        tc_tbl = Table(tc_row, colWidths=[38*mm, 132*mm])
        tc_tbl.setStyle(TableStyle([
            ('VALIGN', (0,0),(-1,-1), 'TOP'),
            ('TOPPADDING', (0,0),(-1,-1), 2),
            ('BOTTOMPADDING', (0,0),(-1,-1), 2),
        ]))
        elems.append(tc_tbl)

    doc.build(elems)
    buf.seek(0)

    from flask import send_file
    return send_file(buf, mimetype='application/pdf',
        as_attachment=True,
        download_name=f"Redstone_Quote_{s['display_id'] or s['job_id']}.pdf")
