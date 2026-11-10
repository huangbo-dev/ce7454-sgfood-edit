# Code-only categorical author-review portal

Portable source for a separately prepared private review candidate. Publishing
this directory does not deploy a service, expose images, issue reviewer access,
or collect ratings. Follow the repository's `CLAUDE.md`: annotations are by
project authors only. Outside-team collection requires the applicable ethics
approval before collection. This is not an externally recruited user study.

## Scope and evidence limits

The candidate uses three Yes/No/Unsure questions per output: change achieved,
other food preserved, and plausibility. It is a new categorical protocol, not a
reinterpretation of the older numeric endpoint or its analysis exports. A
separate protocol and roster/exposure freeze is needed before real collection.
Do not feed these categorical responses into the older numeric analysis.

The privately prepared candidate covers 34 Round 1 pairs, 20 source photos and
7 identical pairs; no Round 2 routing is included. No real human ratings or
independent evaluator results are established by this publication. Existing
26/34 best-of-four and 28/34 retry acceptance counts are from the same checker
used for selection, not human validation or independent held-out confirmation.

Only backend/frontend source, an offline staging helper, synthetic tests and
this documentation are included. Cohort manifests, private mappings, images,
source/evidence locks, credentials, rosters, responses, databases, archives and
model weights are excluded. The local `.gitignore` is a code-only allowlist.
Tests create invented data and temporary codes in disposable directories only.

## Provenance and portable differences

The reviewed source archive has SHA-256
`5644693f140d31f2d11b790b3550490107d74ce053da2512f0052d67e0aecb0d`.
That private archive and its independently staged runtime remain immutable.
Its older README predates the later synthetic browser checks described below.

The six frontend, issuance and original test files preserve their source bytes.
Scoped Git attributes retain the audited CRLF bytes and recognize CRLF endings
for whitespace checks; no global Git setting is changed.
Two repository copies differ only in portable CLI configuration:

- `backend/server.py` requires an explicit HTTPS `--origin`, validated as an
  origin without a path, query, fragment or credentials. There is no published
  host allowlist or private deployment hostname. The listener remains loopback
  only, on `127.0.0.1:8792`.
- `stage_spark.py` requires explicit `--bundle`, `--source` (media directory) and
  `--dest` arguments instead of personal machine paths. The staging function is
  unchanged and never starts a server or issues access.

These sanitized CLI copies are not claimed to match the deployed/staged bytes.
The extra CLI tests are repository-only. Existing runtime code was not changed.

## Security and operational boundary

The standard-library server exposes only `/`, `/app.js` and `/style.css`
without authentication. Protected JSON POST routes require an exact configured
Host/Origin and in-memory bearer authorization. Cookies are not used for
sessions, fetch omits credentials, and tokens do not enter URLs or browser
storage. Sessions expire within 15 minutes, and roster revocation/expiry is
checked on each protected request. Logout clears the tab's state and images.

Credentials are hashed, responses are append-only, exports are reviewer-scoped,
and submissions enforce idempotency and monotonic revisions. Prior familiarity
is required. A media-request audit records requests, not proof of human viewing.
Numeric answers are rejected; Unsure remains an explicit response. Resource
limits are intended for a small pilot, not enterprise denial-of-service defense.

Runtime data, roster and database must be kept in an approved private directory
outside this checkout. POSIX runtime checks require private directory mode 0700
and credential/database file mode 0600. Windows ACL isolation has not been
validated. Issuance is a separately authorized operational action. The legacy
single-reviewer `backend/issue_credential.py` helper requires an explicit
approval flag, refuses an existing roster, and prints the new code once. Never
retain that output in shared logs or Git. The multi-reviewer helper below does
not print credentials.

Deployment, roster approval and secure code distribution are separately
authorized operational actions. No proxy, firewall, service, host credentials
or security settings were changed by this code publication. This review is not
a security certification. The later operational verification is recorded below.

## Running software checks

Use Python 3.10+ and Node.js. The portal tests use only the Python standard
library, temporary synthetic data and ephemeral loopback HTTP listeners:

