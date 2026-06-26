#!/usr/bin/env python3
from __future__ import annotations

import calendar
import io
import json
import os
import sqlite3
import textwrap
from datetime import UTC, date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DATA_DIR = Path(os.environ.get("PAINTRACKER_DATA_DIR", ROOT / ".paintracker-data"))
DB_PATH = DATA_DIR / "paintracker.sqlite3"

ENTRY_FIELDS = (
    "entry_date",
    "pain_morning",
    "pain_noon",
    "pain_evening",
    "pain_night",
    "symptoms",
    "triggers",
    "wellbeing",
    "medication",
    "weather",
    "temperature",
    "notes",
)

PROFILE_FIELDS = (
    "name",
    "gender",
    "age",
    "weight",
    "height",
    "accident_date",
    "case_number_lawyer",
    "case_number_police",
    "lawyer",
    "diagnosis",
    "affected_joint",
    "notes",
)


def db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                name TEXT NOT NULL DEFAULT '',
                gender TEXT NOT NULL DEFAULT '',
                age TEXT NOT NULL DEFAULT '',
                weight TEXT NOT NULL DEFAULT '',
                height TEXT NOT NULL DEFAULT '',
                accident_date TEXT NOT NULL DEFAULT '',
                case_number_lawyer TEXT NOT NULL DEFAULT '',
                case_number_police TEXT NOT NULL DEFAULT '',
                lawyer TEXT NOT NULL DEFAULT '',
                diagnosis TEXT NOT NULL DEFAULT '',
                affected_joint TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        existing_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(profile)").fetchall()
        }
        for column in PROFILE_FIELDS:
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE profile ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        if "case_number" in existing_columns and "case_number_lawyer" not in existing_columns:
            conn.execute(
                """
                UPDATE profile
                SET case_number_lawyer = case_number
                WHERE case_number_lawyer = '' AND case_number != ''
                """
            )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                entry_date TEXT PRIMARY KEY,
                pain_morning INTEGER,
                pain_noon INTEGER,
                pain_evening INTEGER,
                pain_night INTEGER,
                symptoms TEXT NOT NULL DEFAULT '',
                triggers TEXT NOT NULL DEFAULT '',
                wellbeing TEXT NOT NULL DEFAULT '',
                medication TEXT NOT NULL DEFAULT '',
                weather TEXT NOT NULL DEFAULT '',
                temperature TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        migrate_entry_timestamps(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO profile (id, updated_at)
            VALUES (1, ?)
            """,
            (datetime.now(UTC).isoformat(timespec="seconds"),),
        )


def migrate_entry_timestamps(conn: sqlite3.Connection) -> None:
    marker = conn.execute(
        "SELECT value FROM meta WHERE key = 'entry_timestamps_backfilled'"
    ).fetchone()
    if marker:
        return
    conn.execute(
        """
        UPDATE entries
        SET created_at = entry_date,
            updated_at = entry_date
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO meta (key, value)
        VALUES ('entry_timestamps_backfilled', '1')
        """
    )


def row_to_dict(row: sqlite3.Row | None) -> dict:
    return dict(row) if row else {}


def parse_json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


def clean_text(value: object) -> str:
    return str(value or "").strip()


def clean_pain(value: object) -> int | None:
    if value in ("", None):
        return None
    number = int(value)
    if number < 0 or number > 10:
        raise ValueError("Pain values must be between 0 and 10.")
    return number


def valid_date(value: str) -> str:
    datetime.strptime(value, "%Y-%m-%d")
    return value


def is_future_date(value: str) -> bool:
    return value > date.today().isoformat()


def json_response(handler: BaseHTTPRequestHandler, payload: object, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def bytes_response(handler: BaseHTTPRequestHandler, body: bytes, content_type: str, filename: str | None = None) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    if filename:
        handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    handler.end_headers()
    handler.wfile.write(body)


def get_profile() -> dict:
    with db() as conn:
        return row_to_dict(conn.execute("SELECT * FROM profile WHERE id = 1").fetchone())


def save_profile(payload: dict) -> dict:
    data = {field: clean_text(payload.get(field)) for field in PROFILE_FIELDS}
    data["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    with db() as conn:
        conn.execute(
            """
            UPDATE profile
            SET name = :name,
                gender = :gender,
                age = :age,
                weight = :weight,
                height = :height,
                accident_date = :accident_date,
                case_number_lawyer = :case_number_lawyer,
                case_number_police = :case_number_police,
                lawyer = :lawyer,
                diagnosis = :diagnosis,
                affected_joint = :affected_joint,
                notes = :notes,
                updated_at = :updated_at
            WHERE id = 1
            """,
            data,
        )
    return get_profile()


def get_entries(year: int | None = None, month: int | None = None) -> list[dict]:
    where = ""
    params: tuple[object, ...] = ()
    if year and month:
        where = "WHERE entry_date BETWEEN ? AND ?"
        last_day = calendar.monthrange(year, month)[1]
        params = (f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}")
    with db() as conn:
        rows = conn.execute(
            f"SELECT * FROM entries {where} ORDER BY entry_date DESC",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def get_entry(entry_date: str) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM entries WHERE entry_date = ?", (entry_date,)).fetchone()
    return row_to_dict(row)


def save_entry(payload: dict) -> dict:
    entry_date = valid_date(clean_text(payload.get("entry_date")))
    if is_future_date(entry_date):
        raise ValueError("Zukünftige Tage können nicht bearbeitet werden.")
    now = datetime.now(UTC).isoformat(timespec="seconds")
    data = {
        "entry_date": entry_date,
        "pain_morning": clean_pain(payload.get("pain_morning")),
        "pain_noon": clean_pain(payload.get("pain_noon")),
        "pain_evening": clean_pain(payload.get("pain_evening")),
        "pain_night": clean_pain(payload.get("pain_night")),
        "symptoms": clean_text(payload.get("symptoms")),
        "triggers": clean_text(payload.get("triggers")),
        "wellbeing": clean_text(payload.get("wellbeing")),
        "medication": clean_text(payload.get("medication")),
        "weather": clean_text(payload.get("weather")),
        "temperature": clean_text(payload.get("temperature")),
        "notes": clean_text(payload.get("notes")),
        "created_at": now,
        "updated_at": now,
    }
    with db() as conn:
        conn.execute(
            """
            INSERT INTO entries (
                entry_date, pain_morning, pain_noon, pain_evening, pain_night,
                symptoms, triggers, wellbeing, medication, weather, temperature,
                notes, created_at, updated_at
            )
            VALUES (
                :entry_date, :pain_morning, :pain_noon, :pain_evening, :pain_night,
                :symptoms, :triggers, :wellbeing, :medication, :weather, :temperature,
                :notes, :created_at, :updated_at
            )
            ON CONFLICT(entry_date) DO UPDATE SET
                pain_morning = excluded.pain_morning,
                pain_noon = excluded.pain_noon,
                pain_evening = excluded.pain_evening,
                pain_night = excluded.pain_night,
                symptoms = excluded.symptoms,
                triggers = excluded.triggers,
                wellbeing = excluded.wellbeing,
                medication = excluded.medication,
                weather = excluded.weather,
                temperature = excluded.temperature,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            data,
        )
    return get_entry(entry_date)


