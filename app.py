"""
Demand Prediction and Resource Optimization
College PBL Project - Phase 3
"""

import getpass
import json
import math
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import mysql.connector
from flask import Flask, jsonify, render_template, request


# DATABASE SETTINGS

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", "YOUR_MYSQL_PASSWORD"),
    "database": "demand_prediction_db",
}

BUFFER_PERCENT = 5
RECORDS_FOR_AVERAGE = 7

SURPLUS_STATUSES = [
    "Available", "Donated", "Composted", "Discarded"
]

STORAGE_METHODS = [
    "Room Temperature", "Refrigerated", "Hot Holding", "Frozen"
]

FACILITY_TYPES = [
    "Donation Centre", "Composting Facility"
]

STATUS_FACILITY = {
    "Donated": "Donation Centre",
    "Composted": "Composting Facility"
}

app = Flask(__name__)


# DATABASE HELPERS

class ValidationError(Exception):

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


def clean(value):

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")

    if isinstance(value, date):
        return value.isoformat()

    return value


def db_query(sql, params=()):

    conn = get_connection()

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        cursor.close()

        return [
            {
                key: clean(val)
                for key, val in row.items()
            }
            for row in rows
        ]

    finally:
        conn.close()


def db_execute(
    sql,
    params=(),
    dup_msg="This record already exists.",
    fk_msg="This row is used by other records, so it cannot be deleted."
):

    conn = get_connection()

    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()

        new_id = cursor.lastrowid
        cursor.close()

        return new_id

    except mysql.connector.IntegrityError as err:

        conn.rollback()

        if err.errno == 1062:
            raise ValidationError(dup_msg, 409)

        if err.errno == 1451:
            raise ValidationError(fk_msg, 409)

        raise

    finally:
        conn.close()


def ensure_exists(table, id_column, row_id, label):

    rows = db_query(
        f"SELECT 1 AS found FROM {table} WHERE {id_column} = %s",
        (row_id,)
    )

    if not rows:
        raise ValidationError(f"{label} not found.", 404)


# ERROR HANDLERS

@app.errorhandler(ValidationError)
def handle_validation_error(err):
    return jsonify(error=err.message), err.status


@app.errorhandler(mysql.connector.Error)
def handle_mysql_error(err):

    app.logger.error(
        "MySQL error %s: %s",
        getattr(err, "errno", "?"),
        err
    )

    errno = getattr(err, "errno", None)

    if errno == 1045:
        return jsonify(
            error="MySQL username or password is incorrect."
        ), 500

    if errno == 1049:
        return jsonify(
            error="Database demand_prediction_db does not exist."
        ), 500

    if errno in (2002, 2003, 2005, 2006, 2013, 2055):
        return jsonify(
            error="Cannot connect to MySQL. Start MySQL service."
        ), 500

    if errno == 1452:
        return jsonify(
            error="Selected item or record does not exist."
        ), 400

    if errno in (3819, 4025):
        return jsonify(
            error="Value rejected by database CHECK constraint."
        ), 400

    return jsonify(error="Database error. Please try again."), 500


# INPUT VALIDATION HELPERS

def get_data():
    return request.get_json(silent=True) or request.form.to_dict()


def read_text(data, field, label, max_len, required=True):

    value = str(data.get(field) or "").strip()

    if required and not value:
        raise ValidationError(f"{label} is required.")

    if len(value) > max_len:
        raise ValidationError(
            f"{label} must be at most {max_len} characters."
        )

    return value


def read_int(data, field, label, minimum=0, maximum=100000):

    try:
        value = int(str(data.get(field)).strip())

    except (TypeError, ValueError):
        raise ValidationError(
            f"{label} must be a whole number."
        )

    if value < minimum or value > maximum:
        raise ValidationError(
            f"{label} must be between {minimum} and {maximum}."
        )

    return value
def read_money(data, field, label, minimum, maximum=100000):

    try:
        value = Decimal(str(data.get(field)).strip())

    except (InvalidOperation, ValueError):
        raise ValidationError(
            f"{label} must be a number."
        )

    if not value.is_finite():
        raise ValidationError(
            f"{label} must be a number."
        )

    value = value.quantize(Decimal("0.01"))

    if (
        value < Decimal(str(minimum))
        or value > Decimal(str(maximum))
    ):
        raise ValidationError(
            f"{label} must be between {minimum} and {maximum}."
        )

    return value


def read_date(data, field, label):

    try:
        value = datetime.strptime(
            str(data.get(field)).strip(),
            "%Y-%m-%d"
        ).date()

    except ValueError:
        raise ValidationError(
            f"{label} must be a valid date (YYYY-MM-DD)."
        )

    if value > date.today():
        raise ValidationError(
            f"{label} cannot be in the future."
        )

    return value


def read_datetime(data, field, label):

    raw = str(data.get(field)).strip()
    value = None

    formats = [
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M"
    ]

    for fmt in formats:

        try:
            value = datetime.strptime(raw, fmt)
            break

        except ValueError:
            continue

    if value is None:
        raise ValidationError(
            f"{label} must be a valid date and time."
        )

    if value > datetime.now() + timedelta(minutes=1):
        raise ValidationError(
            f"{label} cannot be in the future."
        )

    return value


def read_choice(data, field, label, options):

    value = str(data.get(field) or "").strip()

    if value not in options:
        raise ValidationError(
            f"{label} must be one of: {', '.join(options)}."
        )

    return value


def read_optional_temperature(data, field):

    raw = data.get(field)

    if raw is None or str(raw).strip() == "":
        return None

    try:
        value = Decimal(str(raw).strip())

    except (InvalidOperation, ValueError):
        raise ValidationError(
            "Temperature must be a number."
        )

    if not value.is_finite() or value < -40 or value > 150:
        raise ValidationError(
            "Temperature must be between -40 and 150 degrees Celsius."
        )

    return value.quantize(Decimal("0.1"))


