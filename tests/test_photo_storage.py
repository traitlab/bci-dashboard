"""dashboard/mission_buckets + predict/photo.py: legacy URL to private Arbutus bucket and key, SigV4 signing, credential check."""

import datetime
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "predict"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))

import mission_buckets
import photo

H = "https://" + mission_buckets.LEGACY_HOST + "/"
MISSION = "20241127_knightlangbci_wptsendero_m3e/DJI_202411271018_006_x/DJI_1_V_1536zoom.JPG"
PANAMA = "20250110_pnmcrane_wptne_m3e/DJI_202501101018_006_x/DJI_2_V_1536zoom.JPG"


@pytest.mark.parametrize("url,where", [
    (H + MISSION, ("2024-bci", "drone_missions/2024/" + MISSION)),
    (H + PANAMA, ("2024-panama", "drone_missions/2025/" + PANAMA)),
    (H + "lefolab_drone_missions_wpt/" + MISSION, ("2024-bci", "drone_missions/2024/" + MISSION)),
    (H + MISSION.replace("DJI_1_V", "DJI%201_V"),
     ("2024-bci", "drone_missions/2024/" + MISSION.replace("DJI_1_V", "DJI 1_V"))),
    ("https://example.org/" + MISSION, None),
])
def test_locate(url, where):
    assert mission_buckets.locate(url) == where


def test_s3_uri_and_other_urls():
    assert mission_buckets.s3_uri(H + PANAMA) == "s3://2024-panama/drone_missions/2025/" + PANAMA
    assert mission_buckets.s3_uri("https://example.org/a.jpg") == mission_buckets.s3_uri("") == ""


def test_unknown_mission_is_a_named_error_not_a_guess():
    with pytest.raises(mission_buckets.UnknownMission, match="20990101_nowhere_m3e"):
        mission_buckets.locate(H + "20990101_nowhere_m3e/DJI_x/DJI_1.JPG")


def test_every_mission_in_the_table_is_in_a_known_bucket_and_year_folder():
    table = mission_buckets.load_table()
    assert set(table.values()) == {"2024-bci", "2024-panama"}
    assert all(m[:4].isdigit() for m in table)


def test_sigv4_matches_botocore_reference():
    # Signature computed with botocore's S3SigV4Auth for the same request and time.
    now = datetime.datetime(2024, 11, 27, 10, 18, 31, tzinfo=datetime.timezone.utc)
    url, headers = photo.sigv4_headers("https://object-arbutus.alliancecan.ca", "2024-bci",
                                       "drone_missions/2024/ab/DJI_1.JPG",
                                       "AKIDEXAMPLE", "secretEXAMPLE", now)
    assert url == "https://object-arbutus.alliancecan.ca/2024-bci/drone_missions/2024/ab/DJI_1.JPG"
    assert headers["x-amz-date"] == "20241127T101831Z"
    assert headers["Authorization"].endswith(
        "Signature=aafb877d333e67355f6fd303b9a76f01edc35d4e22bdaca5ca7a9db3066f3fde")


def test_legacy_url_without_credentials_raises_naming_vars(monkeypatch):
    for name in photo.S3_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ARBUTUS_S3_ENDPOINT", "https://s3.example")
    monkeypatch.setattr(photo.requests, "get", lambda *a, **k: pytest.fail("network call"))
    with pytest.raises(photo.MissingStorageCredentials, match="ARBUTUS_S3_ACCESS_KEY, ARBUTUS_S3_SECRET_KEY"):
        photo.download_image(H + MISSION)


class Resp:
    def __init__(self, code):
        self.status_code, self.content = code, b"jpeg"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise photo.requests.HTTPError(str(self.status_code))


def test_download_signs_for_the_bucket_the_table_names(monkeypatch):
    monkeypatch.setenv("ARBUTUS_S3_ENDPOINT", "https://s3.example")
    monkeypatch.setenv("ARBUTUS_S3_ACCESS_KEY", "a")
    monkeypatch.setenv("ARBUTUS_S3_SECRET_KEY", "s")
    urls = []
    monkeypatch.setattr(photo.requests, "get", lambda url, **k: urls.append(url) or Resp(200))
    assert photo.download_image(H + MISSION) == b"jpeg"
    assert photo.download_image(H + PANAMA) == b"jpeg"
    assert [u.split("/")[3] for u in urls] == ["2024-bci", "2024-panama"]


def test_a_404_is_a_requests_error_with_no_second_bucket(monkeypatch):
    monkeypatch.setenv("ARBUTUS_S3_ENDPOINT", "https://s3.example")
    monkeypatch.setenv("ARBUTUS_S3_ACCESS_KEY", "a")
    monkeypatch.setenv("ARBUTUS_S3_SECRET_KEY", "s")
    calls = []
    monkeypatch.setattr(photo.requests, "get", lambda url, **k: calls.append(url) or Resp(404))
    with pytest.raises(photo.requests.HTTPError):
        photo.download_image(H + MISSION)
    assert len(calls) == 1


def test_unknown_mission_download_raises_before_any_request(monkeypatch):
    monkeypatch.setenv("ARBUTUS_S3_ENDPOINT", "https://s3.example")
    monkeypatch.setenv("ARBUTUS_S3_ACCESS_KEY", "a")
    monkeypatch.setenv("ARBUTUS_S3_SECRET_KEY", "s")
    monkeypatch.setattr(photo.requests, "get", lambda *a, **k: pytest.fail("network call"))
    with pytest.raises(mission_buckets.UnknownMission):
        photo.download_image(H + "20990101_nowhere_m3e/DJI_x/DJI_1.JPG")


def test_other_urls_stay_a_plain_get(monkeypatch):
    seen = []
    monkeypatch.setattr(photo.requests, "get", lambda url, **k: seen.append((url, k)) or Resp(200))
    assert photo.download_image("https://example.org/a.jpg") == b"jpeg"
    assert seen == [("https://example.org/a.jpg", {"timeout": 30})]