def delete_entry(entry_date: str) -> None:
    valid_date(entry_date)
    with db() as conn:
        conn.execute("DELETE FROM entries WHERE entry_date = ?", (entry_date,))


def pdf_escape(text: object) -> str:
    value = str(text if text is not None else "")
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class SimplePdf:
    def __init__(self) -> None:
        self.pages: list[str] = []
        self.commands: list[str] = []
        self.width = 595
        self.height = 842

    def add_page(self) -> None:
        if self.commands:
            self.pages.append("\n".join(self.commands))
        self.commands = []

    def text(self, x: float, y: float, value: object, size: int = 10, bold: bool = False) -> None:
        font = "F2" if bold else "F1"
        self.commands.append(f"BT /{font} {size} Tf {x:.2f} {y:.2f} Td ({pdf_escape(value)}) Tj ET")

    def line(self, x1: float, y1: float, x2: float, y2: float, width: float = 0.6) -> None:
        self.commands.append(f"{width:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def rect(self, x: float, y: float, w: float, h: float, fill: bool = False) -> None:
        op = "f" if fill else "S"
        self.commands.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re {op}")

    def fill_rgb(self, r: float, g: float, b: float) -> None:
        self.commands.append(f"{r:.3f} {g:.3f} {b:.3f} rg")

    def stroke_rgb(self, r: float, g: float, b: float) -> None:
        self.commands.append(f"{r:.3f} {g:.3f} {b:.3f} RG")

    def wrapped(self, x: float, y: float, value: object, width: int = 80, size: int = 9, line_height: int = 13, max_lines: int = 4) -> float:
        text = clean_text(value) or "-"
        lines = textwrap.wrap(text, width=width)[:max_lines] or ["-"]
        for line in lines:
            self.text(x, y, line, size=size)
            y -= line_height
        return y

    def build(self) -> bytes:
        if self.commands:
            self.pages.append("\n".join(self.commands))

        objects = [
            "<< /Type /Catalog /Pages 2 0 R >>",
            "",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        ]
        page_refs = []
        for page in self.pages:
            content_obj = len(objects) + 2
            page_obj = len(objects) + 1
            page_refs.append(f"{page_obj} 0 R")
            objects.append(
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.width} {self.height}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_obj} 0 R >>"
            )
            stream = page.encode("latin-1", errors="replace")
            objects.append(f"<< /Length {len(stream)} >>\nstream\n{page}\nendstream")
        objects[1] = f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>"

        buffer = io.BytesIO()
        buffer.write(b"%PDF-1.4\n")
        offsets = [0]
        for idx, obj in enumerate(objects, start=1):
            offsets.append(buffer.tell())
            buffer.write(f"{idx} 0 obj\n{obj}\nendobj\n".encode("latin-1", errors="replace"))
        xref = buffer.tell()
        buffer.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        buffer.write(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            buffer.write(f"{offset:010d} 00000 n \n".encode("ascii"))
        buffer.write(
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
        )
        return buffer.getvalue()


def fmt_date(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").strftime("%d.%m.%Y")


def fmt_optional_date(value: object) -> str:
    text = clean_text(value)
    if not text:
        return "-"
    try:
        return fmt_date(text)
    except ValueError:
        return text


def fmt_history_stamp(value: object) -> str:
    text = clean_text(value)
    if not text:
        return "-"
    if "T" in text:
        try:
            stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return stamp.strftime("%d.%m.%Y %H:%M")
        except ValueError:
            return text
    try:
        return fmt_date(text)
    except ValueError:
        return text


def draw_field(
    pdf: SimplePdf,
    label: str,
    value: object,
    x: float,
    y: float,
    width: float = 225,
    max_lines: int = 3,
) -> None:
    pdf.text(x, y, label, size=9, bold=True)
    pdf.line(x, y - 5, x + width, y - 5)
    pdf.wrapped(x, y - 18, value, width=max(20, int(width / 5.5)), max_lines=max_lines)


def short_value(value: object, max_len: int = 28) -> str:
    text = clean_text(value) or "-"
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 1]}."