# CORS SETTINGS

@app.after_request
def add_cors_headers(response):

    origin = request.headers.get("Origin", "")

    if origin.startswith((
        "http://127.0.0.1",
        "http://localhost"
    )):

        response.headers["Access-Control-Allow-Origin"] = origin

        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, PUT, DELETE, OPTIONS"
        )

        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type"
        )

        response.headers["Vary"] = "Origin"

    return response


# PAGE ROUTES

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/health")
def api_health():
    get_connection().close()
    return jsonify(status="ok")


# =====================================================================
# 6. DASHBOARD
# =====================================================================

@app.route("/api/dashboard")
def api_dashboard():

    totals = db_query("""
        SELECT
            COALESCE(SUM(d.prepared_qty), 0) AS total_prepared,
            COALESCE(SUM(d.sold_qty), 0) AS total_sold,
            COALESCE(SUM(d.leftover_qty), 0) AS total_leftover,
            COALESCE(
                SUM(d.leftover_qty * f.production_cost), 0
            ) AS waste_cost
        FROM daily_records d
        JOIN food_items f ON f.item_id = d.item_id
    """)[0]

    totals["waste_cost"] = round(totals["waste_cost"], 2)

    totals["waste_percent"] = (
        round(
            totals["total_leftover"] * 100 / totals["total_prepared"],
            1
        )
        if totals["total_prepared"] else 0
    )

    counts = db_query("""
        SELECT
            (SELECT COUNT(*) FROM food_items) AS food_items,
            (SELECT COUNT(*) FROM daily_records) AS daily_records,
            (SELECT COUNT(*) FROM surplus_records
             WHERE status = 'Available') AS surplus_available
    """)[0]

    per_item = db_query("""
        SELECT
            f.item_name,
            SUM(d.prepared_qty) AS prepared,
            SUM(d.sold_qty) AS sold,
            SUM(d.leftover_qty) AS leftover,
            ROUND(
                SUM(d.leftover_qty * f.production_cost), 2
            ) AS waste_cost
        FROM daily_records d
        JOIN food_items f ON f.item_id = d.item_id
        GROUP BY f.item_id, f.item_name
        ORDER BY waste_cost DESC
    """)

    trend = db_query("""
        SELECT
            record_date,
            SUM(prepared_qty) AS prepared,
            SUM(sold_qty) AS sold,
            SUM(leftover_qty) AS leftover
        FROM daily_records
        GROUP BY record_date
        ORDER BY record_date DESC
        LIMIT 14
    """)

    trend.reverse()

    return jsonify(
        totals=totals,
        counts=counts,
        per_item=per_item,
        trend=trend
    )


# =====================================================================
# 7. FOOD ITEMS
# =====================================================================

@app.route("/api/food-items", methods=["GET"])
def list_food_items():

    rows = db_query("""
        SELECT
            f.item_id,
            f.item_name,
            f.category,
            f.selling_price,
            f.production_cost,
            COUNT(d.record_id) AS record_count
        FROM food_items f
        LEFT JOIN daily_records d ON d.item_id = f.item_id
        GROUP BY
            f.item_id,
            f.item_name,
            f.category,
            f.selling_price,
            f.production_cost
        ORDER BY f.item_name
    """)

    return jsonify(rows)


@app.route("/api/food-items", methods=["POST"])
def add_food_item():

    data = get_data()

    name = read_text(
        data, "item_name", "Food item name", 100
    )

    category = read_text(
        data, "category", "Category", 50
    )

    selling_price = read_money(
        data, "selling_price", "Selling price", 0
    )

    production_cost = read_money(
        data, "production_cost", "Production cost", 0
    )

    if production_cost > selling_price:
        raise ValidationError(
            "Production cost cannot exceed selling price."
        )

    new_id = db_execute(
        """
        INSERT INTO food_items
        (item_name, category, selling_price, production_cost)
        VALUES (%s, %s, %s, %s)
        """,
        (name, category, selling_price, production_cost),
        dup_msg="This food item already exists."
    )

    return jsonify(
        message="Food item added successfully.",
        item_id=new_id
    ), 201


@app.route("/api/food-items/<int:item_id>", methods=["PUT"])
def update_food_item(item_id):

    data = get_data()

    ensure_exists(
        "food_items", "item_id", item_id, "Food item"
    )

    name = read_text(
        data, "item_name", "Food item name", 100
    )

    category = read_text(
        data, "category", "Category", 50
    )

    selling_price = read_money(
        data, "selling_price", "Selling price", 0
    )

    production_cost = read_money(
        data, "production_cost", "Production cost", 0
    )

    if production_cost > selling_price:
        raise ValidationError(
            "Production cost cannot exceed selling price."
        )

    db_execute(
        """
        UPDATE food_items
        SET item_name = %s,
            category = %s,
            selling_price = %s,
            production_cost = %s
        WHERE item_id = %s
        """,
        (
            name,
            category,
            selling_price,
            production_cost,
            item_id
        ),
        dup_msg="Another food item already has this name."
    )

    return jsonify(message="Food item updated successfully.")


@app.route("/api/food-items/<int:item_id>", methods=["DELETE"])
def delete_food_item(item_id):

    ensure_exists(
        "food_items", "item_id", item_id, "Food item"
    )

    db_execute(
        "DELETE FROM food_items WHERE item_id = %s",
        (item_id,)
    )

    return jsonify(message="Food item deleted successfully.")
# =====================================================================
# 8. DAILY RECORDS
# =====================================================================

