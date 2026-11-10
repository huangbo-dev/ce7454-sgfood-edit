"""Offline NEW roster issuance only. Never alters or installs an application roster."""
import argparse, hashlib, json, math, os, pathlib, re, secrets, stat, time

def no_links(path):
    for p in (path, *path.parents):
        if p.is_symlink():
            raise ValueError('Symlinks refused')

def require_posix():
    if os.name != 'posix':
        raise ValueError('Run only on an approved POSIX host; Windows ACL protection is not implemented')

def validate(plan, now):
    if not isinstance(plan, list) or not 1 <= len(plan) <= 100:
        raise ValueError('Plan must contain 1 to 100 reviewers')
    seen, emails = set(), set()
    for row in plan:
        if not isinstance(row, dict) or set(row) != {'reviewer_id', 'email', 'expires_at'}:
            raise ValueError('Invalid plan fields')
        rid, expiry = row['reviewer_id'], row['expires_at']
        if not isinstance(rid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,64}', rid):
            raise ValueError('Invalid reviewer ID')
        if rid.casefold() in seen:
            raise ValueError('Duplicate reviewer ID')
        seen.add(rid.casefold())
        email = row['email']
        if not isinstance(email, str) or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9._-]{0,62}[A-Za-z0-9])?@e\.ntu\.edu\.sg', email, re.IGNORECASE) or '..' in email:
            raise ValueError('Invalid approved-domain email')
        if email.casefold() in emails:
            raise ValueError('Duplicate email')
        emails.add(email.casefold())
        if type(expiry) not in (int, float) or not math.isfinite(expiry) or not now < expiry <= now + 30 * 86400:
            raise ValueError('Expiry must be in the next 30 days')

def prepare(plan, now, token_factory=None):
    validate(plan, now)
    token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
    roster, owner_mapping, hashes = [], [], set()
    for row in plan:
        code = token_factory()
        if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', code):
            raise ValueError('Invalid generated token')
        digest = hashlib.sha256(code.encode('ascii')).hexdigest()
        if digest in hashes:
            raise ValueError('Duplicate generated token')
        hashes.add(digest)
        roster.append({'reviewer_id': row['reviewer_id'], 'expires_at': row['expires_at'], 'code_sha256': digest, 'revoked': False})
        owner_mapping.append({**row, 'access_code': code})
    return roster, owner_mapping

def exclusive_write(path, payload):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(payload, f, indent=2, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())

def check_parent_permissions(parent):
    if stat.S_IMODE(parent.stat().st_mode) & 0o022:
        raise ValueError('Parent directory must not be group/world writable')

def issue(plan, output, now=None, token_factory=None):
    require_posix()
    output = pathlib.Path(output).absolute()
    no_links(output)
    if output.exists() or not output.parent.is_dir():
        raise ValueError('Output must be a new directory under an existing parent')
    # Refuse a parent writable by other users; do not change existing permissions.
    check_parent_permissions(output.parent)
    roster, owner_mapping = prepare(plan, time.time() if now is None else now, token_factory)
    output.mkdir(mode=0o700)
    # No cleanup on failure: never silently delete potentially generated credentials.
    # An incomplete directory is explicitly not suitable for installation.
    exclusive_write(output / 'owner_credentials.json', owner_mapping)
    exclusive_write(output / 'credentials.json', roster)
    exclusive_write(output / 'COMPLETE.json', {'reviewer_count': len(roster), 'status': 'complete', 'installed': False, 'distributed': False})
    return len(roster)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--approved-plan', type=pathlib.Path, required=True)
    p.add_argument('--new-output-directory', type=pathlib.Path, required=True)
    p.add_argument('--confirm-specific-issuance-approved', action='store_true', required=True)
    args = p.parse_args()
    try:
        require_posix(); no_links(args.approved_plan.absolute())
        if args.approved_plan.stat().st_size > 65536:
            raise ValueError('Plan too large')
        plan = json.loads(args.approved_plan.read_text(encoding='utf-8'))
        issue(plan, args.new_output_directory)
    except Exception:
        # Never print input, output data, exception content, or credentials.
        raise SystemExit('Issuance failed. Any partial output is unapproved and must not be installed; inspect securely.')
    print('Issuance complete. Restricted files created; no credentials printed, installed, or distributed.')

if __name__ == '__main__':
    main()
