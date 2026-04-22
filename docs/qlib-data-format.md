# Qlib Binary Data Format — Taiwan Market

## Directory Structure

After running `sync_qlib_data`, the binary store lives at `workspace/qlib_data/`:

```
workspace/qlib_data/
  calendars/
    day.txt              # one trading date per line: YYYY-MM-DD
  instruments/
    all.txt              # symbol<TAB>start_date<TAB>end_date
  features/
    {SYMBOL.TW}/
      open.day.bin
      high.day.bin
      low.day.bin
      close.day.bin
      volume.day.bin
      factor.day.bin
      revenue.csv        # financial collector output (not yet binned)
      roe.csv
      gm.csv
```

## Symbol Format

Qlib REG_TW uses `{code}.TW`, for example `2330.TW` (TSMC). This matches the format used by Qlib's built-in Taiwan region configuration.

## Factor Field

`factor = adjusted_close / original_close`. Because the current data source (`OfficialHybridClient`) already returns adjusted prices, `factor` is set to `1.0` for all rows. When a raw price feed with corporate-action data is added in a future phase, this field will encode the actual adjustment ratio.

## Holiday and Trading Halt Handling

Days where a stock did not trade (halt, holiday, or weekend) are absent from the staging CSV. Qlib's `DumpDataAll` fills these gaps with `NaN` in the binary files, which is the correct representation for missing data. Downstream expressions that use `Ref($close, -N)` will propagate `NaN` through halted periods automatically.

## Rebuilding from Scratch

```bash
# 1. Clear existing bin (optional — DumpDataAll merges by default)
rm -rf workspace/qlib_data

# 2. Run the sync job with full history
python -m app.orchestration.sync_qlib_data --lookback-days 365

# 3. Verify
python - <<'EOF'
from qlib_ext import init_tw_qlib
import qlib.data as D
init_tw_qlib()
df = D.features(["2330.TW"], ["$close"], start_time="2024-01-01", end_time="2024-01-31")
print(df)
EOF
```

## Financial Data Forward-Fill Rule

Monthly revenue and quarterly financials (ROE, gross margin) are lower-frequency than daily prices. Each announced value is forward-filled to daily frequency: it applies from the announcement date until the next announcement arrives. This preserves point-in-time correctness — no look-ahead bias is introduced.
