//! The production [`Transport`]: HTTPS through the system `curl` executable.
//!
//! **Why a subprocess, not an HTTP crate.** The constitution consumes C only as the vendored
//! Falcon reference, so this crate's dependency graph must contain no `ring`, `aws-lc-sys`,
//! `aws-lc-rs` or `openssl-sys`. Every mainstream Rust HTTPS stack pulls one of them in: `rustls`
//! needs a crypto provider and its two maintained providers are `aws-lc-rs` and `ring`;
//! `native-tls` is `openssl-sys` on Linux. A pure-Rust provider is not available to this
//! repository today. The operating system's own `curl` is: it ships with Windows 10+ (Schannel),
//! macOS, and every CI runner. So TLS and certificate verification are the platform's, and the
//! Rust side stays pure Rust and talks to `curl` through argv and pipes only.
//!
//! **How `curl` is invoked** — always as an argument vector, never through a shell:
//!
//! | argument | why |
//! |---|---|
//! | `-q` (first) | do not read any `.curlrc`, so nothing outside this list changes the request |
//! | `--silent --show-error` | no progress meter; errors still reach stderr, quoted in the report |
//! | `--globoff` | `[` `]` `{` `}` in a URL are literal, not curl globbing |
//! | `--proto =https` | HTTPS only; `=http` (plus `--noproxy *`) only for a loopback node |
//! | no `--location` | redirects are NOT followed: a 3xx is "could not check", never a silent hop to another host |
//! | no `--insecure` | certificate verification stays on |
//! | `--max-time N` | the operator's `--timeout`, for the whole request |
//! | `--max-filesize` | refuse absurd bodies (16 MiB; real ones are a few KiB) |
//! | `--write-out %{http_code}` | the status is appended to stdout and judged by the library |
//! | `--data-binary @-` | the TEAL is streamed byte-exact on stdin: no temporary file, no re-encoding |
//! | `--header "Expect:"` | no `100-continue` round trip on the ~22 KB approval TEAL |
//! | `--url <URL>` | the URL is an option VALUE, so it can never be parsed as an option itself |
//!
//! `--write-out %{http_code}` is used instead of `--fail` / `--fail-with-body` on purpose: it keeps
//! the body of an error response for the report (as the Python quotes `exc.read()`), it works on
//! every `curl` back to 7.x where `--fail-with-body` needs 7.76, and it leaves the decision about
//! what a status means to the library, where it is tested.
//!
//! Proxy environment variables (`HTTPS_PROXY`, ...) are honoured for HTTPS, as Python's
//! `urllib` honours them; they are ignored for a loopback node.

use std::ffi::OsString;
use std::io::{self, Write};
use std::process::{Command, ExitStatus, Stdio};
use std::time::Duration;

use crate::url::{self, Scheme};
use crate::{HttpResponse, MAX_RESPONSE_BYTES, Transport, TransportError, sanitize};

/// How much of curl's stderr is quoted in a failure.
const STDERR_EXCERPT: usize = 300;

/// [`Transport`] over the system `curl` executable.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CurlTransport {
    program: OsString,
}

impl CurlTransport {
    /// `curl` as found by the OS. On Windows, Rust resolves a bare program name in the system
    /// directory before `PATH`, so this is `C:\Windows\System32\curl.exe` there.
    #[must_use]
    pub fn system() -> Self {
        Self::with_program("curl")
    }

    /// A specific `curl` executable (tests use a non-existent one to prove a missing `curl` is
    /// "could not check").
    #[must_use]
    pub fn with_program(program: impl Into<OsString>) -> Self {
        Self {
            program: program.into(),
        }
    }

    fn exec(&self, args: &[String], stdin: Option<&[u8]>) -> Result<HttpResponse, TransportError> {
        let mut child = Command::new(&self.program)
            .args(args)
            .stdin(if stdin.is_some() {
                Stdio::piped()
            } else {
                Stdio::null()
            })
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| {
                TransportError(format!(
                    "could not start '{}': {e} (the system curl is required; it ships with \
                     Windows 10+, macOS and CI runners)",
                    self.program.to_string_lossy()
                ))
            })?;
        let pipe = child.stdin.take();
        // Stream the body on its own thread while this one drains stdout/stderr, so a full pipe
        // in either direction can never deadlock the pair. Dropping `pipe` is curl's EOF.
        let (written, output) = std::thread::scope(|scope| {
            let writer = scope.spawn(move || -> io::Result<()> {
                if let (Some(mut pipe), Some(body)) = (pipe, stdin) {
                    pipe.write_all(body)?;
                    pipe.flush()?;
                }
                Ok(())
            });
            let output = child.wait_with_output();
            (writer.join(), output)
        });
        let output = output.map_err(|e| TransportError(format!("waiting for curl failed: {e}")))?;
        if !output.status.success() {
            return Err(TransportError(format!(
                "curl {}{}",
                describe_exit(output.status),
                stderr_excerpt(&output.stderr)
            )));
        }
        match written {
            Ok(Ok(())) => {}
            Ok(Err(e)) => {
                return Err(TransportError(format!(
                    "could not stream the TEAL to curl: {e}"
                )));
            }
            Err(_) => {
                return Err(TransportError(
                    "the thread streaming the TEAL to curl failed".into(),
                ));
            }
        }
        parse_output(output.stdout)
    }
}

