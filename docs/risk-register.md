# Keeping the risk register current

The register in [quality/fmea.json](../quality/fmea.json) records possible failures
in seal placement and review. [The method](../quality/FMEA.md) explains its scoring;
[the generated register](../quality/FMEA_REGISTER.md) is the readable view.

The source is JSON so the existing test and traceability scripts can check it
without maintaining a second spreadsheet. Each failure mode links to requirements,
controls and exact tests. Actions distinguish verified software checks from open
manual checks on drawings. Occurrence scores are estimates, not measured field
frequencies, and passing synthetic tests does not establish production approval.

Run `python quality/fmea_report.py` to validate the source and regenerate the
page. CI uses `--check` to reject invalid scores, missing rationale, broken test
links and a stale page. The quality scripts also tie the installation/software
check record to fingerprints of the files that were tested. See the
[quality guide](../quality/README.md) for the full procedure.
