import export_pb2
import requests
import logging
import io
from zipfile import ZipFile

log = logging.getLogger(__name__)

ENDPOINT = "https://distribution-te-prod.prod.svc-test-trace.nhs.uk"

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


def get_risky_venues():
    log.info("Fetching venues...")
    res = requests.get(ENDPOINT + '/distribution/risky-venues')
    res.raise_for_status()
    return res.json()

