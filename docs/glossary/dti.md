# Debt-to-income ratio (DTI)

> Front-end: 28% · Back-end: 36%

DTI is the share of your gross monthly income that goes to debt. Lenders use two flavors:

- **Front-end DTI** counts only your future housing cost — principal, interest, taxes, insurance, HOA, Mello-Roos, PMI. The conservative ceiling lenders quote is **28%**.
- **Back-end DTI** counts the housing cost *plus* every other monthly debt: car loans, student loans, credit-card minimums, child support. The conservative ceiling is **36%**.

Some loan programs accept higher back-end ratios — the qualified-mortgage rule lets banks go up to 43%, and manual underwriting sometimes goes to 50% — but **the higher you push, the less of a buffer you have for property-tax surprises, rate resets, or a temporary income dip.**

We use 28/36 throughout the affordability calculator because they reflect *comfort*, not *approval*. The "max approvable" row in the affordability output stretches further (per loan type), but the **comfortable** and **stretch** prices anchor on 28% and 36% respectively.

### Concrete example

You earn $300,000/yr ($25,000/month) and have a $400/month student loan.

- Front-end DTI cap: 28% × $25,000 = **$7,000/month** for housing → that drives your "comfortable" price.
- Back-end DTI cap: 36% × $25,000 − $400 = **$8,600/month** for housing → that drives your "stretch" price.

In Alameda County at a 6.75% rate with $150K down, $7,000/month buys roughly $920K of house (P&I + tax + insurance), and $8,600/month buys roughly $1.16M.
