import sqlite3
import arrow
import requests
from requests.exceptions import HTTPError
import logging
import json

from api import get_daily_file, get_two_hourly_file, get_risky_venues

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

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

    c.execute(
        """CREATE TABLE IF NOT EXISTS risky_venues (
                    export_date INTEGER,
                    id TEXT NOT NULL,
                    risky_from INTEGER,
                    risky_until INTEGER,
                    message_type TEXT
              )"""
    )

    c.execute(
        """CREATE TABLE IF NOT EXISTS exposure_configuration (
                    date INTEGER,
                    configuration TEXT NOT NULL
              )"""
    )

    c.execute(
        """CREATE TABLE IF NOT EXISTS walk_in_pcr_availability (
                    date INTEGER NOT NULL,
                    availability TEXT NOT NULL

    )"""
    )

    c.execute(
        """CREATE TABLE IF NOT EXISTS home_test_availability (
                    date INTEGER NOT NULL,
                    pcr_keyworker TEXT NOT NULL,
                    pcr_public TEXT NOT NULL,
                    lfd_public TEXT NOT NULL
    )"""
    )

    c.execute("""CREATE TABLE IF NOT EXISTS last_update (end_timestamp INTEGER)""")

    conn.commit()


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
    risky_from = arrow.get(venue["riskyWindow"]["from"]).timestamp
    risky_until = arrow.get(venue["riskyWindow"]["until"]).timestamp
    c.execute(
        "SELECT 1 FROM risky_venues WHERE id = ? AND risky_from = ?",
        (venue["id"], risky_from),
    )

    if c.fetchone():
        return False

    c.execute(
        """INSERT INTO risky_venues (export_date, id, risky_from, risky_until, message_type)
                    VALUES (?, ?, ?, ?, ?)""",
        (
            arrow.utcnow().timestamp,
            venue["id"],
            risky_from,
            risky_until,
            venue["messageType"],
        ),
    )
    return True


def import_exposure_data():
    timestamp = get_timestamp()
    log.info("Fetching keys from timestamp %s...", timestamp)

    while timestamp < arrow.utcnow().shift(hours=-2):
        try:
            if timestamp < arrow.utcnow().shift(days=-1):
                data = get_daily_file(timestamp)
                save_timestamp(timestamp.shift(days=1))
            else:
                data = get_two_hourly_file(timestamp)
                save_timestamp(timestamp.shift(hours=2))
        except HTTPError:
            log.exception("Error fetching file")
            return

        insert_exposure_data(data)
        conn.commit()
        timestamp = get_timestamp()

    log.info("Fetched keys to timestamp %s", timestamp)


def import_risky_venues():
    data = get_risky_venues()
    seen = new = 0
    for venue in data["venues"]:
        seen += 1
        if insert_risky_venue(venue):
            new += 1

    conn.commit()

    log.info("Saw %s venues, %s new.", seen, new)


def import_exposure_configuration():
    url = "https://distribution-te-prod.prod.svc-test-trace.nhs.uk/distribution/exposure-configuration"
    config = requests.get(url).text

    c.execute(
        "SELECT configuration FROM exposure_configuration ORDER BY date DESC LIMIT 1"
    )
    res = c.fetchone()
    if res and res[0] == config:
        return

    c.execute(
        "INSERT INTO exposure_configuration (date, configuration) VALUES (?, ?)",
        (arrow.now().timestamp, config),
    )

    conn.commit()
    log.info("Inserted updated exposure configuration")


def import_test_availability():
    s = requests.Session()
    s.headers.update(
        {"Origin": "https://self-referral.test-for-coronavirus.service.gov.uk"}
    )

    # PCR walk-in availability
    res = s.get(
        "https://api-prd-prd-1-ibt.prd.ibt.test-and-trace.nhs.uk/apptbooking/testcentres/availabilitysummary"
    )

    res.raise_for_status()
    walk_in = res.json()

    c.execute("SELECT availability FROM walk_in_pcr_availability ORDER BY date DESC")
    res = c.fetchone()
    if not res or json.loads(res[0])['availability'] != walk_in['availability']:
        log.info("Inserting updated walk-in PCR availability")
        c.execute(
            "INSERT INTO walk_in_pcr_availability (date, availability) VALUES (?, ?)",
            (arrow.now().timestamp, json.dumps(walk_in)),
        )
        conn.commit()

    # PCR home tests, keyworkers
    res = s.get(
        "https://api-prd-prd-1-ibt.prd.ibt.test-and-trace.nhs.uk/ser/app/homeOrderAvailabilityStatus/antigen-keyworkers"
    )

    res.raise_for_status()
    pcr_keyworker = res.json()["status"]

    # PCR home tests, public
    res = s.get(
        "https://api-prd-prd-1-ibt.prd.ibt.test-and-trace.nhs.uk/ser/app/homeOrderAvailabilityStatus/antigen-public"
    )

    res.raise_for_status()
    pcr_public = res.json()["status"]

    # origin: https://test-for-coronavirus.service.gov.uk
    # LFD tests, public
    res = s.get(
        "https://api.test-for-coronavirus.service.gov.uk/ser/app/homeOrderAvailabilityStatus/lfd3-public"
    )
    res.raise_for_status()
    lfd_public = res.json()["status"]

    c.execute(
        "SELECT pcr_keyworker, pcr_public, lfd_public FROM home_test_availability ORDER BY date DESC"
    )
    res = c.fetchone()
    if (
        not res
        or res[0] != pcr_keyworker
        or res[1] != pcr_public
        or res[2] != lfd_public
    ):
        log.info("Inserting updated home test availability")
        c.execute(
            "INSERT INTO home_test_availability (date, pcr_keyworker, pcr_public, lfd_public) VALUES (?, ?, ?, ?)",
            (arrow.now().timestamp, pcr_keyworker, pcr_public, lfd_public),
        )
        conn.commit()


init_db()
import_exposure_data()
import_risky_venues()
import_exposure_configuration()
import_test_availability()
log.info("Run finished")
