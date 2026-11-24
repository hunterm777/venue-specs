# Watcher replay fixtures

- `hyperliquid_fees.md`, `hyperliquid_funding.md`: excerpts of the live Hyperliquid pages as read
  on 2026-11-24, copied cell for cell and sentence for sentence. The replay test alters one value
  to stand in for a fee change.
- `kalshi_changelog_before.xml`, `kalshi_changelog_after.xml`: **reconstructed, not raw captures.**
  An RSS feed shaped like Kalshi's, before and after the August 2026 maker-fee announcement. The
  announcement sentences are quoted from Kalshi's changelog as read on 2026-11-24; the feed markup
  around them is ours.
- `polymarket_perps_changelog_before.txt`, `polymarket_perps_changelog_after.txt`: excerpts of the
  Polymarket Perps changelog, copied line for line from the rendered page as pasted on 2026-11-24,
  before and after its Nov 19, 2026 entry. Only the lines the parser and replay need are kept. The
  watcher fetches the page's HTML, whose text can break into lines differently, so the parser reads
  the text with its line breaks collapsed.