```sh
cd study/public_review
python3 -B -m unittest discover -s tests -v
node --check frontend/app.js
```

On macOS, run the Python command with `TMPDIR=/private/tmp` so disposable
staging paths have no symlink ancestors. The staging helper deliberately rejects
symlinked parents, including the usual `/var` alias.

The code-only checkout is intentionally not a runnable study package. The
staging helper requires a separately authorized private bundle containing its
matching data lock, manifests and evidence directory, plus approved media.
It refuses destination collisions, symlinks and mismatched media hashes.
Do not reconstruct private cohort data from repository documentation.

## Verification record, 10 November 2026

Before code publication, the immutable private Spark stage passed 13 synthetic
server/staging tests, the JavaScript syntax check, 10 code hashes and 83 data
hashes. Separate Windows synthetic browser checks passed login, save, logout
and re-login on desktop/mobile layouts. These checks did not collect human
ratings. At that stage, the public TLS reverse-proxy check was still pending.
A subsequent, separately authorized operational deployment verified public TLS
access and login with HTTP 200, and rejection of anonymous protected requests
with HTTP 401. This does not establish byte identity with the portable CLI
copies or constitute new human evaluation. No deployment hostname, private
owner-file location or actual reviewer credential metadata is published here.

The exact six-file research overlay was also applied to isolated GPU04 and
Spark copies, each passing 24 author-analysis and 5 sync-preflight tests. Its
historical `HOST_SYNC_20261110.md` and `REVISION_VALIDATION_20261110.json` record
the earlier Windows-only preparation state, before these later host checks
and repository publication. They are preserved unchanged as historical receipts.

The portable repository passed 31 core, 24 author-analysis, 16 supplemental
and 19 portal tests (13 original plus 6 CLI checks) on macOS with Python 3.13.5.
The delivery bundle's 5 read-only sync-preflight tests also passed. Four
supplemental pixel tests were not run because NumPy/Pillow are unavailable in
that interpreter; unittest reports that as one skipped test class. JavaScript
syntax (Node.js 26.3.0), changed-Python AST parsing and Git whitespace checks
passed. The staging test used a canonical temporary path on macOS; its symlink
rejection was not relaxed. No GPU/model inference or production credentials
were used. No GitHub Actions workflows are configured in the repository.


## Offline multi-reviewer issuance helper

`issue_reviewers.py` prepares a new, email-mapped roster for specifically
approved project authors. It performs no networking, installation, distribution
or modification of an existing application roster. Publishing or testing this
helper does not authorize issuing operational credentials.

The helper requires an approved plan, an explicit new output directory and the
`--confirm-specific-issuance-approved` flag. Reviewer IDs and institutional
email addresses must be unique; only the approved institutional email domain
is accepted, and expiry must be within the next 30 days. It runs on POSIX only,
rejects symlinks and group/world-writable parents, and refuses an existing
output directory. It creates a new mode-0700 directory and mode-0600 files.
The installable roster contains hashes and reviewer IDs, not emails or raw
codes. The separate owner-only mapping contains the email/code association and
must stay private. No credentials are printed. Partial output is explicitly
unapproved for installation and is not silently deleted.

Only the reviewed source and its nine synthetic tests are included. No actual
plan, email list, owner mapping, operational codes or roster is included or read
by these tests. Test addresses and deterministic codes are invented fixtures.

Source SHA-256:
`967df4762460f184776788eab0e0e8af61741586c4c16ccbe881b078d2d0771c`.
Synthetic test SHA-256:
`8cb4a8c2426bb3eb1359690209ea4505bdd8cd33596609f921093ca051350c63`.
Both files preserve the reviewed source bytes unchanged.

After this code-only addition, all 28 portal tests passed on macOS/Python 3.13.5,
including the nine issuance tests. An additional unmocked POSIX smoke check
verified the new directory/file permissions, hash-only roster, silent output and
overwrite refusal using deterministic fake codes in a disposable directory.
JavaScript syntax, new-Python parsing and staged whitespace/privacy checks also
passed. Neither the immutable operational package nor actual issuance files were
read or changed for this addition.
