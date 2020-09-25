import export_pb2
import sys
import sqlite3
import arrow
import requests
import io
import logging
from zipfile import ZipFile

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

ENDPOINT = "https://distribution-te-prod.prod.svc-test-trace.nhs.uk"

conn = sqlite3.connect("./nhs_covid19_app_data.db")
c = conn.cursor()


def init_db():
    c.execute(
        """CREATE TABLE IF NOT EXISTS exposure_keys (
                    export_date INTEGER,
                    transmission_risk_level INTEGER,
                    rolling_start_interval_number INTEGER,
                    rolling_period INTEGER,
                    report_type INTEGER,
                    days_since_onset_of_symptoms INTEGER
                )"""
    )

    c.execute("""CREATE TABLE IF NOT EXISTS risky_venues (
                    export_date INTEGER,
                    id TEXT NOT NULL,
                    risky_from INTEGER,
                    risky_until INTEGER,
                    message_type TEXT
              )""")

    c.execute("""CREATE TABLE IF NOT EXISTS last_update (end_timestamp INTEGER)""")

    conn.commit()


init_db()


def get_timestamp():
    c.execute("SELECT end_timestamp FROM last_update")
    result = c.fetchone()
    if result:
        return arrow.get(result[0])

    start = (
        arrow.utcnow()
        .shift(days=-13)
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )
    c.execute("INSERT INTO last_update(end_timestamp) VALUES (?)", (start.timestamp,))
    conn.commit()
    return get_timestamp()


def save_timestamp(timestamp):
    c.execute("UPDATE last_update SET end_timestamp = ?", (timestamp.timestamp,))


def insert_exposure(exposure, export_timestamp):
    c.execute(
        """INSERT INTO exposure_keys (export_date,
            transmission_risk_level, rolling_start_interval_number, rolling_period,
            report_type, days_since_onset_of_symptoms) VALUES (?, ?, ?, ?, ?, ?)""",
        (
            export_timestamp,
            exposure.transmission_risk_level,
            exposure.rolling_start_interval_number,
            exposure.rolling_period,
            exposure.report_type,
            exposure.days_since_onset_of_symptoms,
        ),
    )


def insert_exposure_data(export):
    for key in export.keys:
        insert_exposure(key, export.end_timestamp)


def insert_risky_venue(venue):
    risky_from = arrow.get(venue['riskyWindow']['from']).timestamp
    risky_until = arrow.get(venue['riskyWindow']['until']).timestamp
    c.execute("SELECT 1 FROM risky_venues WHERE id = ? AND risky_from = ?",
              (venue['id'], risky_from))

    if c.fetchone():
        return

    c.execute("""INSERT INTO risky_venues (export_date, id, risky_from, risky_until, message_type)
                    VALUES (?, ?, ?, ?, ?)""",
              (arrow.utcnow().timestamp,
               venue['id'],
               risky_from,
               risky_until,
               venue['messageType']
              ))


def fetch_exposure_data(path):
    url = ENDPOINT + path
    log.info("Fetching %s", url)
    res = requests.get(url)
    res.raise_for_status()
    with ZipFile(io.BytesIO(res.content)) as z:
        with z.open("export.bin") as export:
            exp = export_pb2.TemporaryExposureKeyExport()
            exp.ParseFromString(export.read()[16:])
    return exp


def get_daily_file(timestamp):
    path = "/distribution/daily/" + timestamp.strftime("%Y%m%d00.zip")
    return fetch_exposure_data(path)


def get_two_hourly_file(timestamp):
    path = "/distribution/two-hourly/" + timestamp.strftime("%Y%m%d%H.zip")
    return fetch_exposure_data(path)


timestamp = get_timestamp()

while timestamp < arrow.utcnow().shift(hours=-2):
    if timestamp < arrow.utcnow().replace(hour=0, minute=0, second=0, microsecond=0):
        data = get_daily_file(timestamp)
        save_timestamp(timestamp.shift(days=1))
    else:
        data = get_two_hourly_file(timestamp)
        save_timestamp(timestamp.shift(hours=2))

    insert_exposure_data(data)
    conn.commit()
    timestamp = get_timestamp()


def get_risky_venues():
    res = requests.get(ENDPOINT + '/distribution/risky-venues')
    res.raise_for_status()
    data = res.json()

    for venue in data['venues']:
        insert_risky_venue(venue)

    conn.commit()

get_risky_venues()