def read_daily_record(data):

    item_id = read_int(
        data, "item_id", "Food item", 1
    )

    ensure_exists(
        "food_items",
        "item_id",
        item_id,
        "Food item"
    )

    record_date = read_date(
        data, "record_date", "Date"
    )

    prepared = read_int(
        data, "prepared_qty", "Prepared quantity", 1
    )

    sold = read_int(
        data, "sold_qty", "Sold quantity", 0
    )

    if sold > prepared:
        raise ValidationError(
            "Sold quantity cannot be more than prepared quantity."
        )

    return item_id, record_date, prepared, sold


@app.route("/api/daily-records", methods=["GET"])
def list_daily_records():

    rows = db_query("""
        SELECT
            d.record_id,
            d.record_date,
            d.item_id,
            f.item_name,
            d.prepared_qty,
            d.sold_qty,
            d.leftover_qty,
            ROUND(
                d.leftover_qty * f.production_cost, 2
            ) AS waste_cost
        FROM daily_records d
        JOIN food_items f ON f.item_id = d.item_id
        ORDER BY d.record_date DESC, f.item_name
        LIMIT 200
    """)

    return jsonify(rows)


@app.route("/api/daily-records", methods=["POST"])
def add_daily_record():

    item_id, record_date, prepared, sold = read_daily_record(
        get_data()
    )

    new_id = db_execute(
        """
        INSERT INTO daily_records
        (record_date, item_id, prepared_qty, sold_qty)
        VALUES (%s, %s, %s, %s)
        """,
        (record_date, item_id, prepared, sold),
        dup_msg=(
            "A record for this item on this date already exists. "
            "Edit that record instead."
        )
    )

    return jsonify(
        message=(
            "Daily record saved. "
            "Leftover was calculated automatically."
        ),
        record_id=new_id
    ), 201


@app.route("/api/daily-records/<int:record_id>", methods=["PUT"])
def update_daily_record(record_id):

    ensure_exists(
        "daily_records",
        "record_id",
        record_id,
        "Daily record"
    )

    item_id, record_date, prepared, sold = read_daily_record(
        get_data()
    )

    db_execute(
        """
        UPDATE daily_records
        SET record_date = %s,
            item_id = %s,
            prepared_qty = %s,
            sold_qty = %s
        WHERE record_id = %s
        """,
        (record_date, item_id, prepared, sold, record_id),
        dup_msg=(
            "A record for this item on this date already exists."
        )
    )

    return jsonify(message="Daily record updated.")


@app.route("/api/daily-records/<int:record_id>", methods=["DELETE"])
def delete_daily_record(record_id):

    ensure_exists(
        "daily_records",
        "record_id",
        record_id,
        "Daily record"
    )

    db_execute(
        "DELETE FROM daily_records WHERE record_id = %s",
        (record_id,)
    )

    return jsonify(
        message=(
            "Daily record deleted "
            "(its surplus entries were removed too)."
        )
    )


# =====================================================================
# 9. DEMAND PREDICTION
# Basic estimate: last 7 records average + 5% buffer.
# This is not a trained machine-learning model.
# =====================================================================

