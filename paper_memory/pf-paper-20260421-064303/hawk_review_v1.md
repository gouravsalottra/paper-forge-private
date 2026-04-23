## Summary
The paper tests whether higher passive concentration weakens momentum profitability in GSCI energy futures, with the primary estimand defined as the Sharpe-ratio difference between high- and low-concentration periods. The current draft does not deliver a valid identified result. The observed Sharpe differential is economically large, but the inference is unusable because the effective sample is only 9 observations, the factor-control implementation is a development proxy rather than the specified data source, seed consistency fails under the paper’s own rules, and the CODEC audit shows that the implemented pipeline is not fully verified against the stated design. This is not a presentation problem; it is a design-execution mismatch with inadequate statistical support.

## Mandatory revision items

1. **Section Abstract, lines 1–18**
   - **Problem:** The abstract reports a large negative Sharpe differential as the central empirical finding even though the paper’s own decision rule says the finding is invalid when seed consistency fails. Economically, a result that does not replicate across the required seeds is not an admissible finding under the stated protocol. Presenting it as the headline result overstates evidence.
   - **Required fix:** Rewrite the abstract so that the lead result is protocol failure, not the observed point estimate. Explicitly state that the primary finding is invalid under the pre-specified seed policy and that the reported differential is descriptive only unless the full three-seed validation is passed and documented.
   - **Responsible component:** [QUILL]

2. **Section Introduction, paragraph discussing audit-oriented design, lines 32–45**
   - **Problem:** The paper claims an “audit-traceable” and “pre-registered” design, but the materials show the pre-analysis-plan status was marked UNCOMMITTED in the draft discussion, temporal ordering is flagged as “CHECK NEEDED,” and the CODEC audit does not verify several required controls. Economically and procedurally, identification based on a pre-committed design is not credible unless commitment timing and gatekeeping are demonstrated.
   - **Required fix:** Provide a dated audit table showing: PAP lock timestamp, commitment status at run start, forge start timestamp, and evidence that no analysis outputs used in the paper were generated before commitment. If commitment did not precede execution, remove all pre-registration language and restate the paper as exploratory.
   - **Responsible component:** [CODEC]

3. **Section Abstract and primary-results discussion, lines reporting Newey-West t-test**
   - **Problem:** The primary t-test is based on **n = 9** with **4 HAC lags**. Statistically, HAC inference with such a short series is unstable and not informative; with only 9 observations, the long-run variance estimate is poorly determined and the test has little meaning. This is not a minor power issue; it undermines the claimed inferential framework.
   - **Required fix:** Reconstruct the primary test at the underlying rolling-window frequency rather than collapsing to 9 observations, or justify exactly what the 9 observations are and why HAC with 4 lags is valid in that setting. In addition, report finite-sample-appropriate inference: randomization/permutation test for the concentration-label assignment, block bootstrap confidence intervals for the Sharpe differential, and sensitivity to lag choice \(L=0,1,2\). If only 9 independent observations truly exist, drop HAC-based significance claims entirely and relabel the analysis as descriptive.
   - **Responsible component:** [SIGMA]

4. **Section Results tables for Sharpe summaries and primary metric**
   - **Problem:** The paper compares “high” and “low” concentration periods, but the scenario table is organized at 10%, 30%, and 60% concentration while the hypothesis threshold is “exceeds 30%.” The mapping from the three scenarios to the binary high/low comparison is not identified. Economically, the estimand depends on the exact partition rule; if 30% is both a midpoint scenario and a threshold, the treatment definition is ambiguous.
   - **Required fix:** State the exact classification rule used to construct `sharpe_high_mean` and `sharpe_low_mean`: whether 30% is included in high, low, or excluded; whether the primary comparison is 60% vs 10%, above-30% vs below-30%, or pooled bins. Then rerun all primary tables using that exact rule and provide a robustness table for alternative threshold codings: \(>30\), \(\ge 30\), and tercile-based bins.
   - **Responsible component:** [QUILL]

5. **Section Results, factor-control discussion**
   - **Problem:** The factor-control implementation uses only 9 observations and explicitly substitutes development-run proxies for the specified WRDS Fama-French factors. This does not implement the paper’s stated design. Statistically, an OLS with \(R^2=1.0\) on 9 observations using proxy factors is not credible evidence of factor adjustment; it is a red flag for overfit or degenerate construction.
   - **Required fix:** Replace the proxy factor run with the specified factor data source, report the exact merge and sample coverage, and rerun the factor-adjusted regressions on the full available sample. Include a table comparing proxy-factor and true-factor estimates, with observation counts and date ranges. If WRDS factors are unavailable for the asset class, revise the design and remove claims of Fama-French adjustment rather than presenting the proxy as confirmatory evidence.
   - **Responsible component:** [MINER]