impl Transport for CurlTransport {
    fn describe(&self) -> String {
        let program = self.program.to_string_lossy();
        match Command::new(&self.program)
            .args(["-q", "--version"])
            .stdin(Stdio::null())
            .stderr(Stdio::null())
            .output()
        {
            Ok(out) if out.status.success() => {
                let text = String::from_utf8_lossy(&out.stdout);
                let line = text
                    .lines()
                    .find(|l| l.starts_with("curl "))
                    .unwrap_or("curl (?)");
                format!("system {}", sanitize(line.trim()))
            }
            Ok(out) => format!(
                "'{program}' (--version exited {})",
                describe_exit(out.status)
            ),
            Err(e) => format!("'{program}' (not runnable: {e})"),
        }
    }

    fn get(&self, url: &str, timeout: Duration) -> Result<HttpResponse, TransportError> {
        self.exec(&args(url, timeout, false)?, None)
    }

    fn post_teal(
        &self,
        url: &str,
        teal: &[u8],
        timeout: Duration,
    ) -> Result<HttpResponse, TransportError> {
        self.exec(&args(url, timeout, true)?, Some(teal))
    }
}

/// The exact argument vector for one request. Public so the safety-relevant arguments are
/// asserted by tests rather than described in prose only.
///
/// # Errors
///
/// [`TransportError`] if `url` is refused by [`url::check`].
pub fn args(url: &str, timeout: Duration, post: bool) -> Result<Vec<String>, TransportError> {
    let scheme =
        url::check(url).map_err(|reason| TransportError(format!("refused URL {url}: {reason}")))?;
    let mut args: Vec<String> = ["-q", "--silent", "--show-error", "--globoff", "--proto"]
        .into_iter()
        .map(String::from)
        .collect();
    match scheme {
        Scheme::Https => args.push("=https".into()),
        Scheme::LoopbackHttp => args.extend(["=http", "--noproxy", "*"].map(String::from)),
    }
    args.extend([
        "--max-time".into(),
        timeout.as_secs().max(1).to_string(),
        "--max-filesize".into(),
        MAX_RESPONSE_BYTES.to_string(),
        "--write-out".into(),
        "%{http_code}".into(),
        "--header".into(),
        "Accept: application/json".into(),
    ]);
    if post {
        args.extend(
            [
                "--header",
                "Content-Type: text/plain",
                "--header",
                "Expect:",
                "--data-binary",
                "@-",
            ]
            .map(String::from),
        );
    }
    args.extend(["--url".into(), url.to_owned()]);
    Ok(args)
}

/// Split curl's stdout into the body and the three-digit status `--write-out` appended.
fn parse_output(mut stdout: Vec<u8>) -> Result<HttpResponse, TransportError> {
    let Some(split) = stdout.len().checked_sub(3) else {
        return Err(TransportError("curl printed no HTTP status".into()));
    };
    let code = stdout.split_off(split);
    let status = std::str::from_utf8(&code)
        .ok()
        .filter(|s| s.bytes().all(|b| b.is_ascii_digit()))
        .and_then(|s| s.parse::<u16>().ok())
        .ok_or_else(|| TransportError("curl did not print a three-digit HTTP status".into()))?;
    if !(100..=599).contains(&status) {
        return Err(TransportError(format!(
            "curl reported no usable HTTP response (status {status:03})"
        )));
    }
    if stdout.len() > MAX_RESPONSE_BYTES {
        return Err(TransportError(format!(
            "response body over the {MAX_RESPONSE_BYTES} B limit"
        )));
    }
    Ok(HttpResponse {
        status,
        body: stdout,
    })
}