def make_prediction(item_id):

    stats = db_query("""
        SELECT COUNT(*) AS records_used, AVG(sold_qty) AS avg_sales
        FROM (
            SELECT sold_qty
            FROM daily_records
            WHERE item_id = %s
            ORDER BY record_date DESC
            LIMIT 7
        ) AS last_seven
    """, (item_id,))[0]

    if stats["records_used"] == 0:
        return None

    avg_sales = round(stats["avg_sales"], 2)

    recommended = math.ceil(
        round(avg_sales * (1 + BUFFER_PERCENT / 100), 4)
    )

    prediction_date = date.today() + timedelta(days=1)

    db_execute(
        """
        INSERT INTO predictions
        (
            item_id,
            prediction_date,
            records_used,
            avg_sales,
            buffer_percent,
            recommended_qty
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            item_id,
            prediction_date,
            stats["records_used"],
            avg_sales,
            BUFFER_PERCENT,
            recommended
        )
    )

    name = db_query(
        "SELECT item_name FROM food_items WHERE item_id = %s",
        (item_id,)
    )[0]["item_name"]

    return {
        "item_name": name,
        "prediction_date": prediction_date.isoformat(),
        "records_used": stats["records_used"],
        "avg_sales": avg_sales,
        "buffer_percent": BUFFER_PERCENT,
        "recommended_qty": recommended
    }


@app.route("/api/predictions", methods=["GET"])
def list_predictions():

    rows = db_query("""
        SELECT
            p.prediction_id,
            f.item_name,
            p.prediction_date,
            p.records_used,
            p.avg_sales,
            p.buffer_percent,
            p.recommended_qty,
            p.created_at
        FROM predictions p
        JOIN food_items f ON f.item_id = p.item_id
        ORDER BY p.created_at DESC, p.prediction_id DESC
        LIMIT 50
    """)

    return jsonify(rows)


@app.route("/api/predictions", methods=["POST"])
def create_predictions():

    data = get_data()

    if str(data.get("item_id")) == "all":

        ids = [
            r["item_id"]
            for r in db_query(
                "SELECT item_id FROM food_items ORDER BY item_name"
            )
        ]

    else:

        item_id = read_int(
            data, "item_id", "Food item", 1
        )

        ensure_exists(
            "food_items", "item_id", item_id, "Food item"
        )

        ids = [item_id]

    results = [
        r for r in (make_prediction(i) for i in ids) if r
    ]

    if not results:
        raise ValidationError(
            "No daily records found. Add daily records first."
        )

    return jsonify(
        message=f"{len(results)} prediction(s) saved.",
        results=results
    ), 201


@app.route("/api/predictions/<int:prediction_id>", methods=["DELETE"])
def delete_prediction(prediction_id):

    ensure_exists(
        "predictions",
        "prediction_id",
        prediction_id,
        "Prediction"
    )

    db_execute(
        "DELETE FROM predictions WHERE prediction_id = %s",
        (prediction_id,)
    )

    return jsonify(message="Prediction deleted.")


# =====================================================================
# =====================================================================
# 10. FACILITIES
# =====================================================================

@app.route("/api/facilities", methods=["GET"])
def list_facilities():

    rows = db_query("""
        SELECT
            facility_id,
            facility_name,
            facility_type,
            address,
            contact_person,
            contact_phone,
            accepts_food,
            notes
        FROM facilities
        ORDER BY facility_name
    """)

    return jsonify(rows)


# =====================================================================
# 11. SURPLUS FOOD
# =====================================================================

def read_surplus_data(data):

    item_id = read_int(
        data, "item_id", "Food item", 1
    )

    ensure_exists(
        "food_items",
        "item_id",
        item_id,
        "Food item"
    )

    surplus_date = read_date(
        data, "surplus_date", "Surplus date"
    )

    quantity = read_int(
        data, "quantity", "Surplus quantity", 1
    )

    unit = read_choice(
        data,
        "unit",
        "Unit",
        ["plate", "kg", "piece", "packet"],
        default="plate"
    )

    reason = read_choice(
        data,
        "reason",
        "Reason",
        [
            "overproduction",
            "low_demand",
            "event_cancelled",
            "other"
        ],
        default="overproduction"
    )

    notes = str(data.get("notes", "")).strip()[:500]

    return item_id, surplus_date, quantity, unit, reason, notes


@app.route("/api/surplus", methods=["GET"])
def list_surplus():

    rows = db_query("""
        SELECT
            s.surplus_id,
            s.item_id,
            f.item_name,
            s.surplus_date,
            s.quantity,
            s.unit,
            s.reason,
            s.status,
            s.notes,
            s.created_at
        FROM surplus_food s
        JOIN food_items f ON f.item_id = s.item_id
        ORDER BY s.surplus_date DESC, s.surplus_id DESC
        LIMIT 200
    """)

    return jsonify(rows)


@app.route("/api/surplus/options", methods=["GET"])
def surplus_options():

    items = db_query("""
        SELECT item_id, item_name
        FROM food_items
        ORDER BY item_name
    """)

    facilities = db_query("""
        SELECT
            facility_id,
            facility_name,
            facility_type,
            address,
            accepts_food
        FROM facilities
        WHERE accepts_food = 1
        ORDER BY facility_name
    """)

    return jsonify({
        "items": items,
        "facilities": facilities
    })


@app.route("/api/surplus", methods=["POST"])
def add_surplus():

    data = get_data()

    (
        item_id,
        surplus_date,
        quantity,
        unit,
        reason,
        notes
    ) = read_surplus_data(data)

    new_id = db_execute(
        """
        INSERT INTO surplus_food
        (
            item_id,
            surplus_date,
            quantity,
            unit,
            reason,
            status,
            notes
        )
        VALUES (%s, %s, %s, %s, %s, 'available', %s)
        """,
        (
            item_id,
            surplus_date,
            quantity,
            unit,
            reason,
            notes
        )
    )

    return jsonify(
        message="Surplus food entry saved.",
        surplus_id=new_id
    ), 201


@app.route("/api/surplus/<int:surplus_id>", methods=["PUT"])
def update_surplus(surplus_id):

    ensure_exists(
        "surplus_food",
        "surplus_id",
        surplus_id,
        "Surplus entry"
    )

    data = get_data()

    (
        item_id,
        surplus_date,
        quantity,
        unit,
        reason,
        notes
    ) = read_surplus_data(data)

    status = read_choice(
        data,
        "status",
        "Status",
        [
            "available",
            "reserved",
            "donated",
            "composted",
            "discarded"
        ],
        default="available"
    )

    db_execute(
        """
        UPDATE surplus_food
        SET
            item_id = %s,
            surplus_date = %s,
            quantity = %s,
            unit = %s,
            reason = %s,
            status = %s,
            notes = %s
        WHERE surplus_id = %s
        """,
        (
            item_id,
            surplus_date,
            quantity,
            unit,
            reason,
            status,
            notes,
            surplus_id
        )
    )

    return jsonify(message="Surplus food entry updated.")


@app.route("/api/surplus/<int:surplus_id>", methods=["DELETE"])
def delete_surplus(surplus_id):

    ensure_exists(
        "surplus_food",
        "surplus_id",
        surplus_id,
        "Surplus entry"
    )

    db_execute(
        "DELETE FROM surplus_food WHERE surplus_id = %s",
        (surplus_id,)
    )

    return jsonify(message="Surplus food entry deleted.")


# =====================================================================
# =====================================================================
# 12. FOOD STORAGE
# =====================================================================

def storage_alerts(method, temperature, minutes):
    """Generate precautionary food-storage alerts."""

    hours = minutes / 60
    alerts = []

    if method == "Room Temperature":
        if hours > 2:
            alerts.append({
                "level": "warning",
                "text": (
                    f"Kept at room temperature for {hours:.1f} h "
                    "(guideline: max 2 h)."
                )
            })

    elif method == "Hot Holding":
        if temperature is None:
            alerts.append({
                "level": "info",
                "text": (
                    "Temperature not recorded - cannot check "
                    "the 60 C hot-holding guideline."
                )
            })
        elif temperature < 60:
            alerts.append({
                "level": "warning",
                "text": (
                    f"Hot-holding temperature {temperature} C "
                    "is below 60 C."
                )
            })

    elif method == "Refrigerated":
        if temperature is None:
            alerts.append({
                "level": "info",
                "text": (
                    "Temperature not recorded - cannot check "
                    "the 5 C refrigeration guideline."
                )
            })
        elif temperature > 5:
            alerts.append({
                "level": "warning",
                "text": (
                    f"Refrigerator temperature {temperature} C "
                    "is above 5 C."
                )
            })

        if hours > 72:
            alerts.append({
                "level": "warning",
                "text": (
                    f"Stored in the fridge for {hours:.0f} h "
                    "(guideline: about 3 days)."
                )
            })

    elif method == "Frozen":
        if temperature is None:
            alerts.append({
                "level": "info",
                "text": (
                    "Temperature not recorded - cannot check "
                    "the -18 C freezer guideline."
                )
            })
        elif temperature > -18:
            alerts.append({
                "level": "warning",
                "text": (
                    f"Freezer temperature {temperature} C "
                    "is above -18 C."
                )
            })

    return alerts


@app.route("/api/storage", methods=["GET"])
def list_storage():

    rows = db_query("""
        SELECT
            s.storage_id,
            f.item_name,
            s.prep_time,
            s.storage_method,
            s.temperature_c,
            s.notes,
            TIMESTAMPDIFF(
                MINUTE, s.prep_time, NOW()
            ) AS minutes_since_prep
        FROM storage_records s
        JOIN food_items f
            ON f.item_id = s.item_id
        ORDER BY s.prep_time DESC
        LIMIT 100
    """)

    for row in rows:

        row["alerts"] = storage_alerts(
            row["storage_method"],
            row["temperature_c"],
            row["minutes_since_prep"]
        )

        row["hours_since_prep"] = round(
            row["minutes_since_prep"] / 60, 1
        )

        if any(
            alert["level"] == "warning"
            for alert in row["alerts"]
        ):
            row["alert_level"] = "warning"

        elif row["alerts"]:
            row["alert_level"] = "info"

        else:
            row["alert_level"] = "ok"

    return jsonify(rows)


@app.route("/api/storage", methods=["POST"])
def add_storage():

    data = get_data()

    item_id = read_int(
        data, "item_id", "Food item", 1
    )

    ensure_exists(
        "food_items", "item_id", item_id, "Food item"
    )

    prep_time = read_datetime(
        data, "prep_time", "Preparation time"
    )

    method = read_choice(
        data,
        "storage_method",
        "Storage method",
        STORAGE_METHODS
    )

    temperature = read_optional_temperature(
        data, "temperature_c"
    )

    notes = read_text(
        data, "notes", "Notes", 255, required=False
    ) or None

    new_id = db_execute(
        """
        INSERT INTO storage_records
        (
            item_id,
            prep_time,
            storage_method,
            temperature_c,
            notes
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            item_id,
            prep_time,
            method,
            temperature,
            notes
        )
    )

    return jsonify(
        message="Storage record saved.",
        storage_id=new_id
    ), 201


