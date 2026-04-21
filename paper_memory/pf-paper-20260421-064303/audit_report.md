# PaperForge Audit Report

**Run ID:** `pf-paper-20260421-064303`
**Generated:** 2026-04-21T06:59:33+00:00 UTC

---

## 1. Pipeline execution summary

| Phase | Status | Started | Completed |
|---|---|---|---|
| SCOUT | PASS | 2026-04-21T06:58:15+00:00 | 2026-04-21T06:58:15+00:00 |
| MINER | PASS | 2026-04-21T06:58:15+00:00 | 2026-04-21T06:58:15+00:00 |
| SIGMA_JOB1 | PASS | 2026-04-21T06:58:15+00:00 | 2026-04-21T06:58:15+00:00 |
| FORGE | PASS | 2026-04-21T06:58:15+00:00 | 2026-04-21T06:58:15+00:00 |
| SIGMA_JOB2 | PASS | 2026-04-21T06:58:15+00:00 | 2026-04-21T06:58:15+00:00 |
| CODEC | PASS | 2026-04-21T06:58:15+00:00 | 2026-04-21T06:58:15+00:00 |
| QUILL | PASS | 2026-04-21T06:58:15+00:00 | 2026-04-21T06:58:15+00:00 |
| HAWK | PASS | 2026-04-21T06:58:15+00:00 | 2026-04-21T06:58:15+00:00 |

## 2. Pre-Analysis Plan commitment

- **Locked at:** 2026-04-21T06:44:59+00:00
- **Locked by:** SIGMA_JOB1
- **PAP SHA-256:** `90db17e691d0cee623276edcf754c8be...`
- **FORGE start:** 2026-04-21T06:46:08+00:00
- **Temporal ordering verified:** YES — PAP locked before FORGE started

## 3. Data provenance

- **Source:** unknown
- **Rows:** 3514
- **Date range:** {'start': '2010-01-05', 'end': '2023-12-29'}
- **SHA-256:** `0422ec5baff51d97eb533e467c5013eb...`
- **Download timestamp:** 2026-04-21T06:43:48+00:00
- **Library versions:**
  - pandas: 2.2.3
  - numpy: 2.1.3
  - yfinance: 0.2.66

## 4. FORGE simulation results

| Concentration | Seed | Sharpe | Mean reward | Episodes |
|---|---|---|---|---|
| 10% | 42 | 0.9875 | 0.000203 | 2000 |
| 10% | 1337 | -1.1288 | -0.000201 | 2000 |
| 10% | 9999 | 1.1268 | 0.000232 | 2000 |
| 30% | 42 | 0.8450 | 0.000260 | 2000 |
| 30% | 1337 | -1.3645 | -0.000345 | 2000 |
| 30% | 9999 | 0.9929 | 0.000307 | 2000 |
| 60% | 42 | 0.0168 | 0.000012 | 2000 |
| 60% | 1337 | -2.7484 | -0.001321 | 2000 |
| 60% | 9999 | 0.1407 | 0.000098 | 2000 |

## 5. Statistical test results

- **Newey-West t-stat:** -0.681253069342755
- **Newey-West p-value:** 0.4957113733190195
- **Bonferroni threshold:** 0.008333333333333333
- **Bonferroni significant:** False

## 6. CODEC audit

- **CODEC verdict:** ## verdict: FAIL
- **KS statistic:** ks_statistic: insufficient_numeric_data
- **Term overlap:** term_overlap_ratio: 0.538

## 7. HAWK peer review scores

| Dimension | Score |
|---|---|
| Contribution Novelty | 4/5 |
| Identification Validity | 4/5 |
| Methodology Correctness | 4/5 |
| Robustness Evidence | 4/5 |
| Internal Consistency | 4/5 |
| Economic Significance | 4/5 |
| Presentation Quality | 4/5 |
| **Overall mean** | **4.00/5** |

## 8. Artifact file hashes

| File | SHA-256 |
|---|---|
| literature_map.md | `95d6583fd789611e21031c3a72d17e3e...` |
| codec_spec.md | `200bd38edbe324b2f16a048ebaa2a202...` |
| codec_pass2.md | `0a61654856a15d537f89e538e995c33a...` |
| codec_mismatch.md | `6eba44e995592f069527899b69b03e19...` |
| paper_draft_v1.tex | `780b425b2373d7b38b5d0fae707f8fbe...` |

## 9. Integrity statement

This audit report was generated automatically by the PaperForge pipeline.