def footer_text(profile: dict) -> str:
    parts = [
        f"Name: {short_value(profile.get('name'))}",
        f"Unfalltag: {fmt_optional_date(profile.get('accident_date'))}",
        f"Az. Anwalt: {short_value(profile.get('case_number_lawyer'), 18)}",
        f"Az. Polizei: {short_value(profile.get('case_number_police'), 18)}",
    ]
    return " | ".join(parts)


def add_footer(pdf: SimplePdf, profile: dict, page_no: int, entry: dict | None = None) -> None:
    pdf.stroke_rgb(0.70, 0.76, 0.78)
    pdf.line(45, 54, 550, 54)
    pdf.fill_rgb(0.25, 0.31, 0.34)
    pdf.text(45, 38, footer_text(profile), size=8)
    if entry is not None:
        pdf.text(45, 24, f"Geändert: {fmt_history_stamp(entry.get('updated_at'))}", size=8)
    pdf.text(505, 38, f"Seite {page_no}", size=8)
    pdf.fill_rgb(0, 0, 0)
    pdf.stroke_rgb(0, 0, 0)


def add_entry_page(pdf: SimplePdf, entry: dict, day_no: int, profile: dict, page_no: int) -> None:
    pdf.add_page()
    pdf.stroke_rgb(0.1, 0.28, 0.34)
    pdf.fill_rgb(0.1, 0.28, 0.34)
    pdf.text(45, 790, f"{day_no}. Tag", size=22, bold=True)
    pdf.text(430, 790, fmt_date(entry["entry_date"]), size=14, bold=True)
    pdf.fill_rgb(0, 0, 0)

    pdf.text(45, 745, "Schmerzintensität", size=13, bold=True)
    labels = [("morgens", "pain_morning"), ("mittags", "pain_noon"), ("abends", "pain_evening"), ("nachts", "pain_night")]
    x0 = 125
    for n in range(11):
        pdf.text(x0 + n * 34, 720, n, size=8)
    for idx, (label, field) in enumerate(labels):
        y = 695 - idx * 28
        pdf.text(45, y, label, size=10)
        for n in range(11):
            x = x0 + n * 34
            pdf.rect(x - 5, y - 5, 12, 12)
            if entry.get(field) == n:
                pdf.fill_rgb(0.1, 0.55, 0.62)
                pdf.rect(x - 3, y - 3, 8, 8, fill=True)
                pdf.fill_rgb(0, 0, 0)

    draw_field(pdf, "Treten Begleitsymptome auf?", entry.get("symptoms"), 45, 550)
    draw_field(pdf, "Schmerzauslösende Tätigkeiten", entry.get("triggers"), 325, 550)
    draw_field(pdf, "Allgemeinbefinden", entry.get("wellbeing"), 45, 450)
    draw_field(pdf, "Eingenommene Medikamente", entry.get("medication"), 325, 450)
    weather = entry.get("weather") or "-"
    temperature = entry.get("temperature")
    if temperature:
        weather = f"{weather}, {temperature} °C"
    draw_field(pdf, "Wetter (tagsüber)", weather, 45, 350)
    draw_field(pdf, "Bemerkungen", entry.get("notes"), 45, 250, width=505)
    add_footer(pdf, profile, page_no, entry)