@app.route("/api/storage/<int:storage_id>", methods=["DELETE"])
def delete_storage(storage_id):

    ensure_exists(
        "storage_records",
        "storage_id",
        storage_id,
        "Storage record"
    )

    db_execute(
        "DELETE FROM storage_records WHERE storage_id = %s",
        (storage_id,)
    )

    return jsonify(message="Storage record deleted.")


# =====================================================================
# =====================================================================
# 13. START THE APP
# =====================================================================

def split_sql(text):
    """Split SQL text into statements."""

    statements = []
    current = []
    quote = None
    i = 0

    while i < len(text):

        ch = text[i]

        if quote:
            current.append(ch)

            if ch == quote:
                quote = None

        elif ch in ("'", '"'):
            quote = ch
            current.append(ch)

        elif ch == "-" and text.startswith("--", i):

            while i < len(text) and text[i] != "\n":
                i += 1

            continue

        elif ch == ";":

            statement = "".join(current).strip()

            if statement:
                statements.append(statement)

            current = []

        else:
            current.append(ch)

        i += 1

    last = "".join(current).strip()

    if last:
        statements.append(last)

    return statements


def create_database_from_schema():
    """Create database from schema.sql if database is missing."""

    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "schema.sql"
    )

    if not os.path.exists(path):
        print(
            "schema.sql was not found next to app.py "
            "- cannot create the database."
        )
        return False

    with open(path, encoding="utf-8") as file:
        statements = split_sql(file.read())

    server_only = {
        key: value
        for key, value in DB_CONFIG.items()
        if key != "database"
    }

    conn = mysql.connector.connect(**server_only)

    try:
        cursor = conn.cursor()

        for statement in statements:
            cursor.execute(statement)

        conn.commit()
        cursor.close()

    finally:
        conn.close()

    print(
        f"Database created from schema.sql "
        f"({len(statements)} statements) with sample data."
    )

    return True


def check_mysql_at_startup():
    """Check MySQL connection and request password if needed."""

    for attempt in range(5):

        try:
            get_connection().close()
            print("Connected to MySQL successfully.")
            return True

        except mysql.connector.Error as err:

            if getattr(err, "errno", None) == 1045:

                print(
                    f"MySQL rejected the password "
                    f"for user '{DB_CONFIG['user']}'."
                )

                try:
                    typed = getpass.getpass(
                        "Type your MySQL password "
                        "(typing is hidden), then press Enter: "
                    )

                except (EOFError, KeyboardInterrupt):
                    break

                DB_CONFIG["password"] = typed
                os.environ["DB_PASSWORD"] = typed

            elif getattr(err, "errno", None) == 1049:

                print(
                    "The database 'demand_prediction_db' "
                    "does not exist - creating it from schema.sql ..."
                )

                try:

                    if not create_database_from_schema():
                        return False

                except mysql.connector.Error as create_err:

                    print(
                        "Could not create the database automatically ->",
                        create_err
                    )

                    print(
                        "Open schema.sql in MySQL Workbench "
                        "and run it, then start again."
                    )

                    return False

            elif getattr(err, "errno", None) in (
                2002, 2003, 2013
            ):

                print(
                    "Cannot reach MySQL server. "
                    "Start the MySQL service."
                )

                return False

            else:

                print(
                    "WARNING: could not connect to MySQL ->",
                    err
                )

                return False

    print(
        "Could not log in to MySQL. "
        "The page will show an error until this is fixed."
    )

    return False


