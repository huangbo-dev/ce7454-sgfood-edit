"""Synthetic tests only: invented items, hashes and answers. No real responses."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analyze as A  # noqa: E402

VERSION = 'ce7454-public-categorical-v1-synthetic'
YES = {q: 'Yes' for q in A.QUESTIONS}


def answers(**changes):
    row = dict(YES, note='')
    for index, value in changes.items():
        row[A.QUESTIONS[int(index[1:])]] = value
    return row


def package():
    """Four items on two photos; item i3 has identical outputs."""
    public = {'version': VERSION, 'questions': list(A.QUESTIONS), 'items': []}
    private = {'version': VERSION, 'items': {}}
    layout = [('i0', 'p0', 'T2', 'retry', False), ('i1', 'p0', 'T1-B', 'best_check', False),
              ('i2', 'p1', 'T2', 'retry', False), ('i3', 'p1', 'T1-B', 'best_check', True)]
    for item, photo, task, side_a, identical in layout:
        side_b = 'best_check' if side_a == 'retry' else 'retry'
        public['items'].append({'id': item, 'section': 'Round 1', 'task_text': 't',
                                'original': 'o', 'A': 'a', 'B': 'b'})
        private['items'][item] = {
            'condition': 'tuned', 'task': task, 'photo_id': photo, 'A': side_a, 'B': side_b,
            'identical_outputs': identical,
            'selected': {'retry': {'sha256': f'{item}-same' if identical else f'{item}-retry'},
                         'best_check': {'sha256': f'{item}-same' if identical else f'{item}-best'}}}
    return public, private


def export(reviewer, ratings, familiarity='No'):
    events = [{'seq': 1, 'kind': 'familiarity', 'item_id': '', 'revision': 1,
               'payload': {'prior_familiarity': familiarity, 'note': ''}}]
    for seq, (item, revision, a, b) in enumerate(ratings, start=2):
        events.append({'seq': seq, 'kind': 'rating', 'item_id': item, 'revision': revision,
                       'payload': {'A': a, 'B': b}})
    return {'version': VERSION, 'reviewer_id': reviewer, 'events': events}


def reviewers_from(public, exports):
    with tempfile.TemporaryDirectory() as folder:
        paths = []
        for index, body in enumerate(exports):
            path = Path(folder) / f'{index}.json'
            path.write_text(json.dumps(body))
            paths.append(path)
        return A.load_exports(paths, public)


class JointRule(unittest.TestCase):
    def test_any_no_fails_all_yes_passes_unsure_unknown(self):
        self.assertTrue(A.joint(answers()))
        self.assertFalse(A.joint(answers(q1='No')))
        self.assertIsNone(A.joint(answers(q2='Unsure')))
        self.assertFalse(A.joint(answers(q0='Unsure', q2='No')))


class Analysis(unittest.TestCase):
    def setUp(self):
        self.public, self.private = package()
        A.validate_design(self.public, self.private)
        # Retry succeeds everywhere; best_check fails on i0 and i2 for both raters.
        full = [('i0', 1, answers(), answers(q0='No')), ('i1', 1, answers(), answers()),
                ('i2', 1, answers(), answers(q2='No')), ('i3', 1, answers(), answers())]
        self.exports = [export('alice', full), export('bob', full)]
        self.reviewers = reviewers_from(self.public, self.exports)

    def test_method_mapping_and_difference(self):
        report = A.analyze(self.public, self.private, self.reviewers)
        block = report['estimates'][A.JOINT]['all_cases']
        self.assertEqual(block['mean_rate'], {'retry': 1.0, 'best_check': 0.5})
        self.assertEqual(block['mean_paired_difference_retry_minus_best_check'], 0.5)
        self.assertEqual((block['cases_retry_higher'], block['cases_equal']), (2, 2))
        low, high = block['interval_95_photo_cluster']
        self.assertTrue(0 <= low <= 0.5 <= high <= 1)
        self.assertEqual(report['estimates'][A.JOINT]['excluding_identical_outputs']['cases'], 3)
        self.assertEqual(set(report['estimates'][A.JOINT]['by_task']), {'T1-B', 'T2'})

    def test_bootstrap_is_deterministic(self):
        first = A.analyze(self.public, self.private, self.reviewers)
        second = A.analyze(self.public, self.private, self.reviewers)
        self.assertEqual(first, second)

    def test_perfect_agreement_and_identical_consistency(self):
        report = A.analyze(self.public, self.private, self.reviewers)
        for question in A.QUESTIONS:
            self.assertEqual(report['agreement'][question]['mean_pairwise_agreement'], 1.0)
        self.assertEqual(report['agreement'][A.QUESTIONS[0]]['krippendorff_alpha_nominal'], 1.0)
        self.assertEqual(report['identical_pair_consistency']['share'], 1.0)

    def test_latest_revision_wins(self):
        revised = export('carol', [('i0', 1, answers(q0='No'), answers()),
                                   ('i0', 2, answers(), answers(q0='No'))])
        reviewers = reviewers_from(self.public, [revised])
        row = A.case_rows(self.public, self.private, reviewers, A.JOINT)[0]
        self.assertEqual(row['means'], {'retry': 1.0, 'best_check': 0.0})

    def test_unsure_stays_unknown_and_sets_bounds(self):
        unsure = export('dave', [('i0', 1, answers(q1='Unsure'), answers())])
        reviewers = reviewers_from(self.public, [unsure])
        rows = A.case_rows(self.public, self.private, reviewers, A.JOINT)
        self.assertIsNone(rows[0]['means']['retry'])
        self.assertIsNone(rows[0]['difference'])
        self.assertEqual(A.bounds(rows)['retry'], {'known_ratings': 0, 'unknown_ratings': 1,
                                                   'lower': 0.0, 'upper': 1.0})

    def test_coverage_only_reveals_no_method_outcomes(self):
        report = A.analyze(self.public, self.private, self.reviewers, coverage_only=True)
        self.assertEqual(report['status'], 'coverage_only')
        self.assertNotIn('estimates', report)
        self.assertNotIn('retry', json.dumps(report))
        self.assertNotIn('alice', json.dumps(report))
        self.assertEqual(report['coverage']['items_with_all_reviewers'], 4)

    def test_checker_join_pools_identical_outputs(self):
        flags = A.checker_flags({'rows': [
            {'output_sha256': 'i0-retry', 'checker_pass': True},
            {'output_sha256': 'i0-best', 'checker_pass': True},
            {'output_sha256': 'i2-best', 'checker_pass': False},
            {'output_sha256': 'i3-same', 'checker_pass': True}]})
        joined = A.checker_join(self.public, self.private, self.reviewers, flags)
        self.assertEqual(joined['checker_pass']['unique_outputs_with_known_author_ratings'], 3)
        self.assertEqual(joined['checker_pass']['outputs_no_author_success'], 1)
        self.assertEqual(joined['checker_fail']['mean_author_joint_success'], 0.0)
        self.assertEqual(joined['outputs_without_checker_verdict'], 3)

    def test_rejections(self):
        wrong = export('eve', [])
        wrong['version'] = 'other'
        with self.assertRaises(ValueError):
            reviewers_from(self.public, [wrong])
        with self.assertRaises(ValueError):
            reviewers_from(self.public, [self.exports[0], self.exports[0]])
        bad = export('frank', [('i0', 1, dict(answers(), **{A.QUESTIONS[0]: 'Maybe'}), answers())])
        with self.assertRaises(ValueError):
            reviewers_from(self.public, [bad])
        with self.assertRaises(ValueError):
            A.checker_flags([{'output_sha256': 'x', 'checker_pass': True},
                             {'output_sha256': 'x', 'checker_pass': False}])


class Alpha(unittest.TestCase):
    def test_disagreement_lowers_alpha(self):
        self.assertEqual(A.krippendorff_nominal([['Yes', 'Yes'], ['No', 'No']]), 1.0)
        self.assertLess(A.krippendorff_nominal([['Yes', 'No'], ['No', 'Yes']]), 0)
        self.assertIsNone(A.krippendorff_nominal([['Yes']]))


if __name__ == '__main__':
    unittest.main()
