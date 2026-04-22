# Qlib Setup Guide — Taiwan Market

## Prerequisites

- Python 3.11
- `gcc`, `g++`, `cython3` (needed to build Qlib's C extensions)

## 1. Install Dependencies

```bash
pip install -r requirements.txt
# pyqlib>=0.9.5 is included; it will compile C extensions on first install
```

If pip build fails, install the build tools first:

```bash
# Debian/Ubuntu
sudo apt-get install -y gcc g++ cython3 libgomp1
```

## 2. Run the Data Sync

Collect the last 5 trading days (fast smoke test):

```bash
python -m app.orchestration.sync_qlib_data --lookback-days 5
```

Collect a full year of history (takes several minutes with mock data off):

```bash
python -m app.orchestration.sync_qlib_data --lookback-days 365
```

Or via Docker:

```bash
bash scripts/linux/run_qlib_sync.sh --lookback-days 5
```

## 3. Verify the Binary Store

```python
from qlib_ext import init_tw_qlib
import qlib.data as D

init_tw_qlib()  # uses workspace/qlib_data by default
df = D.features(["2330.TW"], ["$close", "$volume"], start_time="2024-01-01", end_time="2024-01-31")
print(df)
# Expected: non-empty DataFrame with (instrument, datetime) MultiIndex
```

## 4. Run Integration Tests

```bash
pytest -q tests/integration/test_qlib_init.py
```

The test is skipped automatically if `workspace/qlib_data/instruments/all.txt` does not exist.

## 5. Backup to pCloud

```bash
python -m app.orchestration.backup_qlib_data
```

Uploads `workspace/qlib_data/` as a zip to `/qlib_data/snapshot={YYYY-MM-DD}/qlib_data.zip` on pCloud. Runs in mock mode if `PCLOUD_TOKEN` is not set.

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `CACHE_DIR` | `workspace/hotdata` | Raw data cache for `OfficialHybridClient` |
| `OUTPUT_DIR` | `workspace` | Parent of `qlib_data/` binary store |
| `USE_MOCK_DATA` | `false` | Set to `true` to use mock data (no network) |
| `PCLOUD_TOKEN` | — | Required for real pCloud backup |
| `PCLOUD_REGION` | `eu` | `eu` or `us` |