6. **Section Results, GARCH and DCC discussion**
   - **Problem:** The paper invokes GARCH(1,1) and DCC-GARCH as part of the mechanism, but the reported GARCH estimates are degenerate (\(\alpha=0\), \(\beta=1\), persistence \(=1\)) on 9 observations, and DCC is estimated for only one pair. Econometrically, these outputs do not identify volatility clustering or dynamic correlation; they are artifacts of an unusably small sample.
   - **Required fix:** Rerun GARCH/DCC on the full return series at the native frequency with sufficient observations for stable estimation, report convergence diagnostics and parameter constraints, and show whether the mechanism variables change across concentration regimes. If the sample cannot support these models, remove them from the claimed mechanism and from the abstract/introduction.
   - **Responsible component:** [SIGMA]

7. **Section Data/Methods where futures construction is described**
   - **Problem:** The CODEC audit reports a mismatch between the specified adjustment method (`ratio_backward`) and the implemented method (`yfinance auto_adjust=True`). For futures return construction, roll and adjustment conventions directly affect momentum signals and Sharpe ratios. This is a substantive implementation issue, not a cosmetic one.
   - **Required fix:** Implement the exact specified roll-adjustment method and regenerate all return-based outputs, or formally amend the design and provide a side-by-side replication showing that the main Sharpe differential is robust to both `ratio_backward` and the current implementation. The paper must identify which series enters the momentum strategy and why.
   - **Responsible component:** [CODEC]

8. **Section Methods / empirical sample construction**
   - **Problem:** The paper claims to study “GSCI energy futures,” but the reported DCC output has only one estimated pair and the rest of the materials do not document contract coverage, date range, roll schedule, missing-data handling, or how passive concentration is measured and aligned to returns. Economically, without transparent coverage and alignment, the treatment variable may be mismeasured and the sample may not represent the stated market.
   - **Required fix:** Add a data-construction table listing every contract, exchange, sample start/end, roll rule, observation frequency, passive concentration source, merge key, and final usable observations by contract. Also report how many observations are lost at each cleaning step and whether concentration is contemporaneous, lagged, or averaged over the return window.
   - **Responsible component:** [MINER]

9. **Section Results and conclusion language**
   - **Problem:** The draft repeatedly frames the evidence as “large negative observed Sharpe differential” despite non-significance, failed seed consistency, and invalid mechanism tests. Economically, this is classic overclaiming from a noisy point estimate. The paper’s own minimum-effect rule does not override failed inference and failed protocol validity.
   - **Required fix:** Rewrite the results and conclusion so that the paper states plainly: the observed effect is not statistically reliable, not seed-consistent, and not protocol-valid in the current implementation. Any discussion of economic magnitude must be explicitly labeled exploratory and conditional on successful replication.
   - **Responsible component:** [QUILL]

10. **Section Methods / reproducibility and seed policy**
    - **Problem:** The seed policy requires validation across seeds \([1337, 42, 9999]\), but the audit states the full seed list is not found in the provided code context and the validation file says the finding does not hold across all three seeds. Under the paper’s own rules, this invalidates the result. A result that depends on one seed is not reproducible evidence.
    - **Required fix:** Provide a seed-by-seed replication table for every primary output: Sharpe differential, HAC test, factor regression, and any bootstrap intervals. Archive the exact code path that loops over all three seeds and aggregates the decision rule. If the result remains seed-sensitive, redesign the simulation or estimation procedure so the primary conclusion is not driven by seed choice.
    - **Responsible component:** [FORGE]

11. **Section Methods / code-to-paper conformity**
    - **Problem:** The CODEC report shows 34/43 specified parameters matched, 2 mismatched, and 7 not found in code, including training episodes, evaluation frequency, and audit gatekeeping fields. Even if some are pipeline-level controls, the paper currently asserts stronger implementation fidelity than has been verified. This is a code-specification conformity problem.
    - **Required fix:** Produce a complete code-spec concordance appendix listing each specified parameter, where it is implemented, and whether it affects the reported empirical outputs. For every “not found” item, either implement it and rerun the pipeline or document that it is irrelevant to this paper and remove it from the claimed design. The revised manuscript must not claim full protocol compliance unless CODEC verifies it.
    - **Responsible component:** [CODEC]

## Optional suggestions

1. Report the date range and number of rolling 252-day windows used in the primary Sharpe calculations, and include a time-series plot of concentration and momentum Sharpe by window.  
   - **Responsible component:** [QUILL]

2. Add a placebo analysis using non-energy commodity futures or an alternative concentration threshold to show whether the observed pattern is specific to the stated mechanism.  
   - **Responsible component:** [SIGMA]

3. Replace the current factor discussion with commodity-relevant controls if equity Fama-French factors are not theoretically appropriate for futures momentum.  
   - **Responsible component:** [FORGE]

4. Include a simple table reconciling every number in the abstract to the exact source file and row used to generate it.  
   - **Responsible component:** [QUILL]

## Decision
MAJOR_REVISION