from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import md5
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import pandas as pd
import requests
import urllib3

from data.finmind_client import FinMindClient, FinMindConfig


class OfficialDataError(RuntimeError):
    pass


@dataclass(slots=True)
class OfficialHybridConfig:
    cache_dir: str = ".cache/official_hybrid"
    timeout: int = 30
    use_mock_data: bool = False
    finmind_token: str | None = None
    finmind_cache_dir: str = ".cache/finmind"
    use_finmind_financials_cache: bool = True
    ssl_insecure_fallback_enabled: bool = True
    ssl_insecure_fallback_hosts: tuple[str, ...] = (
        "mopsfin.twse.com.tw",
        "openapi.twse.com.tw",
        "www.twse.com.tw",
        "www.tpex.org.tw",
    )


class OfficialHybridClient:
    """Mixed-source client.

    Daily market-heavy datasets come from official TWSE/TPEx sources.
    Low-frequency financial statements are read from local FinMind cache only.
    """

    TWSE_MI_INDEX_URL = "https://www.twse.com.tw/exchangeReport/MI_INDEX"
    TWSE_T86_URL = "https://www.twse.com.tw/fund/T86"
    TPEX_PRICE_URL = "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php"
    TPEX_INST_URL = "https://www.tpex.org.tw/web/stock/3insti/DAILY_TradE/3itrade_hedge_result.php"

    TWSE_OPENAPI_BASE = "https://openapi.twse.com.tw/v1"
    LISTED_BASIC_URL = f"{TWSE_OPENAPI_BASE}/opendata/t187ap03_L"
    LISTED_REVENUE_URL = f"{TWSE_OPENAPI_BASE}/opendata/t187ap05_L"

    LEGACY_LISTED_BASIC_URL = "https://mopsfin.twse.com.tw/opendata/t187ap03_L.csv"
    LEGACY_OTC_BASIC_URL = "https://mopsfin.twse.com.tw/opendata/t187ap03_O.csv"
    LEGACY_LISTED_REVENUE_URL = "https://mopsfin.twse.com.tw/opendata/t187ap05_L.csv"
    LEGACY_OTC_REVENUE_URL = "https://mopsfin.twse.com.tw/opendata/t187ap05_O.csv"

    def __init__(self, config: OfficialHybridConfig):
        self.config = config
        self.cache_dir = Path(config.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        if config.ssl_insecure_fallback_enabled:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self._mock_client = FinMindClient(FinMindConfig(use_mock_data=True))
        self._finmind_cache_client = None
        if config.use_finmind_financials_cache:
            self._finmind_cache_client = FinMindClient(
                FinMindConfig(
                    token=config.finmind_token,
                    cache_dir=config.finmind_cache_dir,
                    use_mock_data=False,
                    allow_batch_all_stocks=False,
                )
            )

    @staticmethod
    def _daterange(start: date, end: date) -> Iterable[date]:
        cursor = start
        while cursor <= end:
            yield cursor
            cursor += timedelta(days=1)

    @staticmethod
    def _month_starts(start: date, end: date) -> list[date]:
        cursor = date(start.year, start.month, 1)
        end_marker = date(end.year, end.month, 1)
        values: list[date] = []
        while cursor <= end_marker:
            values.append(cursor)
            if cursor.month == 12:
                cursor = date(cursor.year + 1, 1, 1)
            else:
                cursor = date(cursor.year, cursor.month + 1, 1)
        return values

    @staticmethod
    def _normalize_string(value: object) -> str:
        return str(value or "").strip()

    @staticmethod
    def _clean_numeric(value: object) -> float | None:
        if value is None:
            return None
        text = str(value).strip().replace(",", "")
        if text in {"", "--", "---", "N/A", "nan", "None"}:
            return None
        text = text.replace("X", "").replace("*", "")
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _roc_date(value: date) -> str:
        return f"{value.year - 1911:03d}/{value.month:02d}/{value.day:02d}"


    @staticmethod
    def _normalize_listing_date(value: object) -> str:
        text = str(value or "").strip().replace("\u3000", "")
        if text == "" or text.lower() in {"nan", "none", "nat"}:
            return ""

        normalized = text.replace("年", "/").replace("月", "/").replace("日", "")
        parts = [part for part in re.split(r"[^0-9]+", normalized) if part]
        candidates: list[str] = []

        if len(parts) >= 3:
            year_raw, month_raw, day_raw = parts[:3]
            try:
                year = int(year_raw) + 1911 if len(year_raw) <= 3 else int(year_raw)
                month = int(month_raw)
                day = int(day_raw)
                candidates.append(f"{year:04d}-{month:02d}-{day:02d}")
            except ValueError:
                pass

        digits = "".join(parts) if parts else re.sub(r"\D", "", normalized)
        if len(digits) == 8:
            candidates.append(f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}")
        elif len(digits) == 7:
            year = int(digits[:3]) + 1911
            candidates.append(f"{year:04d}-{digits[3:5]}-{digits[5:7]}")
        elif len(digits) == 6:
            year = int(digits[:2]) + 1911
            candidates.append(f"{year:04d}-{digits[2:4]}-{digits[4:6]}")

        for candidate in candidates:
            parsed = pd.to_datetime(candidate, errors="coerce")
            if not pd.isna(parsed):
                return pd.Timestamp(parsed).date().isoformat()
        return ""

    def _cache_path(self, namespace: str, key_parts: list[str], suffix: str = ".json") -> Path:
        payload = "|".join([namespace] + key_parts)
        digest = md5(payload.encode("utf-8")).hexdigest()
        return self.cache_dir / namespace / f"{digest}{suffix}"

    def _read_frame_cache(self, namespace: str, key_parts: list[str]) -> pd.DataFrame | None:
        path = self._cache_path(namespace, key_parts)
        if path.exists():
            return pd.read_json(path)
        return None

    def _write_frame_cache(self, namespace: str, key_parts: list[str], frame: pd.DataFrame) -> None:
        path = self._cache_path(namespace, key_parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_json(path, orient="records", force_ascii=False)

    def _read_text_cache(self, namespace: str, key_parts: list[str]) -> str | None:
        path = self._cache_path(namespace, key_parts, suffix=".txt")
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def _write_text_cache(self, namespace: str, key_parts: list[str], text: str) -> None:
        path = self._cache_path(namespace, key_parts, suffix=".txt")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _host_allows_insecure_retry(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return any(host == allowed or host.endswith(f".{allowed}") for allowed in self.config.ssl_insecure_fallback_hosts)

    def _session_get(self, url: str, *, params: dict[str, str] | None = None) -> requests.Response:
        try:
            response = self.session.get(url, params=params, timeout=self.config.timeout)
            response.raise_for_status()
            return response
        except requests.exceptions.SSLError:
            if not self.config.ssl_insecure_fallback_enabled or not self._host_allows_insecure_retry(url):
                raise
            response = self.session.get(url, params=params, timeout=self.config.timeout, verify=False)
            response.raise_for_status()
            return response

    def _request_text(
        self,
        namespace: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        encoding: str | None = None,
    ) -> str:
        key_parts = [url, json.dumps(params or {}, sort_keys=True, ensure_ascii=False), encoding or "response.encoding"]
        cached = self._read_text_cache(namespace, key_parts)
        if cached is not None:
            return cached
        response = self._session_get(url, params=params)
        if encoding:
            text = response.content.decode(encoding, errors="replace")
        else:
            text = response.text
        self._write_text_cache(namespace, key_parts, text)
        return text

    def _request_csv_frame(
        self,
        namespace: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        encoding: str | None = None,
    ) -> pd.DataFrame:
        key_parts = [url, json.dumps(params or {}, sort_keys=True, ensure_ascii=False), encoding or "utf-8"]
        cached = self._read_frame_cache(namespace, key_parts)
        if cached is not None:
            return cached
        response = self._session_get(url, params=params)
        content = response.content
        chosen_encoding = encoding or response.encoding or "utf-8-sig"
        text = content.decode(chosen_encoding, errors="replace")
        frame = pd.read_csv(io.StringIO(text))
        self._write_frame_cache(namespace, key_parts, frame)
        return frame

    @staticmethod
    def _parse_flexible_csv_text(
        text: str,
        *,
        header_keywords: list[str],
        minimum_columns: int = 2,
    ) -> pd.DataFrame:
        """Parse TPEx-style CSV that may include preamble/footer rows."""

        rows = list(csv.reader(io.StringIO(text)))
        cleaned_rows: list[list[str]] = []
        for row in rows:
            normalized = [str(cell).replace("\ufeff", "").strip() for cell in row]
            if not any(normalized):
                continue
            cleaned_rows.append(normalized)

        if not cleaned_rows:
            return pd.DataFrame()

        normalized_keywords = [keyword.strip().lower() for keyword in header_keywords]
        header_index: int | None = None
        for index, row in enumerate(cleaned_rows):
            joined = " ".join(row).lower()
            if len(row) >= minimum_columns and all(keyword in joined for keyword in normalized_keywords):
                header_index = index
                break

        if header_index is None:
            return pd.DataFrame()

        header = cleaned_rows[header_index]
        data_rows: list[list[str]] = []
        for row in cleaned_rows[header_index + 1 :]:
            first_cell = row[0].strip() if row else ""
            if len(row) == 1 and (
                first_cell.startswith("共")
                or first_cell.startswith("註")
                or first_cell.startswith("說明")
                or first_cell.startswith("資料日期")
            ):
                break
            if len(row) != len(header):
                continue
            if row == header:
                continue
            data_rows.append(row)

        return pd.DataFrame(data_rows, columns=header)

    def _request_json_payload(
        self,
        namespace: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
    ) -> object:
        key_parts = [url, json.dumps(params or {}, sort_keys=True, ensure_ascii=False), "json_payload"]
        cached = self._read_text_cache(namespace, key_parts)
        if cached is None:
            response = self._session_get(url, params=params)
            cached = response.text
            self._write_text_cache(namespace, key_parts, cached)
        return json.loads(cached)

    def _request_json_frame(
        self,
        namespace: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
    ) -> pd.DataFrame:
        key_parts = [url, json.dumps(params or {}, sort_keys=True, ensure_ascii=False), "json"]
        cached = self._read_frame_cache(namespace, key_parts)
        if cached is not None:
            return cached
        payload = self._request_json_payload(namespace + "__payload", url, params=params)
        frame = pd.DataFrame(payload if isinstance(payload, list) else [])
        self._write_frame_cache(namespace, key_parts, frame)
        return frame

    @staticmethod
    def _flatten_columns(frame: pd.DataFrame) -> pd.DataFrame:
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = [
                " ".join([str(level).strip() for level in col if str(level).strip() and not str(level).startswith("Unnamed")]).strip()
                for col in frame.columns
            ]
        else:
            frame.columns = [str(col).strip() for col in frame.columns]
        return frame

    @staticmethod
    def _pick_column(frame: pd.DataFrame, keywords: list[str]) -> str | None:
        normalized = {str(col).lower().replace("_", " "): col for col in frame.columns}
        for keyword in keywords:
            needle = keyword.lower().replace("_", " ")
            for norm_name, original in normalized.items():
                if needle == norm_name or needle in norm_name:
                    return original
        return None

    @staticmethod
    def _extract_twse_json_table(payload: object, required_keywords: list[str]) -> pd.DataFrame:
        if not isinstance(payload, dict):
            return pd.DataFrame()

        required = [keyword.lower() for keyword in required_keywords]
        table_keys = sorted(
            key for key in payload.keys() if isinstance(key, str) and key.startswith("fields")
        )
        for fields_key in table_keys:
            suffix = fields_key[len("fields") :]
            data_key = f"data{suffix}"
            fields = payload.get(fields_key)
            data = payload.get(data_key)
            if not isinstance(fields, list) or not isinstance(data, list):
                continue
            joined = " ".join(str(field) for field in fields).lower()
            if not all(keyword in joined for keyword in required):
                continue
            return pd.DataFrame(data, columns=[str(field).strip() for field in fields])

        tables = payload.get("tables")
        if isinstance(tables, list):
            for table in tables:
                if not isinstance(table, dict):
                    continue
                fields = table.get("fields")
                data = table.get("data")
                if not isinstance(fields, list) or not isinstance(data, list):
                    continue
                joined = " ".join(str(field) for field in fields).lower()
                if not all(keyword in joined for keyword in required):
                    continue
                return pd.DataFrame(data, columns=[str(field).strip() for field in fields])

        return pd.DataFrame()

    @staticmethod
    def _find_code_column(frame: pd.DataFrame) -> str | None:
        return OfficialHybridClient._pick_column(frame, ["證券代號", "股票代號", "security code", "code", "公司代號", "company code", "代號"])

    @staticmethod
    def _standardize_stock_id(frame: pd.DataFrame) -> pd.DataFrame:
        code_col = OfficialHybridClient._find_code_column(frame)
        if code_col is None:
            return frame
        frame = frame.copy()
        frame["stock_id"] = frame[code_col].astype(str).str.strip().str.replace(r"^=\"|\"$", "", regex=True)
        frame["stock_id"] = frame["stock_id"].str.replace("'", "", regex=False)
        return frame

    @staticmethod
    def _coerce_date(frame: pd.DataFrame, raw_value: date) -> pd.DataFrame:
        frame = frame.copy()
        frame["date"] = raw_value.isoformat()
        return frame

    def _normalize_basic_frame(self, frame: pd.DataFrame, market_type: str) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=["stock_id", "stock_name", "industry_category", "type", "date"])
        frame = frame.copy()
        frame = self._standardize_stock_id(frame)
        name_col = self._pick_column(frame, ["公司名稱", "company name", "股票名稱", "security name"])
        industry_col = self._pick_column(frame, ["產業別", "industry"])
        list_date_col = self._pick_column(frame, ["上市日期", "上櫃日期", "listing date"])
        out = pd.DataFrame(
            {
                "stock_id": frame.get("stock_id", pd.Series(dtype=str)).astype(str),
                "stock_name": frame.get(name_col, pd.Series(dtype=str)).astype(str) if name_col else "",
                "industry_category": frame.get(industry_col, pd.Series(dtype=str)).astype(str) if industry_col else "",
                "type": market_type,
                "date": frame.get(list_date_col, pd.Series(dtype=str)).map(self._normalize_listing_date) if list_date_col else "",
            }
        )
        return out[out["stock_id"].astype(str).str.len() > 0].copy()

    def _load_basic_info(self) -> pd.DataFrame:
        try:
            listed = self._request_json_frame("official_basic_listed_json", self.LISTED_BASIC_URL)
        except Exception:
            listed = self._request_csv_frame("official_basic_listed_csv", self.LEGACY_LISTED_BASIC_URL, encoding="utf-8-sig")

        otc = self._request_csv_frame("official_basic_otc_csv", self.LEGACY_OTC_BASIC_URL, encoding="utf-8-sig")
        frames = [self._normalize_basic_frame(listed, "twse"), self._normalize_basic_frame(otc, "tpex")]
        merged = pd.concat(frames, ignore_index=True)
        merged = merged.drop_duplicates(subset=["stock_id"], keep="last")
        return merged

    def _fetch_twse_price_day(self, trade_date: date) -> pd.DataFrame:
        try:
            payload = self._request_json_payload(
                "official_twse_price_json_payload",
                self.TWSE_MI_INDEX_URL,
                params={
                    "date": trade_date.strftime("%Y%m%d"),
                    "response": "json",
                    "type": "ALLBUT0999",
                },
            )
        except Exception:
            return pd.DataFrame(columns=["stock_id", "date", "close", "Trading_Volume", "Trading_money"])

        frame = self._extract_twse_json_table(payload, ["證券代號", "收盤價"])
        if frame.empty:
            frame = self._extract_twse_json_table(payload, ["Security Code", "Closing Price"])
        if frame.empty:
            return pd.DataFrame(columns=["stock_id", "date", "close", "Trading_Volume", "Trading_money"])
        frame = self._standardize_stock_id(frame)
        close_col = self._pick_column(frame, ["closing price", "收盤價"])
        volume_col = self._pick_column(frame, ["trade volume", "成交股數", "trading volume"])
        value_col = self._pick_column(frame, ["trade value", "成交金額", "trading value"])
        open_col = self._pick_column(frame, ["opening price", "開盤價"])
        high_col = self._pick_column(frame, ["highest price", "最高價"])
        low_col = self._pick_column(frame, ["lowest price", "最低價"])
        tx_col = self._pick_column(frame, ["transaction", "成交筆數"])
        name_col = self._pick_column(frame, ["security name", "證券名稱"])

        out = pd.DataFrame({
            "stock_id": frame["stock_id"],
            "stock_name": frame.get(name_col, pd.Series(index=frame.index, dtype=str)).astype(str) if name_col else "",
            "date": trade_date.isoformat(),
            "close": frame.get(close_col).map(self._clean_numeric) if close_col else None,
            "Trading_Volume": frame.get(volume_col).map(self._clean_numeric) if volume_col else None,
            "Trading_money": frame.get(value_col).map(self._clean_numeric) if value_col else None,
            "open": frame.get(open_col).map(self._clean_numeric) if open_col else None,
            "max": frame.get(high_col).map(self._clean_numeric) if high_col else None,
            "min": frame.get(low_col).map(self._clean_numeric) if low_col else None,
            "Trading_turnover": frame.get(tx_col).map(self._clean_numeric) if tx_col else None,
            "market_type": "twse",
        })
        return out[out["stock_id"].str.len() > 0].copy()

    def _fetch_tpex_price_day(self, trade_date: date) -> pd.DataFrame:
        text = self._request_text(
            "official_tpex_price_text",
            self.TPEX_PRICE_URL,
            params={
                "l": "zh-tw",
                "o": "csv",
                "se": "EW",
                "d": self._roc_date(trade_date),
            },
            encoding="big5",
        )
        frame = self._parse_flexible_csv_text(text, header_keywords=["代號", "名稱", "收盤"], minimum_columns=8)
        if frame.empty:
            return pd.DataFrame(columns=["stock_id", "date", "close", "Trading_Volume", "Trading_money"])
        frame = self._standardize_stock_id(frame)
        close_col = self._pick_column(frame, ["收盤", "close"])
        volume_col = self._pick_column(frame, ["成交股數", "volume", "成交仟股"])
        value_col = self._pick_column(frame, ["成交金額", "trading value"])
        open_col = self._pick_column(frame, ["開盤", "opening price"])
        high_col = self._pick_column(frame, ["最高", "highest price"])
        low_col = self._pick_column(frame, ["最低", "lowest price"])
        tx_col = self._pick_column(frame, ["成交筆數", "transaction"])
        name_col = self._pick_column(frame, ["名稱", "company name", "security name"])
        out = pd.DataFrame({
            "stock_id": frame["stock_id"],
            "stock_name": frame.get(name_col, pd.Series(index=frame.index, dtype=str)).astype(str) if name_col else "",
            "date": trade_date.isoformat(),
            "close": frame.get(close_col).map(self._clean_numeric) if close_col else None,
            "Trading_Volume": frame.get(volume_col).map(self._clean_numeric) if volume_col else None,
            "Trading_money": frame.get(value_col).map(self._clean_numeric) if value_col else None,
            "open": frame.get(open_col).map(self._clean_numeric) if open_col else None,
            "max": frame.get(high_col).map(self._clean_numeric) if high_col else None,
            "min": frame.get(low_col).map(self._clean_numeric) if low_col else None,
            "Trading_turnover": frame.get(tx_col).map(self._clean_numeric) if tx_col else None,
            "market_type": "tpex",
        })
        return out[out["stock_id"].str.len() > 0].copy()

    def _fetch_twse_institutional_day(self, trade_date: date) -> pd.DataFrame:
        try:
            payload = self._request_json_payload(
                "official_twse_t86_json_payload",
                self.TWSE_T86_URL,
                params={
                    "date": trade_date.strftime("%Y%m%d"),
                    "response": "json",
                    "selectType": "ALLBUT0999",
                },
            )
        except Exception:
            return pd.DataFrame(columns=["date", "stock_id", "buy", "sell", "name"])

        frame = self._extract_twse_json_table(payload, ["證券代號", "外陸資買進股數"])
        if frame.empty:
            frame = self._extract_twse_json_table(payload, ["Security Code", "Difference"])
        if frame.empty:
            return pd.DataFrame(columns=["date", "stock_id", "buy", "sell", "name"])
        frame = self._standardize_stock_id(frame)
        foreign_buy_col = self._pick_column(frame, ["Foreign Investors include Mainland Area Investors (Foreign Dealers excluded) Total Buy", "外資及陸資(不含外資自營商)買進股數", "外陸資買進股數(不含外資自營商)"])
        foreign_sell_col = self._pick_column(frame, ["Foreign Investors include Mainland Area Investors (Foreign Dealers excluded) Total Sell", "外資及陸資(不含外資自營商)賣出股數", "外陸資賣出股數(不含外資自營商)"])
        trust_buy_col = self._pick_column(frame, ["Securities Investment Trust Companies Total Buy", "投信買進股數"])
        trust_sell_col = self._pick_column(frame, ["Securities Investment Trust Companies Total Sell", "投信賣出股數"])
        dealer_buy_col = self._pick_column(frame, ["Dealers (Proprietary) Total Buy", "自營商(自行買賣)買進股數", "自營商買進股數(自行買賣)"])
        dealer_sell_col = self._pick_column(frame, ["Dealers (Proprietary) Total Sell", "自營商(自行買賣)賣出股數", "自營商賣出股數(自行買賣)"])
        dealer_hedge_buy_col = self._pick_column(frame, ["Dealers (Hedge) Total Buy", "自營商(避險)買進股數", "自營商買進股數(避險)"])
        dealer_hedge_sell_col = self._pick_column(frame, ["Dealers (Hedge) Total Sell", "自營商(避險)賣出股數", "自營商賣出股數(避險)"])

        rows: list[dict[str, object]] = []
        for _, row in frame.iterrows():
            stock_id = str(row.get("stock_id", "")).strip()
            if not stock_id:
                continue
            foreign_buy = self._clean_numeric(row.get(foreign_buy_col)) or 0.0
            foreign_sell = self._clean_numeric(row.get(foreign_sell_col)) or 0.0
            trust_buy = self._clean_numeric(row.get(trust_buy_col)) or 0.0
            trust_sell = self._clean_numeric(row.get(trust_sell_col)) or 0.0
            dealer_buy = (self._clean_numeric(row.get(dealer_buy_col)) or 0.0) + (self._clean_numeric(row.get(dealer_hedge_buy_col)) or 0.0)
            dealer_sell = (self._clean_numeric(row.get(dealer_sell_col)) or 0.0) + (self._clean_numeric(row.get(dealer_hedge_sell_col)) or 0.0)
            rows.extend([
                {"date": trade_date.isoformat(), "stock_id": stock_id, "buy": foreign_buy, "sell": foreign_sell, "name": "Foreign_Investor"},
                {"date": trade_date.isoformat(), "stock_id": stock_id, "buy": trust_buy, "sell": trust_sell, "name": "Investment_Trust"},
                {"date": trade_date.isoformat(), "stock_id": stock_id, "buy": dealer_buy, "sell": dealer_sell, "name": "Dealer_Hedging"},
            ])
        return pd.DataFrame(rows)

    def _fetch_tpex_institutional_day(self, trade_date: date) -> pd.DataFrame:
        text = self._request_text(
            "official_tpex_3inst_text",
            self.TPEX_INST_URL,
            params={
                "l": "zh-tw",
                "o": "csv",
                "se": "EW",
                "t": "D",
                "d": self._roc_date(trade_date),
            },
            encoding="big5",
        )
        frame = self._parse_flexible_csv_text(text, header_keywords=["代號", "名稱", "外資"], minimum_columns=7)
        if frame.empty:
            return pd.DataFrame(columns=["date", "stock_id", "buy", "sell", "name"])
        frame = self._standardize_stock_id(frame)
        foreign_buy_col = self._pick_column(frame, ["外資及陸資(不含外資自營商)-買進股數", "foreign buy"])
        foreign_sell_col = self._pick_column(frame, ["外資及陸資(不含外資自營商)-賣出股數", "foreign sell"])
        trust_buy_col = self._pick_column(frame, ["投信-買進股數", "investment trust buy"])
        trust_sell_col = self._pick_column(frame, ["投信-賣出股數", "investment trust sell"])
        dealer_buy_col = self._pick_column(frame, ["自營商-買進股數", "dealer buy"])
        dealer_sell_col = self._pick_column(frame, ["自營商-賣出股數", "dealer sell"])
        dealer_self_buy_col = self._pick_column(frame, ["自營商(自行買賣)-買進股數"])
        dealer_self_sell_col = self._pick_column(frame, ["自營商(自行買賣)-賣出股數"])
        dealer_hedge_buy_col = self._pick_column(frame, ["自營商(避險)-買進股數"])
        dealer_hedge_sell_col = self._pick_column(frame, ["自營商(避險)-賣出股數"])
        rows: list[dict[str, object]] = []
        for _, row in frame.iterrows():
            stock_id = str(row.get("stock_id", "")).strip()
            if not stock_id:
                continue
            foreign_buy = self._clean_numeric(row.get(foreign_buy_col)) or 0.0
            foreign_sell = self._clean_numeric(row.get(foreign_sell_col)) or 0.0
            trust_buy = self._clean_numeric(row.get(trust_buy_col)) or 0.0
            trust_sell = self._clean_numeric(row.get(trust_sell_col)) or 0.0
            if dealer_buy_col and dealer_sell_col:
                dealer_buy = self._clean_numeric(row.get(dealer_buy_col)) or 0.0
                dealer_sell = self._clean_numeric(row.get(dealer_sell_col)) or 0.0
            else:
                dealer_buy = (self._clean_numeric(row.get(dealer_self_buy_col)) or 0.0) + (self._clean_numeric(row.get(dealer_hedge_buy_col)) or 0.0)
                dealer_sell = (self._clean_numeric(row.get(dealer_self_sell_col)) or 0.0) + (self._clean_numeric(row.get(dealer_hedge_sell_col)) or 0.0)
            rows.extend([
                {"date": trade_date.isoformat(), "stock_id": stock_id, "buy": foreign_buy, "sell": foreign_sell, "name": "Foreign_Investor"},
                {"date": trade_date.isoformat(), "stock_id": stock_id, "buy": trust_buy, "sell": trust_sell, "name": "Investment_Trust"},
                {"date": trade_date.isoformat(), "stock_id": stock_id, "buy": dealer_buy, "sell": dealer_sell, "name": "Dealer_Hedging"},
            ])
        return pd.DataFrame(rows)

    @staticmethod
    def _parse_year_month_columns(frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame.copy()
        year_col = OfficialHybridClient._pick_column(frame, ["年度", "year"])
        month_col = OfficialHybridClient._pick_column(frame, ["月份", "month"])
        if year_col and month_col:
            frame["year"] = pd.to_numeric(frame[year_col], errors="coerce")
            frame["month"] = pd.to_numeric(frame[month_col], errors="coerce")
            return frame

        ym_col = OfficialHybridClient._pick_column(frame, ["資料年月", "年月", "yearmonth", "year month"])
        if ym_col is None:
            frame["year"] = pd.NA
            frame["month"] = pd.NA
            return frame

        digits = frame[ym_col].astype(str).str.replace(r"\D", "", regex=True)
        year_values = []
        month_values = []
        for raw in digits:
            raw = raw or ""
            year = None
            month = None
            if len(raw) == 5 and raw.isdigit():
                year = int(raw[:3]) + 1911
                month = int(raw[3:])
            elif len(raw) >= 6 and raw[:6].isdigit():
                year = int(raw[:4])
                month = int(raw[4:6])
            year_values.append(year)
            month_values.append(month)

        frame["year"] = pd.to_numeric(pd.Series(year_values, index=frame.index), errors="coerce")
        frame["month"] = pd.to_numeric(pd.Series(month_values, index=frame.index), errors="coerce")
        return frame

    def _load_month_revenue_table(self) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        try:
            listed = self._request_json_frame("official_revenue_listed_json", self.LISTED_REVENUE_URL)
            frames.append(listed)
        except Exception:
            listed = self._request_csv_frame("official_revenue_listed_csv", self.LEGACY_LISTED_REVENUE_URL, encoding="utf-8-sig")
            frames.append(listed)

        try:
            otc = self._request_csv_frame("official_revenue_otc_csv", self.LEGACY_OTC_REVENUE_URL, encoding="utf-8-sig")
            frames.append(otc)
        except Exception:
            pass

        merged = pd.concat([frame for frame in frames if not frame.empty], ignore_index=True)
        if merged.empty:
            return pd.DataFrame(columns=["stock_id", "date", "revenue"])
        merged = self._standardize_stock_id(merged)
        merged = self._parse_year_month_columns(merged)
        revenue_col = self._pick_column(merged, ["營業收入-當月營收", "當月營收", "revenue"])
        if revenue_col is None:
            return pd.DataFrame(columns=["stock_id", "date", "revenue"])
        merged["date"] = pd.to_datetime({"year": merged["year"], "month": merged["month"], "day": 1}, errors="coerce")
        merged["revenue"] = merged[revenue_col].map(self._clean_numeric)
        out = merged[["stock_id", "date", "revenue"]].dropna(subset=["stock_id", "date", "revenue"]).copy()
        out["date"] = out["date"].dt.strftime("%Y-%m-%d")
        return out

    def get_stock_info(self) -> pd.DataFrame:
        if self.config.use_mock_data:
            return self._mock_client.get_stock_info()
        return self._load_basic_info()

    def get_trading_dates(self, start_date: date, end_date: date) -> pd.DataFrame:
        if self.config.use_mock_data:
            return self._mock_client.get_trading_dates(start_date, end_date)
        # Lightweight approximation: probe backward snapshots; cache prevents repeated calls.
        days: list[str] = []
        for day in self._daterange(start_date, end_date):
            try:
                snapshot = self.get_price_snapshot(day)
            except Exception:
                continue
            if not snapshot.empty:
                days.append(day.isoformat())
        return pd.DataFrame({"date": days})

    def get_latest_trading_date(self, as_of_date: date, lookback_days: int = 14) -> date:
        if self.config.use_mock_data:
            return self._mock_client.get_latest_trading_date(as_of_date, lookback_days)
        for offset in range(lookback_days + 1):
            candidate = as_of_date - timedelta(days=offset)
            try:
                snapshot = self.get_price_snapshot(candidate)
            except Exception:
                continue
            if not snapshot.empty:
                return candidate
        return as_of_date

    def get_price_snapshot(self, trade_date: date) -> pd.DataFrame:
        if self.config.use_mock_data:
            return self._mock_client.get_price_snapshot(trade_date)
        key_parts = [trade_date.isoformat()]
        cached = self._read_frame_cache("official_price_snapshot", key_parts)
        if cached is not None:
            return cached
        frames = [self._fetch_twse_price_day(trade_date), self._fetch_tpex_price_day(trade_date)]
        non_empty_frames = [frame for frame in frames if frame is not None and not frame.empty]
        if non_empty_frames:
            merged = pd.concat(non_empty_frames, ignore_index=True)
        else:
            merged = pd.DataFrame(
                columns=[
                    "stock_id",
                    "stock_name",
                    "date",
                    "close",
                    "Trading_Volume",
                    "Trading_money",
                    "open",
                    "max",
                    "min",
                    "Trading_turnover",
                    "market_type",
                ]
            )
        self._write_frame_cache("official_price_snapshot", key_parts, merged)
        return merged

    def get_price_history(self, stock_ids: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        if self.config.use_mock_data:
            return self._mock_client.get_price_history(stock_ids, start_date, end_date)
        frames: list[pd.DataFrame] = []
        wanted = {str(stock_id) for stock_id in stock_ids}
        for day in self._daterange(start_date, end_date):
            snapshot = self.get_price_snapshot(day)
            if snapshot.empty:
                continue
            if wanted:
                snapshot = snapshot[snapshot["stock_id"].astype(str).isin(wanted)].copy()
            if not snapshot.empty:
                frames.append(snapshot)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def get_institutional_buy_sell(self, stock_ids: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        if self.config.use_mock_data:
            return self._mock_client.get_institutional_buy_sell(stock_ids, start_date, end_date)
        frames: list[pd.DataFrame] = []
        wanted = {str(stock_id) for stock_id in stock_ids}
        for day in self._daterange(start_date, end_date):
            cache_key = [day.isoformat()]
            cached = self._read_frame_cache("official_inst_snapshot", cache_key)
            if cached is not None:
                snapshot = cached
            else:
                daily_frames = [self._fetch_twse_institutional_day(day), self._fetch_tpex_institutional_day(day)]
                non_empty_daily_frames = [frame for frame in daily_frames if frame is not None and not frame.empty]
                if non_empty_daily_frames:
                    snapshot = pd.concat(non_empty_daily_frames, ignore_index=True)
                else:
                    snapshot = pd.DataFrame(
                        columns=["date", "stock_id", "buy", "sell", "name", "market_type"]
                    )
                self._write_frame_cache("official_inst_snapshot", cache_key, snapshot)
            if snapshot.empty:
                continue
            if wanted:
                snapshot = snapshot[snapshot["stock_id"].astype(str).isin(wanted)].copy()
            if not snapshot.empty:
                frames.append(snapshot)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def get_month_revenue(self, stock_ids: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        if self.config.use_mock_data:
            return self._mock_client.get_month_revenue(stock_ids, start_date, end_date)
        frame = self._load_month_revenue_table()
        if frame.empty:
            return frame
        frame = frame.copy()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame[(frame["date"].dt.date >= start_date) & (frame["date"].dt.date <= end_date)]
        if stock_ids:
            frame = frame[frame["stock_id"].astype(str).isin({str(stock_id) for stock_id in stock_ids})].copy()
        frame["date"] = frame["date"].dt.strftime("%Y-%m-%d")
        return frame

    def get_financial_statements(self, stock_ids: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        if self.config.use_mock_data:
            return self._mock_client.get_financial_statements(stock_ids, start_date, end_date)
        if self._finmind_cache_client is None:
            return pd.DataFrame()
        return self._finmind_cache_client.get_cached_financial_statements(stock_ids, start_date, end_date)