fn describe_exit(status: ExitStatus) -> String {
    let Some(code) = status.code() else {
        return format!("was terminated ({status})");
    };
    let meaning = match code {
        1 => " (unsupported protocol: refused by --proto)",
        3 => " (malformed URL)",
        6 => " (could not resolve host)",
        7 => " (could not connect)",
        28 => " (timed out)",
        35 => " (TLS handshake failed)",
        52 => " (empty reply from server)",
        56 => " (failure receiving data)",
        60 => " (TLS certificate could not be verified)",
        63 => " (response over --max-filesize)",
        _ => "",
    };
    format!("exited with code {code}{meaning}")
}

fn stderr_excerpt(stderr: &[u8]) -> String {
    let text = String::from_utf8_lossy(stderr);
    let text = text.trim();
    if text.is_empty() {
        return String::new();
    }
    let shown: String = text.chars().take(STDERR_EXCERPT).collect();
    format!(": {}", sanitize(&shown))
}

#[cfg(test)]
mod tests {
    #![allow(clippy::expect_used, clippy::unwrap_used, clippy::panic)]

    use super::*;

    const T: Duration = Duration::from_secs(30);

    #[test]
    fn curlrc_is_disabled_by_the_first_argument() {
        // `-q` only disables .curlrc when it is the FIRST argument.
        let a = args("https://node.example", T, false).unwrap();
        assert_eq!(a[0], "-q");
    }

    #[test]
    fn https_is_https_only_with_no_redirects_and_no_insecure() {
        let a = args("https://node.example/v2/x", T, false).unwrap();
        let pos = a.iter().position(|x| x == "--proto").unwrap();
        assert_eq!(a[pos + 1], "=https");
        for forbidden in [
            "-L",
            "--location",
            "-k",
            "--insecure",
            "--proto-redir",
            "--noproxy",
        ] {
            assert!(
                !a.iter().any(|x| x == forbidden),
                "{forbidden} must not be passed: {a:?}"
            );
        }
        // The URL is the value of --url, and it is the last thing on the line.
        assert_eq!(&a[a.len() - 2..], ["--url", "https://node.example/v2/x"]);
    }

    #[test]
    fn loopback_http_is_http_without_proxy() {
        let a = args("http://127.0.0.1:4001", T, false).unwrap();
        let pos = a.iter().position(|x| x == "--proto").unwrap();
        assert_eq!(&a[pos + 1..pos + 4], ["=http", "--noproxy", "*"]);
    }

    #[test]
    fn non_loopback_http_is_refused_before_curl_runs() {
        assert!(args("http://testnet-api.algonode.cloud", T, false).is_err());
        assert!(args("-K/etc/passwd", T, false).is_err());
    }

    #[test]
    fn post_streams_the_body_as_text_plain() {
        let a = args("https://node.example/v2/teal/compile", T, true).unwrap();
        let joined = a.join(" ");
        assert!(
            joined.contains("--header Content-Type: text/plain"),
            "{joined}"
        );
        assert!(joined.contains("--header Expect:"), "{joined}");
        assert!(joined.contains("--data-binary @-"), "{joined}");
        let get = args("https://node.example/v2/teal/compile", T, false).unwrap();
        assert!(
            !get.iter().any(|x| x == "--data-binary"),
            "a GET must carry no body"
        );
    }

    #[test]
    fn timeout_is_whole_seconds_and_never_zero() {
        let a = args("https://n.example", Duration::from_millis(10), false).unwrap();
        let pos = a.iter().position(|x| x == "--max-time").unwrap();
        assert_eq!(a[pos + 1], "1");
    }

    #[test]
    fn status_is_split_from_the_end_of_stdout() {
        let r = parse_output(b"{\"result\":\"DIEBQw==\"}200".to_vec()).unwrap();
        assert_eq!(r.status, 200);
        assert_eq!(r.body, b"{\"result\":\"DIEBQw==\"}");
        // A body that itself ends in digits is still split at the LAST three bytes.
        let r = parse_output(b"123404".to_vec()).unwrap();
        assert_eq!((r.status, r.body.as_slice()), (404, &b"123"[..]));
        let r = parse_output(b"200".to_vec()).unwrap();
        assert_eq!((r.status, r.body.len()), (200, 0));
    }

    #[test]
    fn missing_or_junk_status_is_an_error_not_a_response() {
        assert!(parse_output(Vec::new()).is_err());
        assert!(parse_output(b"20".to_vec()).is_err());
        assert!(parse_output(b"{}abc".to_vec()).is_err());
        assert!(
            parse_output(b"{}000".to_vec()).is_err(),
            "000 means curl got no response"
        );
        assert!(parse_output(b"{}999".to_vec()).is_err());
    }
}