# =====================================================================
# REAL NEARBY PLACES: BHIMTAL + 20 KM (OPENSTREETMAP / OVERPASS)
# These are mapped OSM features, not invented database sample records.
# =====================================================================

BHIMTAL_CENTER = {"lat": 29.3500, "lon": 79.5667}
BHIMTAL_RADIUS_METRES = 20000


@app.route("/api/nearby-facilities")
def nearby_facilities():
    """Return mapped food-relief and waste-related places around Bhimtal."""
    overpass_query = f"""
    [out:json][timeout:25];
    (
      node(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[amenity=food_bank];
      way(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[amenity=food_bank];
      relation(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[amenity=food_bank];

      node(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[social_facility];
      way(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[social_facility];
      relation(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[social_facility];

      node(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[office=ngo];
      way(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[office=ngo];
      relation(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[office=ngo];

      node(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[amenity=recycling];
      way(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[amenity=recycling];
      relation(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[amenity=recycling];

      node(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[landuse=landfill];
      way(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[landuse=landfill];
      relation(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[landuse=landfill];

      node(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[office=government];
      way(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[office=government];
      relation(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[office=government];

      node(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[amenity=townhall];
      way(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[amenity=townhall];
      relation(around:{BHIMTAL_RADIUS_METRES},{BHIMTAL_CENTER['lat']},{BHIMTAL_CENTER['lon']})[amenity=townhall];
    );
    out center tags;
    """

    try:
        req = Request(
            "https://overpass-api.de/api/interpreter",
            data=urlencode({"data": overpass_query}).encode("utf-8"),
            headers={
                "User-Agent": "DemandPredictionPBL/1.0 (Bhimtal nearby map)",
                "Content-Type": "application/x-www-form-urlencoded"
            },
            method="POST"
        )
        with urlopen(req, timeout=35) as response:
            payload = json.loads(response.read().decode("utf-8"))

        places = []
        seen = set()

        for element in payload.get("elements", []):
            tags = element.get("tags", {})
            lat = element.get("lat") or element.get("center", {}).get("lat")
            lon = element.get("lon") or element.get("center", {}).get("lon")
            if lat is None or lon is None:
                continue

            if tags.get("amenity") == "food_bank":
                category = "Food bank"
            elif tags.get("social_facility"):
                category = "Social facility"
            elif tags.get("office") == "ngo":
                category = "NGO"
            elif tags.get("amenity") == "recycling":
                category = "Recycling point"
            elif tags.get("landuse") == "landfill":
                category = "Waste site"
            elif tags.get("office") == "government" or tags.get("amenity") == "townhall":
                category = "Civic office"
            else:
                continue

            name = tags.get("name") or tags.get("operator") or category
            key = (round(float(lat), 5), round(float(lon), 5), name.lower())
            if key in seen:
                continue
            seen.add(key)

            address_parts = [
                tags.get("addr:street"),
                tags.get("addr:suburb"),
                tags.get("addr:city")
            ]
            address = ", ".join(p for p in address_parts if p) or "Address not listed in OpenStreetMap"

            places.append({
                "id": f"osm-{element.get('type')}-{element.get('id')}",
                "name": name,
                "category": category,
                "lat": float(lat),
                "lon": float(lon),
                "address": address,
                "phone": tags.get("phone") or tags.get("contact:phone") or "",
                "website": tags.get("website") or tags.get("contact:website") or "",
                "osm_url": f"https://www.openstreetmap.org/{element.get('type')}/{element.get('id')}",
                "source": "OpenStreetMap"
            })

        return jsonify(
            center=BHIMTAL_CENTER,
            radius_km=20,
            source="OpenStreetMap",
            places=places,
            count=len(places),
            note="OSM coverage varies. Call the organisation before arranging food pickup."
        )

    except Exception as err:
        app.logger.warning("OpenStreetMap lookup failed: %s", err)
        return jsonify(
            error="Nearby map data is temporarily unavailable. Please retry.",
            center=BHIMTAL_CENTER,
            radius_km=20,
            places=[]
        ), 503


# =====================================================================
# =====================================================================
# PHASE 3: INVENTORY, DONATION WORKFLOW, FORECASTING & SIMULATION
# =====================================================================

@app.route("/api/phase3/summary")
def phase3_summary():

    inventory = db_query("""
        SELECT
            i.ingredient_id,
            i.ingredient_name,
            i.unit,
            i.reorder_level,
            COALESCE(v.quantity, 0) AS quantity,
            CASE
                WHEN COALESCE(v.quantity, 0) <= i.reorder_level
                THEN 1 ELSE 0
            END AS low_stock
        FROM ingredients i
        LEFT JOIN inventory v
            ON v.ingredient_id = i.ingredient_id
        ORDER BY i.ingredient_name
    """)

    donations = db_query("""
        SELECT
            d.donation_id,
            d.requested_quantity,
            d.status,
            d.pickup_time,
            d.created_at,
            s.surplus_id,
            s.status AS surplus_status,
            f.facility_name,
            fi.item_name
        FROM donation_requests d
        JOIN surplus_records s
            ON s.surplus_id = d.surplus_id
        JOIN daily_records dr
            ON dr.record_id = s.record_id
        JOIN food_items fi
            ON fi.item_id = dr.item_id
        LEFT JOIN facilities f
            ON f.facility_id = d.facility_id
        ORDER BY d.created_at DESC
        LIMIT 100
    """)

    return jsonify(
        inventory=inventory,
        donations=donations
    )


