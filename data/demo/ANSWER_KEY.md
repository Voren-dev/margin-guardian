# Answer key: what changed in the new price lists

For testing only. Do not show in the demo and do not feed it to the agents.

## VeloParts (new Q4 PDF vs Q3)
- VP-10233 front light 800 lm: 24.90 -> 26.39 (**+6%**, top seller, ~140 units/month)
- VP-10234 rear light: 11.40 -> 11.75 (+3.1%)
- VP-30108 folding lock: 34.90 -> 36.20 (+3.7%)
- VP-60030 phone mount: 8.30 -> 8.65 (+4.2%)
- VP-50310 torque wrench: 39.50 -> 37.50 (**-5.1%**, a decrease)
- VP-50320 chain checker: **discontinued** (missing from the new list)
- VP-10250 front light 1200 lm: **new product** (32.80)

## Ciclo Componenti (new 2026-10 PDF vs 2026-06)
- CC-S305 comfort saddle: 16,90 -> 18,25 (+8%)
- CC-C705 chain 11s: 21,90 -> 22,90 (+4.6%)
- CC-G401 grips: minimum order 5 -> **20 pieces**
- **Footnote trap**: from 1 Nov 2026, **+4% on all aluminium items** (marked with *), *not included in the listed prices*. Affects CC-A118, CC-A121, CC-A130, CC-A140, CC-M520, CC-B610.

## TrailGear (new Autumn xlsx vs Summer)
- All tyres +5%: TG-T1001, TG-T1002, TG-T1010, TG-T1020
- TG-L5001 wet lube: 4.70 -> 4.90 (+4.3%)
- **Pack trap**: TG-B4001 disc pads go from pack of 4 at GBP 9.60 to **pack of 2 at GBP 5.10**. The price "drops", but per unit it is **+6.25%**.
- All prices in GBP: they must be converted before comparing with the EUR catalog.

## Sales history: the price elasticity hidden in the data
`sales_history.csv` is generated with a known price elasticity of demand per category
(units change by e% when the price changes by 1%). An estimate from the data should land near these values.

| Category | True elasticity |
|---|---|
| Accessories | -1.5 |
| Apparel | -1.7 |
| Bags | -1.4 |
| Bottles | -1.6 |
| Brakes | -0.6 |
| Components | -0.8 |
| Drivetrain | -0.7 |
| Lights | -1.3 |
| Locks | -0.9 |
| Maintenance | -0.8 |
| Pumps | -1.1 |
| Saddles | -1.0 |
| Tools | -1.0 |
| Tubes | -0.5 |
| Tyres | -0.9 |

Check done on generation day with a plain log-log regression per category (SKU and calendar-month effects):
every estimate within 0.3 of the true value. Categories with one or two products have wide intervals,
so the app must show the interval, not only the point estimate.
