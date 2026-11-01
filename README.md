# Decode-before-guard UAV telemetry audit

This repository contains executable round-2 audit code, declared configuration, seeds and record-level derived evaluation results for **Decode-Before-Guard Compression for UAV Energy Telemetry**. The latest 15-page manuscript is available at [`paper/UAV_Energy_Conserving_Compression.pdf`](paper/UAV_Energy_Conserving_Compression.pdf). The paper presents a streaming compressor that decodes candidate packets before checking power error, prefix-energy error, nonnegativity and segment duration.

The repository does not redistribute the original datasets or their encoded sample fields. Reproduction requires authorized local inputs under their source terms. No Zenodo DOI is claimed in this repository until a public record has actually been created and verified.

Python 3.13 and the pinned requirements are required. The numerical certification concerns the explicitly prepared piecewise-linear references, not physical sensor calibration, radio-energy savings or unobserved erased interiors. Solar is one descriptive campaign.

## Reproduce

Obtain the original datasets under their source terms, or use an authorized local extraction of the supplied evidence package. This release is not falsely described as a standalone raw-data mirror. Verify the prepared-input SHA-256 values in `configuration/local_input_manifest.json`. The round-2 runner expects the paper-root directory structure documented in `README_REPRODUCTION.md`.

```powershell
python -m pip install -r requirements.txt
python -X utf8 run_public.py --paper-root D:/authorized/local/Paper_02_Sparse_Auditing
```

The single command replays the isolated legacy gate, new codec comparisons, loss simulation, long streams, statistics, tables and figures inside the authorized local paper root. A TeX distribution and Poppler are needed to rebuild the separately retained article. Public result CSVs can be inspected without original inputs. Runtime depends on available CPU/RAM.

## Scope and negative results

See `PROTOCOL.md`, `CHANGELOG_VI.md` and `NOT_COMPLETED_VI.md`. All-attempt costs retain refused encodings. Finite-catalogue iso-guard searches are not global optimization over real tolerances, and the byte oracle applies only to fixed nearest-rounded nodes. Common ULEB recoding preserves actual decoded fields and is distinct from native format performance.

The numerical guarantees apply to the prepared piecewise-linear reference and decoded wire values. They do not establish physical sensor accuracy, erased-data recovery, radio-energy savings or prospective flight reliability.
