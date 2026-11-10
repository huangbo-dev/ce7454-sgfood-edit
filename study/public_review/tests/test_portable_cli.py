"""CLI-only checks: no operational data, codes, listeners or staging writes."""
import argparse
import contextlib
import importlib.util
import io
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]

def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

server = load('portable_server', 'backend/server.py')
staging = load('portable_staging', 'stage_spark.py')

class PortableCLITests(unittest.TestCase):
    def test_explicit_https_origin_accepts_host_and_optional_port(self):
        for value in ('https://review.example', 'https://review.example:10443'):
            self.assertEqual(server.public_origin(value), value)

    def test_insecure_or_non_origin_values_rejected(self):
        for value in ('http://127.0.0.1:8792', 'http://review.example', 'https://',
                      'https://review.example/', 'https://review.example/path',
                      'https://review.example?x=1', 'https://review.example#x',
                      'https://user@review.example', 'https://user:password@review.example',
                      'https://review.example:invalid', 'https://review.example:70000',
                      'https://bad host.example'):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                server.public_origin(value)

    def test_server_missing_configuration_never_initializes_app(self):
        with mock.patch.object(server, 'App') as app, contextlib.redirect_stderr(io.StringIO()):
            for args in ([], ['--root', 'synthetic-root'], ['--origin', 'https://review.example']):
                with self.assertRaises(SystemExit) as error:
                    server.main(args)
                self.assertEqual(error.exception.code, 2)
            app.assert_not_called()

    def test_server_invalid_origin_never_initializes_app(self):
        with mock.patch.object(server, 'App') as app, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                server.main(['--root', 'synthetic-root', '--origin', 'http://review.example'])
            self.assertEqual(error.exception.code, 2)
            app.assert_not_called()

    def test_staging_requires_all_explicit_paths(self):
        with mock.patch.object(staging, 'stage') as stage, contextlib.redirect_stderr(io.StringIO()):
            for args in ([], ['--bundle', 'bundle'], ['--bundle', 'bundle', '--source', 'media']):
                with self.assertRaises(SystemExit) as error:
                    staging.main(args)
                self.assertEqual(error.exception.code, 2)
            stage.assert_not_called()

    def test_staging_forwards_only_explicit_paths(self):
        with mock.patch.object(staging, 'stage') as stage:
            staging.main(['--bundle', 'synthetic-bundle', '--source', 'synthetic-media', '--dest', 'synthetic-dest'])
            stage.assert_called_once_with(Path('synthetic-bundle'), Path('synthetic-media'), Path('synthetic-dest'))

if __name__ == '__main__':
    unittest.main()
