# Capacity engine — measured output

Generated 2026-09-12 18:14Z by `python -m oci capacity`. Catalogue: 19232 objects from the public CelesTrak groups; screening run run_20260912T1700Z_4371 (5745 objects, 7 d, 24492 conjunctions).

Every figure is MODELLED (kinetic-gas flux, §11.13) except the spatial density, the mean relative speed, and the
shells where `q` is calibrated from the pairwise screener (COMPUTED). The calibration factor column is the
pairwise conjunction rate divided by the flux-model rate in the same shell — reported, never used to tune.

```
SHELL MAP  Pc* 1e-05 · c_intra 0.05 · calibrated shells shell_0500, shell_0550, shell_0600, shell_0650, shell_0700, shell_0750, shell_0800, shell_0850, shell_0900, shell_0950, shell_1000
  q fallback: pooled over screened shells ['shell_0500', 'shell_0550', 'shell_0600', 'shell_0650', 'shell_0700', 'shell_0750', 'shell_0800', 'shell_0850', 'shell_0900', 'shell_0950', 'shell_1000']: 403/29090 conjunctions above Pc* = 1.39e-02
    shell km      N active   dead  D obj/km³  v_rel  conj/yr        q   M/yr   OCS hazard life yr      κ        regime  calib
    200-250      21     21      0   7.67e-10    9.5      8.1 1.4e-02*   0.11  99.9   0.00     0.0      —             —    N/A
    250-300      84     83      1   3.02e-09    9.8     41.1 1.4e-02*   0.57  99.5   0.00     0.0      —             —    N/A
    300-350     376    374      2   1.33e-08    9.8     83.6 1.4e-02*   1.16  99.0   0.00     0.1      —             —    N/A
    350-400     878    871      7   3.06e-08    8.3    176.6 1.4e-02*   2.45  98.0   0.00     0.2      —             —    N/A
    400-450     388    378     10   1.33e-08    9.9    277.5 1.4e-02*   3.84  96.8   0.01     0.4      —             —    N/A
    450-500    9692   9675     17   3.28e-07    8.5   1179.2 1.4e-02*  16.34  86.4   0.30     0.9      —             —    N/A
    500-550     946    914     32   3.16e-08   10.0    726.5  5.0e-03   3.66  96.9   0.10     2.0   0.00   SUBSTITUTES   0.85
    550-600    1054    994     60   3.47e-08    9.8    664.1  7.9e-03   5.27  95.6   0.22     4.4   0.00   SUBSTITUTES   0.87
    600-650     733    595    138   2.38e-08    9.3    428.8  1.2e-02   5.14  95.7   0.51     9.6   0.00   SUBSTITUTES   0.86
    650-700     356    133    223   1.14e-08    9.8    277.6  1.3e-02   3.59  97.0   0.66    20.2   0.00   SUBSTITUTES   1.09
    700-750     371     45    326   1.17e-08    9.8    283.0  2.3e-02   6.57  94.5   0.25    40.8    N/A           N/A   1.19
    750-800     554    150    404   1.72e-08    9.7    409.1  2.6e-02  10.61  91.2   1.00    77.4   0.00   SUBSTITUTES   1.00
    800-850     558     75    483   1.71e-08    9.6    405.0  2.6e-02  10.39  91.3   0.61   100.0    N/A           N/A   0.82
    850-900     430     66    364   1.30e-08    9.6    309.8  1.7e-02   5.29  95.6   0.15   100.0    N/A           N/A   0.76
    900-950     222     82    140   6.62e-09    9.6    157.9  1.6e-02   2.53  97.9   0.17   100.0   0.00   SUBSTITUTES   1.22
    950-1000    165     73     92   4.86e-09    9.7    116.2  1.3e-02   1.50  98.8   0.15   100.0    N/A           N/A   1.34
   1000-1050     87     21     66   2.53e-09    9.5     58.7  2.9e-02   1.72  98.6   0.05   100.0    N/A           N/A   2.20
   1050-1100    275    233     42   7.88e-09    9.5    101.9 1.4e-02*   1.41  98.8   0.56   100.0      —             —    N/A
   1100-1150    180    143     37   5.09e-09    8.4    105.6 1.4e-02*   1.46  98.8   0.16   100.0      —             —    N/A
   1150-1200    394    383     11   1.10e-08    9.3     99.8 1.4e-02*   1.38  98.8   0.42   100.0      —             —    N/A
   1200-1250    342    337      5   9.42e-09    9.3     21.5 1.4e-02*   0.30  99.8   0.37   100.0      —             —    N/A
   1400-1450     31     29      2   8.10e-10    8.1     16.3 1.4e-02*   0.23  99.8   0.54   100.0      —             —    N/A
   1450-1500     60     60      0   1.55e-09    9.1     34.8 1.4e-02*   0.48  99.6   0.66   100.0      —             —    N/A
  * q carried from the pooled screening calibration (MODELLED); unstarred q is calibrated in that shell (COMPUTED)
  TWO PEAKS: workload peak 475.0 km · hazard peak 775.0 km · DIFFER (OCS anchored to M_viability = 120/sat-yr: 2025 study: 10 CAMs/month = operationally unviable (SPEC §2.2))
```

```
DEPLOYMENT  5000 satellites · 53° · target 550 km · c_intra 0.05 · Pc* as above
     alt OCS before OCS after  M/sat/yr imposed m/s/yr       hazard → decay yr WORKLOAD HAZARD
    500        96.9      96.1      4.69           1879   0.10 →  1.82      1.3        1      1
    525        96.9      96.1      4.69           1879   0.10 →  2.00      2.0        2      2
    550*       95.6      93.6      7.68           3039   0.22 →  2.39      3.0        4      3 ◀
    570        95.6      93.6      7.68           3039   0.22 →  2.70      4.1        5      4
    600        95.7      93.3      8.01           2508   0.51 →  3.66      6.6        6      5
    650        97.0      95.4      5.57            677   0.66 →  5.85     14.0        3      6
  Both optima coincide on this range.
  workload-optimal 500 km · hazard-optimal 500 km · balanced under stated weights (0.5, 0.5) → 500 km
  Workload-optimal altitude is 500 km (manoeuvres/sat-yr from 4.69 at best to 8.01 at worst) because it follows the existing traffic density shell by shell. Hazard-optimal altitude is 500 km because natural decay lifetime grows from 1.3 yr at 500 km to 14.0 yr at 650 km, so every PMD failure persists that much longer. Both currencies agree on this range — report that it is not the general case.
  This is a trade-off, not an optimum. Report both.
  if the constellation were NOT coordinated (c_intra = 1.0): 31.15 manoeuvres/sat-yr, OCS 74.0 vs 7.68 and 93.6 coordinated
```

## Reading it

- OCS is anchored to the published viability threshold (10 manoeuvres/month = 120 per satellite-year); it is not a composite.
- Workload follows traffic density; hazard follows inactive mass × decay lifetime. They peak at different altitudes
  — the two-peaks structure of the literature (§2.6) reproduced from the public catalogue.
- The catalogue is the public CelesTrak groups (active + four debris groups). Most tracked debris and rocket bodies
  are absent until Space-Track is wired in, so absolute burdens are lower bounds; the shape is what is measured.
- κ is estimated by simulation in the shells covered by a screening run only; elsewhere it is N/A with the reason.
