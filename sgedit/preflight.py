"""Read-only technical checks for the existing test_split manifest, never a launch gate by itself."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(manifest, work, development_hashes=None):
    errors = []
    manifest, work = Path(manifest), Path(work).resolve()
    if not manifest.is_file():
        return ['Missing held-out manifest: ' + str(manifest)]
    try:
        data = json.loads(manifest.read_text())
    except (ValueError, OSError) as exc:
        return ['Unreadable manifest: ' + str(exc)]
    if not isinstance(data, dict):
        return ['Manifest must be an object']
    photos, jobs = data.get('photos'), data.get('jobs')
    if not isinstance(photos, list) or not photos or not isinstance(jobs, list) or not jobs:
        return ['Nonempty photos and jobs arrays are required']
    if data.get('n_photos') != len(photos):
        errors.append('n_photos does not match photos')
    if not data.get('frozen_at'):
        errors.append('Missing frozen_at')
    if development_hashes is None:
        errors.append('Development source-hash inventory not supplied')
    elif not isinstance(development_hashes, list) or not development_hashes:
        errors.append('Development source-hash inventory must be a nonempty JSON array')
        development_hashes = []
    hashes = development_hashes or []
    valid_hashes = [h for h in hashes if isinstance(h, str) and len(h) == 64 and all(c in '0123456789abcdef' for c in h)]
    if len(valid_hashes) != len(hashes):
        errors.append('Invalid development source hash')
    dev = set(valid_hashes)
    seen_ids, seen_sources, expected = set(), set(), set()
    indexed = {}
    for p in photos:
        if not isinstance(p, dict):
            errors.append('Invalid photo record')
            continue
        iid, source = p.get('image_id'), p.get('source')
        if not isinstance(iid, str) or len(iid) != 12 or any(c not in '0123456789abcdef' for c in iid):
            errors.append('Invalid image_id')
            continue
        if iid in seen_ids:
            errors.append('Duplicate photo id: ' + iid)
        seen_ids.add(iid)
        indexed[iid] = p
        for field in ('file', 'dish', 'mask_source_sha256'):
            if not isinstance(p.get(field), str) or not p[field].strip():
                errors.append('Missing photo provenance ' + field + ': ' + iid)
        mh = p.get('mask_source_sha256', '')
        if not isinstance(mh, str) or len(mh) != 64 or any(c not in '0123456789abcdef' for c in mh):
            errors.append('Invalid mask source hash: ' + iid)
        h = p.get('source_sha256')
        if not isinstance(h, str) or len(h) != 64 or any(c not in '0123456789abcdef' for c in h):
            errors.append('Invalid source hash: ' + iid)
            continue
        elif h[:12] != iid:
            errors.append('Photo id/source hash mismatch: ' + iid)
        if h in seen_sources:
            errors.append('Duplicate source photo: ' + iid)
        seen_sources.add(h)
        if h in dev:
            errors.append('Development/test source overlap: ' + iid)
        if source not in ('rice', 'noodles'):
            errors.append('Invalid staple source: ' + iid)
            continue
        expected.update((iid, task) for task in (['T1-B', 'T2'] if source == 'rice' else ['T1-B']))
        for filename, field in [('image.png', 'image_sha256'), ('mask.png', 'mask_sha256')]:
            path = work / 'data' / 'test' / iid / filename
            if not path.is_file():
                errors.append('Missing processed file: ' + str(path))
            elif sha(path) != p.get(field):
                errors.append('Processed hash mismatch: ' + str(path))
    actual = []
    for j in jobs:
        if not isinstance(j, dict):
            errors.append('Invalid job record')
            continue
        iid, task = j.get('image_id'), j.get('task')
        if not isinstance(iid, str) or not isinstance(task, str):
            errors.append('Invalid job identifier')
            continue
        actual.append((iid, task))
        p = indexed.get(iid, {})
        if j.get('source') != p.get('source'):
            errors.append('Job/photo staple mismatch: ' + iid)
        for field, filename in [('original_path', 'image.png'), ('mask_path', 'mask.png')]:
            expected_path = 'data/test/' + iid + '/' + filename
            if j.get(field) != expected_path:
                errors.append('Unexpected job path: ' + str(j.get(field)))
    if len(actual) != len(set(actual)):
        errors.append('Duplicate edit jobs')
    if set(actual) != expected:
        errors.append('Job set does not match rice/noodle task coverage')
    return errors


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', type=Path, required=True)
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--development-hashes', type=Path)
    a = ap.parse_args()
    try:
        hashes = json.loads(a.development_hashes.read_text()) if a.development_hashes else None
        errors = check(a.manifest, a.work, hashes)
    except (OSError, ValueError, TypeError) as exc:
        errors = ['Invalid input: ' + str(exc)]
    print(json.dumps({'technical_checks_pass': not errors, 'launch_authorized': False,
                      'errors': errors, 'note': 'Human eligibility, mask review, study approval and locked protocol still required.'}, indent=2))
    return 2 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
