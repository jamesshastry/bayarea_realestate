# Proposition 13

> California's 1978 cap on property-tax growth. The single biggest reason buying matters more than renting in California.

Proposition 13 (CA Constitution Article XIIIA) does two things:

1. **Caps the base property-tax rate at 1%** of assessed value statewide. (Local voter-approved bonds and Mello-Roos add to that — the *effective* Bay Area rate is usually 1.10–1.20%.)
2. **Caps annual increases in assessed value at 2%** as long as you own the home. The assessed value is reset to the purchase price (the "base year") only when ownership transfers or major construction happens.

The practical effect: a long-time owner can pay vastly less in property tax than a new buyer next door. This is the most under-discussed part of buying in California — your first-year tax bill is *not* a stable estimate of what your neighbor pays, and it *will* compound 2%/yr forever (whereas your mortgage P&I is fixed for the loan's life on a fixed-rate loan).

We model Prop 13 in two places:
- **Affordability** assumes year-1 assessment ≈ purchase price (correct for a fresh purchase).
- **TCO (10/30-year)** compounds the assessed value at 2%/yr to project property tax in year 10, year 30, etc.

### Concrete example

You buy a $1.5M Fremont home in 2026. Your effective tax rate is ~1.16% (Alameda County base + voter bonds), so year-1 tax is **$17,400**.

By 2036 (10 years), under Prop 13's 2% cap your assessed value is $1.5M × 1.02¹⁰ ≈ **$1.83M**, so your tax bill is **$21,200**. Without Prop 13, if the home had risen at the full Bay Area appreciation rate (say 4%/yr), your assessed value would be $2.22M and tax would be **$25,800** — a $4,600/yr difference, growing every year.

This is also why **selling and re-buying is structurally painful in CA**: even a same-priced "lateral" move resets your assessed value to today's purchase price.

See also: [Prop 13 base year](./prop-13-base-year.md).
