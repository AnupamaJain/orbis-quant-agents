# Orbis Quant Agents/compliance.py

import os
import uuid
import json
import hashlib
import contextvars
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ContextVar to hold current data sources collected during execution.
# Structure: { ticker: [ { method, vendor, arguments, timestamp, source_attribution } ] }
data_sources_var = contextvars.ContextVar("data_sources", default=None)

# Retrieve configuration from env
SEBI_RA_NUMBER = os.getenv("SEBI_RA_NUMBER", "").strip()

# Build standard SEBI disclaimer
if SEBI_RA_NUMBER:
    SEBI_DISCLAIMER = f"""**SEBI REGULATORY DISCLOSURE & DISCLAIMER (Regulation 18 & 24)**
*SEBI Registered Research Analyst Registration No: {SEBI_RA_NUMBER}*
Orbis Quant Agents is an AI-powered financial intelligence platform. All research reports, analysis, and trading recommendations generated are for educational and informational purposes only. Nothing on this platform constitutes investment, legal, or tax advice. Investing in securities is subject to market risks; please consult a SEBI registered investment advisor before making any investment decisions. The developers of Orbis Quant Agents do not guarantee the accuracy, completeness, or timeliness of any data provided. Past performance is not indicative of future results."""
else:
    SEBI_DISCLAIMER = """**SEBI REGULATORY DISCLOSURE & DISCLAIMER (Regulation 18 & 24)**
*STATUS: NON-REGISTERED (Educational & Research Demonstration Platform Only)*
Orbis Quant Agents is an AI-powered financial intelligence platform. All research reports, analysis, and trading recommendations generated are for educational and informational purposes only. Orbis Quant Agents is NOT a SEBI Registered Investment Advisor (RIA) or Research Analyst (RA). Nothing on this platform constitutes investment, legal, or tax advice. Investing in securities is subject to market risks; please consult a SEBI registered investment advisor before making any investment decisions. The developers of Orbis Quant Agents do not guarantee the accuracy, completeness, or timeliness of any data provided. Past performance is not indicative of future results."""


def generate_session_id() -> str:
    """Generate a unique session ID for audit trail tracking."""
    return str(uuid.uuid4())


def get_execution_timestamp() -> str:
    """Get the current timezone-aware timestamp (IST)."""
    utc_now = datetime.now(timezone.utc)
    ist_now = utc_now.astimezone(timezone(timedelta(hours=5, minutes=30)))
    return ist_now.strftime("%Y-%m-%d %H:%M:%S IST")


def record_data_source(method: str, vendor: str, args: tuple, kwargs: dict):
    """Record a data source access event in the active context."""
    sources = data_sources_var.get()
    if sources is None:
        return

    # Extract ticker symbol from arguments
    ticker = "GLOBAL"
    if args:
        ticker = str(args[0]).upper()
    elif "ticker" in kwargs:
        ticker = str(kwargs["ticker"]).upper()
    elif "symbol" in kwargs:
        ticker = str(kwargs["symbol"]).upper()

    # Clean ticker suffix for dictionary keys
    ticker = ticker.split('.')[0] if '.' in ticker else ticker

    timestamp = get_execution_timestamp()

    # Create detailed entry
    entry = {
        "method": method,
        "vendor": vendor,
        "arguments": {
            "args": [str(a) for a in args],
            "kwargs": {k: str(v) for k, v in kwargs.items()}
        },
        "timestamp": timestamp,
        "source_attribution": f"Data retrieved from {vendor} API via endpoint '{method}'."
    }

    if ticker not in sources:
        sources[ticker] = []

    # Check for duplicates
    for existing in sources[ticker]:
        if existing["method"] == method and existing["arguments"] == entry["arguments"]:
            return

    sources[ticker].append(entry)


def compute_log_checksum(log_entry: dict) -> str:
    """Compute deterministic SHA-256 hash of a log entry, excluding the 'checksum' key."""
    clean_entry = {k: v for k, v in log_entry.items() if k != "checksum"}
    serialized = json.dumps(clean_entry, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def append_audit_log(ticker: str, trade_date: str, log_entry: dict, results_dir: str = "./results"):
    """
    Appends a log entry to the audit_trail.jsonl log file.
    Calculates a cryptographic checksum chained to the previous log entry.
    Also preserves logs locally via write-protected (WORM) mirroring and optionally on S3.
    """
    directory = Path(results_dir) / ticker / "OrbisQuantAgentsStrategy_logs"
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / "audit_trail.jsonl"

    previous_checksum = "0" * 64
    # Read the last line to get the previous checksum
    if log_path.exists() and log_path.stat().st_size > 0:
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                if lines:
                    last_line = lines[-1].strip()
                    if last_line:
                        last_entry = json.loads(last_line)
                        previous_checksum = last_entry.get("checksum", "0" * 64)
        except Exception:
            pass

    # Prepare audit log record with chain linkage
    audit_record = log_entry.copy()
    audit_record["previous_checksum"] = previous_checksum
    audit_record["checksum"] = compute_log_checksum(audit_record)

    # 1. Write to standard local log path
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(audit_record) + "\n")

    # 2. Write-protected (WORM) local mirroring
    try:
        backup_dir = Path(results_dir).parent / "compliance_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"{ticker}_audit_trail.jsonl"

        # Temporarily make writable if it exists to append
        if backup_path.exists():
            os.chmod(backup_path, 0o644)

        with open(backup_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_record) + "\n")

        # Set to read-only (owner/group/others can only read)
        os.chmod(backup_path, 0o444)
    except Exception as e:
        print(f"[COMPLIANCE WARNING] Local log preservation failed: {e}")

    # 3. Optional S3 cloud preservation
    s3_bucket = os.getenv("COMPLIANCE_S3_BUCKET", "").strip()
    if s3_bucket:
        try:
            import boto3
            s3_client = boto3.client(
                "s3",
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                region_name=os.getenv("AWS_DEFAULT_REGION", "ap-south-1")
            )
            s3_key = f"compliance_backups/{ticker}_audit_trail.jsonl"
            s3_client.upload_file(str(log_path), s3_bucket, s3_key)
            print(f"[COMPLIANCE] Audit log for {ticker} successfully preserved in cloud bucket '{s3_bucket}'.")
        except ModuleNotFoundError:
            # Silent fallback if boto3 is not installed
            pass
        except Exception as e:
            print(f"[COMPLIANCE ERROR] Cloud log preservation failed: {e}")