# =====================================================================
# ADD INGREDIENT
# =====================================================================

@app.route("/api/phase3/ingredients", methods=["POST"])
def phase3_add_ingredient():

    data = get_data()

    name = read_text(
        data, "ingredient_name", "Ingredient name", 100
    )

    unit = read_text(
        data, "unit", "Unit", 20
    )

    reorder = read_money(
        data, "reorder_level", "Reorder level", 0, 10000000
    )

    quantity = read_money(
        data, "quantity", "Opening quantity", 0, 10000000
    )

    conn = get_connection()

    try:
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO ingredients
            (ingredient_name, unit, reorder_level)
            VALUES (%s, %s, %s)
        """, (name, unit, reorder))

        ingredient_id = cur.lastrowid

        cur.execute("""
            INSERT INTO inventory
            (ingredient_id, quantity)
            VALUES (%s, %s)
        """, (ingredient_id, quantity))

        cur.execute("""
            INSERT INTO audit_logs
            (entity_type, entity_id, action_type, details)
            VALUES ('ingredient', %s, 'CREATE', %s)
        """, (
            ingredient_id,
            f"Created {name}; opening stock {quantity} {unit}"
        ))

        conn.commit()

        return jsonify(
            message="Ingredient and opening stock saved.",
            ingredient_id=ingredient_id
        ), 201

    except mysql.connector.IntegrityError as err:

        conn.rollback()

        if err.errno == 1062:
            raise ValidationError(
                "Ingredient already exists.", 409
            )

        raise

    finally:
        conn.close()


# =====================================================================
# UPDATE INVENTORY
# =====================================================================

@app.route(
    "/api/phase3/inventory/<int:ingredient_id>",
    methods=["PUT"]
)
def phase3_update_inventory(ingredient_id):

    data = get_data()

    quantity = read_money(
        data, "quantity", "Quantity", 0, 10000000
    )

    conn = get_connection()

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT inventory_id
            FROM inventory
            WHERE ingredient_id = %s
            FOR UPDATE
        """, (ingredient_id,))

        if not cur.fetchone():
            raise ValidationError(
                "Ingredient inventory not found.", 404
            )

        cur.execute("""
            UPDATE inventory
            SET quantity = %s
            WHERE ingredient_id = %s
        """, (quantity, ingredient_id))

        cur.execute("""
            INSERT INTO audit_logs
            (entity_type, entity_id, action_type, details)
            VALUES ('inventory', %s, 'ADJUST', %s)
        """, (
            ingredient_id,
            f"Stock adjusted to {quantity}"
        ))

        conn.commit()

        return jsonify(message="Inventory updated.")

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# =====================================================================
# =====================================================================
# CREATE DONATION REQUEST
# =====================================================================

@app.route("/api/phase3/donations", methods=["POST"])
def phase3_create_donation():

    data = get_data()

    surplus_id = read_int(
        data, "surplus_id", "Surplus record", 1
    )

    quantity = read_int(
        data, "requested_quantity", "Requested quantity", 1
    )

    facility_raw = data.get("facility_id")

    facility_id = (
        int(facility_raw)
        if facility_raw not in (None, "", "null")
        else None
    )

    notes = read_text(
        data, "notes", "Notes", 255, required=False
    ) or None

    conn = get_connection()

    try:
        cur = conn.cursor(dictionary=True)

        cur.execute("""
            SELECT quantity, status, facility_id
            FROM surplus_records
            WHERE surplus_id = %s
            FOR UPDATE
        """, (surplus_id,))

        surplus = cur.fetchone()

        if not surplus:
            raise ValidationError(
                "Surplus record not found.", 404
            )

        if surplus["status"] != "Available":
            raise ValidationError(
                "Only Available surplus can be requested for donation.",
                409
            )

        cur.execute("""
            SELECT COALESCE(
                SUM(requested_quantity), 0
            ) AS total
            FROM donation_requests
            WHERE surplus_id = %s
              AND status NOT IN ('Rejected', 'Cancelled')
        """, (surplus_id,))

        already = int(cur.fetchone()["total"])

        if quantity + already > int(surplus["quantity"]):
            raise ValidationError(
                "Requested quantity exceeds available surplus.",
                400
            )

        if facility_id:

            cur.execute("""
                SELECT facility_id
                FROM facilities
                WHERE facility_id = %s
            """, (facility_id,))

            if not cur.fetchone():
                raise ValidationError(
                    "Facility not found.", 404
                )

        cur.execute("""
            INSERT INTO donation_requests
            (
                surplus_id,
                facility_id,
                requested_quantity,
                notes
            )
            VALUES (%s, %s, %s, %s)
        """, (
            surplus_id,
            facility_id,
            quantity,
            notes
        ))

        donation_id = cur.lastrowid

        cur.execute("""
            INSERT INTO audit_logs
            (entity_type, entity_id, action_type, details)
            VALUES ('donation', %s, 'CREATE', %s)
        """, (
            donation_id,
            f"Donation requested: surplus {surplus_id}, quantity {quantity}"
        ))

        conn.commit()

        return jsonify(
            message="Donation request created.",
            donation_id=donation_id
        ), 201

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# =====================================================================
# UPDATE DONATION STATUS
# =====================================================================

