# Orbis Quant Agents/compliance_retention.py

import os
import json
import shutil
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from orbisquantagents.compliance import compute_log_checksum


def verify_audit_trail_integrity(audit_trail_path: str) -> tuple[bool, str]:
    """
    Verify the cryptographic integrity of a JSONL audit trail file.
    Recalculates SHA-256 hashes and verifies the linkage between successive entries.
    """
    path = Path(audit_trail_path)
    if not path.exists():
        return False, f"Audit trail file does not exist: {audit_trail_path}"

    expected_prev_checksum = "0" * 64
    line_number = 0

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line_number += 1
                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    return False, f"Line {line_number} is not valid JSON."

                # Verify previous checksum link
                prev_checksum = record.get("previous_checksum")
                if prev_checksum != expected_prev_checksum:
                    return False, (
                        f"Integrity broken at line {line_number}. "
                        f"Expected previous_checksum '{expected_prev_checksum}', "
                        f"but found '{prev_checksum}'."
                    )

                # Verify current entry checksum
                stored_checksum = record.get("checksum")
                if not stored_checksum:
                    return False, f"Missing checksum field at line {line_number}."

                computed_checksum = compute_log_checksum(record)
                if stored_checksum != computed_checksum:
                    return False, (
                        f"Tampering detected at line {line_number}. "
                        f"Stored checksum: '{stored_checksum}', "
                        f"Computed checksum: '{computed_checksum}'."
                    )

                # Update expected checksum for next iteration
                expected_prev_checksum = stored_checksum

        return True, f"Integrity verified successfully for {line_number} records."

    except Exception as e:
        return False, f"Verification failed with error: {str(e)}"


def archive_old_logs(results_dir: str, archive_dir: str = None, retention_years: int = 5) -> list[str]:
    """
    Finds log files older than the specified retention period, compresses them, and moves them to archives.
    SEBI mandates retaining records for a minimum of 5 years.
    """
    results_path = Path(results_dir)
    if not results_path.exists():
        return []

    if archive_dir is None:
        archive_path = results_path / "compliance_archive"
    else:
        archive_path = Path(archive_dir)

    archive_path.mkdir(parents=True, exist_ok=True)
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_years * 365)

    archived_files = []

    # Traverse directories to search for logs (full_states_log_*.json, audit_trail.jsonl, message_tool.log)
    for root, dirs, files in os.walk(results_path):
        # Skip the archive directory itself
        if Path(root).resolve() == archive_path.resolve() or archive_path.resolve() in Path(root).resolve().parents:
            continue

        for file in files:
            if not (file.endswith(".json") or file.endswith(".jsonl") or file.endswith(".log")):
                continue

            file_path = Path(root) / file
            file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)

            # Archive if older than retention limit
            if file_mtime < cutoff_date:
                # Group by year for archiving
                archive_zip_name = f"compliance_archive_{file_mtime.year}.zip"
                zip_path = archive_path / archive_zip_name

                # Add to zip
                with zipfile.ZipFile(zip_path, "a", zipfile.ZIP_DEFLATED) as zip_file:
                    arcname = file_path.relative_to(results_path)
                    zip_file.write(file_path, arcname=arcname)

                # Delete the original file after archiving
                file_path.unlink()
                archived_files.append(str(file_path))

    return archived_files


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SEBI Compliance Log Retention & Verification Utility")
    parser.add_argument("--verify", type=str, help="Path to audit_trail.jsonl to verify integrity")
    parser.add_argument("--results-dir", type=str, default="./results", help="Path to results directory")
    parser.add_argument("--archive-dir", type=str, help="Custom path for archiving logs")
    parser.add_argument("--archive", action="store_true", help="Perform archival of logs older than 5 years")

    args = parser.parse_args()

    if args.verify:
        success, msg = verify_audit_trail_integrity(args.verify)
        print(f"[{'SUCCESS' if success else 'FAILURE'}] {msg}")
    elif args.archive:
        print(f"Scanning for logs older than 5 years in {args.results_dir}...")
        archived = archive_old_logs(args.results_dir, args.archive_dir)
        if archived:
            print(f"Archived {len(archived)} files:")
            for f in archived:
                print(f" - {f}")
        else:
            print("No logs older than 5 years found. Nothing to archive.")
    else:
        # Default behavior: verify all audit trails found under results-dir
        results_path = Path(args.results_dir)
        audit_trails = list(results_path.glob("**/audit_trail.jsonl"))
        if not audit_trails:
            print(f"No audit trail files found under {args.results_dir}")
        else:
            print(f"Found {len(audit_trails)} audit trail files. Verifying...")
            for trail in audit_trails:
                success, msg = verify_audit_trail_integrity(str(trail))
                print(f" - {trail.relative_to(results_path)}: [{'VALID' if success else 'INVALID'}] {msg}")
