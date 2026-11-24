//! Minimal UTC timestamp parsing: `YYYY-MM-DD` (start of that UTC day) or RFC 3339.

use crate::error::{Error, Result};

/// Seconds since 1970-01-01T00:00:00Z.
pub type Instant = i64;

fn days_from_civil(y: i64, m: i64, d: i64) -> i64 {
    // Howard Hinnant's algorithm, proleptic Gregorian calendar.
    let y = if m <= 2 { y - 1 } else { y };
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = y - era * 400;
    let mp = (m + 9) % 12;
    let doy = (153 * mp + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146_097 + doe - 719_468
}

fn num(s: &str, raw: &str) -> Result<i64> {
    if s.is_empty() || !s.bytes().all(|b| b.is_ascii_digit()) {
        return Err(Error::BadTimestamp(raw.to_string()));
    }
    s.parse().map_err(|_| Error::BadTimestamp(raw.to_string()))
}

fn days_in_month(y: i64, m: i64) -> i64 {
    match m {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        _ if (y % 4 == 0 && y % 100 != 0) || y % 400 == 0 => 29,
        _ => 28,
    }
}

/// Parse `YYYY-MM-DD`, `YYYY-MM-DDTHH:MM[:SS[.fff]](Z|+HH:MM|-HH:MM)`.
pub fn parse(raw: &str) -> Result<Instant> {
    let bad = || Error::BadTimestamp(raw.to_string());
    let s = raw.trim();
    if s.len() < 10 || s.as_bytes()[4] != b'-' || s.as_bytes()[7] != b'-' {
        return Err(bad());
    }
    let (y, m, d) = (
        num(&s[0..4], raw)?,
        num(&s[5..7], raw)?,
        num(&s[8..10], raw)?,
    );
    if !(1..=12).contains(&m) || d < 1 || d > days_in_month(y, m) {
        return Err(bad());
    }
    let mut secs = days_from_civil(y, m, d) * 86_400;
    if s.len() == 10 {
        return Ok(secs);
    }
    let rest = &s[10..];
    let rest = rest
        .strip_prefix('T')
        .or_else(|| rest.strip_prefix(' '))
        .ok_or_else(bad)?;
    let (clock, offset) = match rest.find(['Z', 'z', '+', '-']) {
        Some(i) => rest.split_at(i),
        None => return Err(bad()),
    };
    let parts: Vec<&str> = clock.split(':').collect();
    if parts.len() < 2 || parts.len() > 3 {
        return Err(bad());
    }
    let (hh, mm) = (num(parts[0], raw)?, num(parts[1], raw)?);
    let ss = match parts.get(2) {
        Some(p) => num(p.split('.').next().unwrap_or(""), raw)?,
        None => 0,
    };
    if hh > 23 || mm > 59 || ss > 60 {
        return Err(bad());
    }
    secs += hh * 3600 + mm * 60 + ss;
    if offset.eq_ignore_ascii_case("z") {
        return Ok(secs);
    }
    let sign = if offset.starts_with('+') { 1 } else { -1 };
    let off = &offset[1..];
    if off.len() != 5 || off.as_bytes()[2] != b':' {
        return Err(bad());
    }
    let (oh, om) = (num(&off[0..2], raw)?, num(&off[3..5], raw)?);
    Ok(secs - sign * (oh * 3600 + om * 60))
}

/// The current instant from the system clock.
pub fn now() -> Instant {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_or(0, |d| i64::try_from(d.as_secs()).unwrap_or(i64::MAX))
}

#[cfg(test)]
mod tests {
    use super::parse;

    #[test]
    fn dates_and_offsets() {
        assert_eq!(parse("1970-01-01").unwrap(), 0);
        assert_eq!(parse("2026-11-25").unwrap(), 1_795_564_800);
        assert_eq!(parse("2026-11-25T00:00:00Z").unwrap(), 1_795_564_800);
        assert_eq!(parse("2026-11-24T19:00:00-05:00").unwrap(), 1_795_564_800);
        assert_eq!(parse("2026-11-25T05:30+05:30").unwrap(), 1_795_564_800);
        assert_eq!(
            parse("2024-02-29").unwrap() + 86_400,
            parse("2024-03-01").unwrap()
        );
    }

    #[test]
    fn rejects_garbage() {
        for s in [
            "",
            "2026-13-01",
            "2026-02-30",
            "2026-11-24T25:00Z",
            "2026-11-24T10:00",
            "2026/11/24",
            "2026-11-24T10:00+0500",
        ] {
            assert!(parse(s).is_err(), "{s}");
        }
    }
}