@app.route(
    "/api/phase3/donations/<int:donation_id>",
    methods=["PUT"]
)
def phase3_update_donation(donation_id):

    data = get_data()

    status = read_choice(
        data,
        "status",
        "Status",
        [
            "Requested",
            "Accepted",
            "Rejected",
            "Pickup Scheduled",
            "Collected",
            "Cancelled"
        ]
    )

    pickup = data.get("pickup_time") or None

    if pickup:
        try:
            pickup = datetime.strptime(
                pickup, "%Y-%m-%dT%H:%M"
            )
        except ValueError:
            raise ValidationError(
                "Pickup time must be valid."
            )

    conn = get_connection()

    try:
        cur = conn.cursor(dictionary=True)

        cur.execute("""
            SELECT
                donation_id,
                surplus_id,
                requested_quantity,
                status
            FROM donation_requests
            WHERE donation_id = %s
            FOR UPDATE
        """, (donation_id,))

        row = cur.fetchone()

        if not row:
            raise ValidationError(
                "Donation request not found.", 404
            )

        cur.execute("""
            UPDATE donation_requests
            SET status = %s,
                pickup_time = %s
            WHERE donation_id = %s
        """, (status, pickup, donation_id))

        if status == "Collected":
            cur.execute("""
                SELECT
                    s.quantity,
                    COALESCE(SUM(
                        CASE WHEN d.status = 'Collected'
                             THEN d.requested_quantity ELSE 0 END
                    ), 0) AS collected_qty
                FROM surplus_records s
                LEFT JOIN donation_requests d
                    ON d.surplus_id = s.surplus_id
                WHERE s.surplus_id = %s
                GROUP BY s.surplus_id, s.quantity
                FOR UPDATE
            """, (row["surplus_id"],))
            totals = cur.fetchone()
            if totals and int(totals["collected_qty"]) >= int(totals["quantity"]):
                cur.execute("""
                    UPDATE surplus_records
                    SET status = 'Donated'
                    WHERE surplus_id = %s
                """, (row["surplus_id"],))

        cur.execute("""
            INSERT INTO audit_logs
            (entity_type, entity_id, action_type, details)
            VALUES ('donation', %s, 'STATUS', %s)
        """, (
            donation_id,
            f"Status changed to {status}"
        ))

        conn.commit()

        return jsonify(
            message="Donation status updated."
        )

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# =====================================================================
# =====================================================================
# PHASE 3: DEMAND FORECAST
# =====================================================================

@app.route("/api/phase3/forecast")
def phase3_forecast():

    rows = db_query("""
        SELECT
            f.item_id,
            f.item_name,
            COUNT(x.sold_qty) AS records_used,
            COALESCE(AVG(x.sold_qty), 0) AS avg_sales
        FROM food_items f
        LEFT JOIN (
            SELECT
                d1.item_id,
                d1.sold_qty
            FROM daily_records d1
            JOIN (
                SELECT
                    item_id,
                    record_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY item_id
                        ORDER BY record_date DESC
                    ) AS rn
                FROM daily_records
            ) ranked
                ON ranked.record_id = d1.record_id
            WHERE ranked.rn <= 7
        ) x
            ON x.item_id = f.item_id
        GROUP BY f.item_id, f.item_name
        ORDER BY f.item_name
    """)

    for row in rows:

        row["recommended_qty"] = math.ceil(
            float(row["avg_sales"] or 0) * 1.05
        )

        row["avg_sales"] = round(
            float(row["avg_sales"] or 0), 2
        )

    return jsonify(rows)


# =====================================================================
# PHASE 3: WHAT-IF SIMULATION
# =====================================================================

@app.route("/api/phase3/simulation", methods=["POST"])
def phase3_simulation():

    data = get_data()

    item_id = read_int(
        data, "item_id", "Food item", 1
    )

    demand = read_int(
        data, "expected_demand", "Expected demand",
        0, 1000000
    )

    buffer = read_int(
        data, "buffer_percent", "Buffer percentage",
        0, 100
    )

    ensure_exists(
        "food_items", "item_id", item_id, "Food item"
    )

    rows = db_query("""
        SELECT selling_price, production_cost
        FROM food_items
        WHERE item_id = %s
    """, (item_id,))

    price = float(rows[0]["selling_price"])
    cost = float(rows[0]["production_cost"])

    prepared = math.ceil(
        demand * (1 + buffer / 100)
    )

    leftover = max(0, prepared - demand)

    return jsonify(
        expected_demand=demand,
        recommended_preparation=prepared,
        estimated_leftover=leftover,
        estimated_waste_cost=round(leftover * cost, 2),
        estimated_revenue=round(
            min(prepared, demand) * price, 2
        ),
        buffer_percent=buffer
    )


# =====================================================================
# PHASE 3: AUDIT LOG
# =====================================================================

@app.route("/api/phase3/audit")
def phase3_audit():

    return jsonify(db_query("""
        SELECT
            audit_id,
            entity_type,
            entity_id,
            action_type,
            details,
            created_at
        FROM audit_logs
        ORDER BY created_at DESC
        LIMIT 100
    """))


@app.route("/api/phase3/health")
def phase3_health():

    return jsonify(
        status="ok",
        modules=[
            "inventory",
            "donations",
            "forecast",
            "simulation",
            "audit"
        ]
    )


# =====================================================================
# =====================================================================
# RUN FLASK APPLICATION
# =====================================================================

if __name__ == "__main__":

    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":

        if check_mysql_at_startup():

            try:
                upgrade_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "phase3_upgrade.sql"
                )

                with open(
                    upgrade_path,
                    encoding="utf-8"
                ):
                    pass

                print(
                    "Run phase3_upgrade.sql once in MySQL Workbench."
                )

            except Exception as upgrade_error:

                print(
                    "Phase 3 migration notice:",
                    upgrade_error
                )

    print(
        "Backend running at http://127.0.0.1:5000"
    )

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
