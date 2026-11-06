//! Which URLs this tool will hand to a transport at all.
//!
//! The policy is deliberately narrow, because the URL ends up as an argument to an external
//! program and because the whole point of the tool is to know exactly which endpoint said what:
//!
//! * `https://` to any host — the normal case (the default algod is HTTPS).
//! * `http://` **only** to a loopback node: `localhost`, `127.0.0.1` or `[::1]`, with an optional
//!   port. That covers a local algod (an operator splitting trust with `--compile-url`, or a
//!   `LocalNet`) and the test servers, and nothing else. Plain HTTP to any other host is refused:
//!   anyone on the path could then rewrite either half of the comparison.
//! * No credentials in the URL (`user:pass@host`): they would be visible in the process list.
//! * No whitespace or control characters anywhere.
//!
//! The check is applied twice — by the library before any request, and again by the curl
//! transport to choose `--proto` — so a caller that bypasses one still meets the other.

/// How a URL that passed the policy may be fetched.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Scheme {
    /// `https://` — TLS with the transport's default certificate verification.
    Https,
    /// `http://` to a loopback address only.
    LoopbackHttp,
}

/// Apply the policy described in the module docs.
///
/// # Errors
///
/// Returns a human-readable reason when the URL is refused. A refusal happens before any
/// request is made.
pub fn check(url: &str) -> Result<Scheme, String> {
    if url.is_empty() {
        return Err("empty URL".to_owned());
    }
    if url.chars().any(|c| c.is_whitespace() || c.is_control()) {
        return Err("URL contains whitespace or control characters".to_owned());
    }
    let (scheme, rest) = if let Some(rest) = strip_prefix_ascii_ci(url, "https://") {
        (Scheme::Https, rest)
    } else if let Some(rest) = strip_prefix_ascii_ci(url, "http://") {
        (Scheme::LoopbackHttp, rest)
    } else {
        return Err(
            "only https:// URLs are allowed (plain http:// only to localhost, \
                    127.0.0.1 or [::1])"
                .to_owned(),
        );
    };
    let authority = rest.split(['/', '?', '#']).next().unwrap_or_default();
    if authority.is_empty() {
        return Err("URL has no host".to_owned());
    }
    if authority.contains('@') {
        return Err(
            "credentials in the URL are refused (they would be visible in the process list)"
                .to_owned(),
        );
    }
    if scheme == Scheme::LoopbackHttp && !is_loopback_authority(authority) {
        return Err(format!(
            "plain http:// is only allowed to a loopback node (localhost, 127.0.0.1, [::1]); \
             '{authority}' is not one — use https://"
        ));
    }
    Ok(scheme)
}

fn strip_prefix_ascii_ci<'a>(s: &'a str, prefix: &str) -> Option<&'a str> {
    let head = s.get(..prefix.len())?;
    if head.eq_ignore_ascii_case(prefix) {
        s.get(prefix.len()..)
    } else {
        None
    }
}

/// `host` or `host:port`, where host is exactly one of the three loopback spellings.
fn is_loopback_authority(authority: &str) -> bool {
    // Split "host[:port]" at the port colon, keeping the ':' with the port so "host:" (empty
    // port) stays distinguishable from "host". A bracketed IPv6 host contains colons of its own,
    // so it is split after the closing bracket instead.
    let split_at = authority.strip_prefix('[').map_or_else(
        || authority.rfind(':'),
        |_| authority.find(']').map(|i| i + 1),
    );
    let (host, port) = split_at
        .and_then(|i| authority.split_at_checked(i))
        .unwrap_or((authority, ""));
    let port_ok = port.is_empty()
        || port.strip_prefix(':').is_some_and(|digits| {
            !digits.is_empty() && digits.len() <= 5 && digits.bytes().all(|b| b.is_ascii_digit())
        });
    let host_ok = host.eq_ignore_ascii_case("localhost") || host == "127.0.0.1" || host == "[::1]";
    host_ok && port_ok
}

#[cfg(test)]
mod tests {
    use super::{Scheme, check};

    #[test]
    fn https_anywhere_is_allowed() {
        assert_eq!(
            check("https://testnet-api.algonode.cloud"),
            Ok(Scheme::Https)
        );
        assert_eq!(check("HTTPS://node.example:8443/v2"), Ok(Scheme::Https));
    }

    #[test]
    fn plain_http_only_to_loopback() {
        for ok in [
            "http://localhost",
            "http://localhost:4001",
            "http://127.0.0.1:8080/",
            "http://[::1]:4001",
            "http://[::1]",
        ] {
            assert_eq!(check(ok), Ok(Scheme::LoopbackHttp), "{ok}");
        }
        for refused in [
            "http://testnet-api.algonode.cloud",
            "http://127.0.0.2:4001",
            "http://localhost.evil.example",
            "http://localhost:80x",
            "http://localhost:",
            "http://[::2]:4001",
            "http://127.0.0.1:4001:5",
        ] {
            assert!(check(refused).is_err(), "{refused} must be refused");
        }
    }

    #[test]
    fn other_schemes_credentials_and_junk_are_refused() {
        for refused in [
            "",
            "ftp://example.com",
            "file:///etc/passwd",
            "-K/etc/passwd",
            "testnet-api.algonode.cloud",
            "https://",
            "https://user:pw@node.example",
            "https://node.example/a b",
            "https://node.example/\nX-Injected: 1",
        ] {
            assert!(check(refused).is_err(), "{refused:?} must be refused");
        }
    }
}
