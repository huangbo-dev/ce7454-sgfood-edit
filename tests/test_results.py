"""Offline result-contract and Runner.run regression tests; no GPU or API calls."""
import copy
import importlib.util
from dataclasses import dataclass
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from sgedit.results import summarize_result


def candidate(tag, score, passed):
    return {'tag': tag, 'score': score, 'pass': passed,
            'failure': None if passed else 'edit'}


class ResultContractTests(unittest.TestCase):
    def test_selected_failure_is_not_last_attempt_success(self):
        first = candidate('seed0', 1.9, False)
        last = candidate('retry1', 1.8, True)
        result = summarize_result('job', 4, [first], [first, last])
        self.assertEqual(result['retry'], 'seed0')
        self.assertFalse(result['retry_passed'])
        self.assertTrue(result['retry_last_passed'])
        self.assertEqual(result['result_schema_version'], 2)

    def test_successful_retry_selected(self):
        first = candidate('seed0', 1.0, False)
        last = candidate('retry1', 1.8, True)
        result = summarize_result('job', 2, [first], [first, last])
        self.assertEqual(result['retry'], 'retry1')
        self.assertTrue(result['retry_passed'])
        self.assertTrue(result['retry_last_passed'])

    def test_all_fail_preserves_highest_score_selection(self):
        first = candidate('seed0', 1.0, False)
        best = candidate('retry1', 1.4, False)
        last = candidate('retry2', 1.2, False)
        result = summarize_result('job', 3, [first], [first, best, last])
        self.assertEqual(result['retry'], 'retry1')
        self.assertFalse(result['retry_passed'])
        self.assertFalse(result['retry_last_passed'])

    def test_first_attempt_passes_without_retry(self):
        first = candidate('seed0', 1.8, True)
        result = summarize_result('job', 1, [first], [first])
        self.assertEqual(result['retry_steps'], ['seed0'])
        self.assertTrue(result['retry_passed'])
        self.assertTrue(result['retry_last_passed'])

    def test_ties_keep_first_candidate_without_pass_preference(self):
        first = candidate('seed0', 1.8, False)
        last = candidate('retry1', 1.8, True)
        result = summarize_result('job', 2, [first], [first, last])
        self.assertEqual(result['retry'], 'seed0')
        self.assertFalse(result['retry_passed'])

    def test_existing_fields_and_inputs_are_preserved(self):
        first = candidate('seed0', 1.0, False)
        other = candidate('seed1', 1.9, True)
        retry = candidate('retry1', 1.8, True)
        seeds, tried = [first, other], [first, retry]
        before = copy.deepcopy((seeds, tried))
        result = summarize_result('job', 2, seeds, tried)
        expected = {'key': 'job', 'K': 2, 'single': 'seed0',
                    'best_check': 'seed1', 'retry': 'retry1',
                    'seed_tags': ['seed0', 'seed1'],
                    'retry_steps': ['seed0', 'retry1']}
        self.assertEqual({k: result[k] for k in expected}, expected)
        self.assertEqual((seeds, tried), before)


@dataclass
class FakeEditSpec:
    prompt: str
    negative_prompt: str | None
    seed: int
    steps: int
    guidance: float
    mode: str


def offline_loop():
    """Load the real loop with only its heavyweight/config imports stubbed."""
    editor = types.ModuleType('sgedit.editor')
    editor.EditSpec = FakeEditSpec
    prompts = types.ModuleType('sgedit.prompts')
    prompts.PROMPT_SETS = {}
    prompts.ladder = lambda *args: [('base', None), ('next', None)]
    source = Path(__file__).resolve().parents[1] / 'sgedit' / 'loop.py'
    spec = importlib.util.spec_from_file_location('sgedit._offline_loop', source)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'sgedit.editor': editor, 'sgedit.prompts': prompts}):
        spec.loader.exec_module(module)
    return module


class RunnerReportingTests(unittest.TestCase):
    def test_real_runner_stops_on_pass_but_reports_selected_failure(self):
        loop = offline_loop()
        rows = {'seed0': candidate('seed0', 1.9, False),
                'seed1': candidate('seed1', 1.7, True),
                'seed2': candidate('seed2', 1.6, False),
                'retry1': candidate('retry1', 1.8, True)}
        seen = []
        runner = loop.Runner(None, None, 'unused')
        def fake_candidate(job, spec, tag):
            seen.append((tag, spec.prompt, spec.seed))
            return rows[tag]
        runner.candidate = fake_candidate
        result = runner.run({'key': 'job', 'task': 'T2', 'source': 'rice'}, K=3)
        self.assertEqual([x[0] for x in seen], ['seed0', 'seed1', 'seed2', 'retry1'])
        self.assertEqual(seen[-1][1:], ('next', loop.POLICY['seeds'][1]))
        self.assertEqual(result['retry_steps'], ['seed0', 'retry1'])
        self.assertEqual(result['retry'], 'seed0')
        self.assertFalse(result['retry_passed'])
        self.assertTrue(result['retry_last_passed'])

    def test_real_runner_first_pass_uses_existing_seed_budget(self):
        loop = offline_loop()
        runner = loop.Runner(None, None, 'unused')
        seen = []
        def fake_candidate(job, spec, tag):
            seen.append(tag)
            return candidate(tag, 1.8, True)
        runner.candidate = fake_candidate
        result = runner.run({'key': 'job', 'task': 'T2', 'source': 'rice'}, K=2)
        self.assertEqual(seen, ['seed0', 'seed1'])
        self.assertEqual(result['retry_steps'], ['seed0'])
        self.assertEqual(result['retry'], 'seed0')
        self.assertTrue(result['retry_passed'])


if __name__ == '__main__':
    unittest.main()
