# -*- coding: utf-8 -*-
"""
DSBApi
An API for the DSBMobile substitution plan solution, which many schools use.
"""

from __future__ import annotations

import base64
import datetime
import gzip
import io
import json
import uuid

import bs4
import requests

try:
    from PIL import Image
except ImportError:  # pragma: no cover - Pillow is the supported dependency
    import Image  # type: ignore[no-redef]

try:
    from pytesseract import TesseractError
except ImportError:  # pragma: no cover - older pytesseract exports may differ
    TesseractError = RuntimeError

import pytesseract

__version_info__ = ("0", "0", "14")
__version__ = ".".join(__version_info__)

DEFAULT_TABLEMAPPER = [
    "type",
    "class",
    "lesson",
    "subject",
    "room",
    "new_subject",
    "new_teacher",
    "teacher",
]


class DSBApi:
    def __init__(self, username, password, tablemapper=None, timeout=15):
        """
        Class constructor for class DSBApi.

        @param username: string, the username of the DSBMobile account
        @param password: string, the password of the DSBMobile account
        @param tablemapper: list, the field mapping of the DSBMobile tables
        @param timeout: int/float, request timeout in seconds
        @raise TypeError: If the attribute tablemapper is not of type list
        """
        self.DATA_URL = "https://app.dsbcontrol.de/JsonHandler.ashx/GetData"
        self.username = username
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()

        if tablemapper is None:
            tablemapper = list(DEFAULT_TABLEMAPPER)
        if not isinstance(tablemapper, list):
            raise TypeError("Attribute tablemapper is not of type list!")
        self.tablemapper = tablemapper
        self.class_index = self._find_class_index()

    def _find_class_index(self):
        for index, value in enumerate(self.tablemapper):
            if value == "class":
                return index
        return None

    def _request_json(self, url, **kwargs):
        response = self.session.request(url=url, timeout=self.timeout, **kwargs)
        response.raise_for_status()
        return response.json()

    def _request_text(self, url):
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    def _request_bytes(self, url):
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.content

    def fetch_entries(self, images=True):
        """
        Fetch all DSBMobile entries.

        @return: list, containing lists of DSBMobile entries from the tables or
                 only the entries if just one table was received
        @raise Exception: If the request to DSBMobile failed
        """
        current_time = datetime.datetime.utcnow().isoformat(timespec="milliseconds") + "Z"

        params = {
            "UserId": self.username,
            "UserPw": self.password,
            "AppVersion": "2.5.9",
            "Language": "de",
            "OsVersion": "28 8.0",
            "AppId": str(uuid.uuid4()),
            "Device": "SM-G930F",
            "BundleId": "de.heinekingmedia.dsbmobile",
            "Date": current_time,
            "LastUpdate": current_time,
        }

        params_bytestring = json.dumps(params, separators=(",", ":")).encode("utf-8")
        params_compressed = base64.b64encode(gzip.compress(params_bytestring)).decode("utf-8")
        json_data = {"req": {"Data": params_compressed, "DataType": 1}}
        payload = self._request_json(self.DATA_URL, method="post", json=json_data)

        try:
            data_compressed = payload["d"]
            data = json.loads(gzip.decompress(base64.b64decode(data_compressed)))
        except (KeyError, ValueError, OSError, TypeError) as exc:
            raise Exception("Received invalid response payload from DSBMobile") from exc

        if data.get("Resultcode") != 0:
            raise Exception(data.get("ResultStatusInfo", "Unknown DSBMobile error"))

        detail_urls = self._extract_detail_urls(data)
        if not detail_urls:
            raise Exception("Timetable data could not be found")

        output = []
        for entry in detail_urls:
            if entry.endswith(".htm") and not entry.endswith(".html") and not entry.endswith("news.htm"):
                output.append(self.fetch_timetable(entry))
            elif entry.endswith(".jpg") and images:
                image_text = self.fetch_img(entry)
                if image_text is not None:
                    output.append(image_text)

        if len(output) == 1:
            return output[0]
        return output

    def _extract_detail_urls(self, data):
        detail_urls = []
        menu_items = data.get("ResultMenuItems") or []
        if not menu_items:
            return detail_urls

        for page in menu_items[0].get("Childs", []):
            root = page.get("Root") or {}
            for child in root.get("Childs", []):
                child_nodes = child.get("Childs")
                if isinstance(child_nodes, list):
                    for sub_child in child_nodes:
                        detail = sub_child.get("Detail")
                        if detail:
                            detail_urls.append(detail)
                elif isinstance(child_nodes, dict):
                    detail = child_nodes.get("Detail")
                    if detail:
                        detail_urls.append(detail)
        return detail_urls

    def fetch_img(self, imgurl):
        """
        Extract OCR text from an image.

        @param imgurl: string, the URL to the image
        @return: string or None
        """
        try:
            image_bytes = self._request_bytes(imgurl)
            img = Image.open(io.BytesIO(image_bytes))
        except Exception:
            return None

        try:
            return pytesseract.image_to_string(img)
        except TesseractError as exc:
            raise Exception("You have to make the tesseract command accessible and work!") from exc

    def fetch_timetable(self, timetableurl):
        """
        Parse the timetable HTML page and return the parsed entries.

        @param timetableurl: string, the URL to the timetable in HTML format
        @return: list, list of dicts
        """
        results = []
        soup = bs4.BeautifulSoup(self._request_text(timetableurl), "html.parser")
        tables = soup.find_all("table", {"class": "mon_list"})
        headers = soup.find_all("table", {"class": "mon_head"})
        titles = [title.get_text(" ", strip=True) for title in soup.find_all("div", {"class": "mon_title"})]

        for index, table in enumerate(tables):
            updated = self._extract_updated(headers, index)
            date, day = self._extract_title_parts(titles, index)
            rows = table.find_all("tr")[1:]

            for row in rows:
                infos = row.find_all("td")
                if len(infos) < 2:
                    continue

                class_values = self._extract_class_values(infos)
                for class_value in class_values:
                    new_entry = {
                        "date": date,
                        "day": day,
                        "updated": updated,
                    }
                    for col_index, info in enumerate(infos):
                        attribute = self.tablemapper[col_index] if col_index < len(self.tablemapper) else "col" + str(col_index)
                        value = info.get_text(strip=True) or "---"
                        if attribute == "class":
                            new_entry[attribute] = class_value if value != "---" else "---"
                        else:
                            new_entry[attribute] = value
                    results.append(new_entry)
        return results

    def _extract_updated(self, headers, index):
        if index >= len(headers):
            return "---"

        spans = headers[index].find_all("span")
        if not spans:
            return "---"

        sibling = spans[-1].next_sibling
        if not isinstance(sibling, str):
            return "---"

        parts = sibling.split("Stand: ", 1)
        if len(parts) == 2 and parts[1].strip():
            return parts[1].strip()
        return sibling.strip() or "---"

    def _extract_title_parts(self, titles, index):
        if index >= len(titles):
            return "---", "---"

        title = titles[index].strip()
        if not title:
            return "---", "---"

        parts = title.split(" ", 1)
        date = parts[0]
        day_text = parts[1] if len(parts) > 1 else "---"
        day = day_text.split(", ", 1)[0].replace(",", "").strip() or "---"
        return date, day

    def _extract_class_values(self, infos):
        if self.class_index is None or self.class_index >= len(infos):
            return ["---"]

        raw_value = infos[self.class_index].get_text(strip=True)
        if not raw_value:
            return ["---"]

        return [part.strip() for part in raw_value.split(",") if part.strip()] or ["---"]


__all__ = ["DSBApi", "__version__", "__version_info__"]

