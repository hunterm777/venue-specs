# Funding

Excerpt of https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding.md as read on 2026-11-24
(the sentences that state the interest rate, the funding formula and the cap, verbatim).

For consistency with CEXs, interest rate component is predetermined at 0.01% every 8 hours, which is 0.00125% every hour, or 11.6% APR paid to short.

The funding rate formula applies to 8 hour funding rate. However, funding is paid every hour at one eighth of the computed rate for each hour. The specific formula is `Funding Rate (F) = Average Premium Index (P) + clamp (interest rate - Premium Index (P), -0.0005, 0.0005)`. The premium is sampled every 5 seconds and averaged over the hour.

Funding on Hyperliquid is capped at 0.5%/hour. Note that this is much less aggressive capping than CEX counterparts.