def make_pdf() -> bytes:
    profile = get_profile()
    entries = list(reversed(get_entries()))
    pdf = SimplePdf()
    pdf.add_page()
    pdf.fill_rgb(0.1, 0.28, 0.34)
    pdf.text(45, 775, "Schmerztagebuch", size=28, bold=True)
    pdf.fill_rgb(0, 0, 0)
    pdf.text(45, 700, "Allgemeine Informationen", size=18, bold=True)
    draw_field(pdf, "Name", profile.get("name"), 45, 660)
    draw_field(pdf, "Geschlecht", profile.get("gender"), 325, 660)
    draw_field(pdf, "Alter", profile.get("age"), 45, 565)
    draw_field(pdf, "Gewicht", f"{profile.get('weight') or '-'} kg", 185, 565, width=110)
    draw_field(pdf, "Größe", f"{profile.get('height') or '-'} cm", 325, 565, width=110)
    pdf.text(45, 480, "Fallinformationen", size=18, bold=True)
    draw_field(pdf, "Unfalldatum", fmt_optional_date(profile.get("accident_date")), 45, 440)
    draw_field(pdf, "Aktenzeichen Anwalt", profile.get("case_number_lawyer"), 325, 440)
    draw_field(pdf, "Anwalt / Kanzlei", profile.get("lawyer"), 45, 345)
    draw_field(pdf, "Aktenzeichen Polizei", profile.get("case_number_police"), 325, 345)
    draw_field(pdf, "Diagnose", profile.get("diagnosis"), 45, 250, width=505)
    draw_field(pdf, "Betroffenes Gelenk / Körperbereich", profile.get("affected_joint"), 45, 160, width=505, max_lines=2)
    draw_field(pdf, "Notizen", profile.get("notes"), 45, 105, width=340, max_lines=2)
    pdf.text(410, 105, f"Export erstellt am {datetime.now().strftime('%d.%m.%Y')}", size=9)
    pdf.text(410, 89, f"Einträge: {len(entries)}", size=9)
    add_footer(pdf, profile, 1)

    for idx, entry in enumerate(entries, start=1):
        add_entry_page(pdf, entry, idx, profile, idx + 1)
    return pdf.build()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if path == "/":
                self.serve_static("index.html")
            elif path.startswith("/static/"):
                self.serve_static(path.removeprefix("/static/"))
            elif path == "/api/profile":
                json_response(self, get_profile())
            elif path == "/api/entries":
                year = int(query["year"][0]) if query.get("year") else None
                month = int(query["month"][0]) if query.get("month") else None
                json_response(self, get_entries(year, month))
            elif path.startswith("/api/entries/"):
                json_response(self, get_entry(path.rsplit("/", 1)[-1]))
            elif path == "/export.pdf":
                bytes_response(self, make_pdf(), "application/pdf", "schmerztagebuch.pdf")
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            json_response(self, {"error": str(exc)}, status=500)

    def do_POST(self) -> None:
        try:
            if self.path == "/api/profile":
                json_response(self, save_profile(parse_json_body(self)))
            elif self.path == "/api/entries":
                json_response(self, save_entry(parse_json_body(self)))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            json_response(self, {"error": str(exc)}, status=400)

    def do_DELETE(self) -> None:
        try:
            if self.path.startswith("/api/entries/"):
                delete_entry(self.path.rsplit("/", 1)[-1])
                json_response(self, {"ok": True})
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            json_response(self, {"error": str(exc)}, status=400)

    def serve_static(self, filename: str) -> None:
        path = (STATIC_DIR / filename).resolve()
        if not str(path).startswith(str(STATIC_DIR.resolve())) or not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = "text/html; charset=utf-8"
        if path.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif path.suffix == ".js":
            content_type = "text/javascript; charset=utf-8"
        bytes_response(self, path.read_bytes(), content_type)


def main() -> None:
    init_db()
    host = os.environ.get("PAINTRACKER_HOST", "0.0.0.0")
    port = int(os.environ.get("PAINTRACKER_PORT", "8080"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Paintracker läuft auf http://{host}:{port}")
    print(f"SQLite DB: {DB_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()
