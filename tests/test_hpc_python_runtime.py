"""Exercise interpreter selection, isolation and failure paths without downloads.

Real managed-Python installation is a separate local integration check. The
unattended Slurm suite must never download another runtime in a test fixture.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


HPC = Path(__file__).resolve().parents[1]/'hpc'


class PythonRuntimeTests(unittest.TestCase):
    def command(self, project, *, old_candidates=False, force=False):
        bin_dir = project/'test-bin'
        bin_dir.mkdir(exist_ok=True)
        if old_candidates:
            for name in ['python3.13', 'python3.12', 'python3.11', 'python3', 'python']:
                p = bin_dir/name
                p.write_text('#!/bin/sh\nexit 1\n')
                p.chmod(0o700)
        else:
            p = bin_dir/'python3.13'
            if not p.exists():
                p.symlink_to(sys.executable)
        env = dict(os.environ, PATH=str(bin_dir)+':/usr/bin:/bin',
                   GS_OJCS_MANAGED_PYTHON='1' if force else '0')
        script = ('set -e\nexport GS_OJCS_PROJECT="$2"\nsource "$1/environment.sh"\n'
                  'source "$1/python_runtime.sh"\ngs_prepare_python_runtime "$2"\n')
        return subprocess.run(['bash', '-c', script, 'runtime-test', str(HPC), str(project)],
                              env=env, capture_output=True, text=True, timeout=45)

    def assert_project_python(self, project):
        result = subprocess.run([str(project/'.venv/bin/python'), '-c',
                                 'import json,sys; print(json.dumps([list(sys.version_info[:2]),sys.prefix]))'],
                                capture_output=True, text=True, check=True)
        version, prefix = json.loads(result.stdout)
        self.assertGreaterEqual(version, [3, 11])
        self.assertEqual(Path(prefix).resolve(), (project/'.venv').resolve())
        pip = subprocess.run([str(project/'.venv/bin/python'), '-m', 'pip', '--version'],
                             capture_output=True, text=True)
        self.assertEqual(pip.returncode, 0, pip.stderr)
        self.assertIn('pip ', pip.stdout)

    def test_compatible_interpreter_creates_and_reuses_isolated_venv(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            first = self.command(project)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assert_project_python(project)
            marker = project/'.venv/preserved'
            marker.write_text('keep')
            second = self.command(project, force=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn('Reusing project environment', second.stdout)
            self.assertEqual(marker.read_text(), 'keep')
            self.assertFalse((project/'.tools/uv-0.13.8').exists())

    def test_incompatible_environment_is_preserved_before_replacement(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            old = project/'.venv'
            (old/'bin').mkdir(parents=True)
            (old/'bin/python').write_text('#!/bin/sh\nexit 1\n')
            (old/'bin/python').chmod(0o700)
            (old/'original-marker').write_text('preserve original')
            result = self.command(project)
            self.assertEqual(result.returncode, 0, result.stderr)
            backups = list(project.glob('.venv.incompatible-*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual((backups[0]/'original-marker').read_text(), 'preserve original')
            self.assert_project_python(project)

    def test_old_interpreters_select_managed_runtime_and_propagate_download_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            uv = project/'.tools/uv-0.13.8/uv'
            uv.parent.mkdir(parents=True)
            uv.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$GS_OJCS_PROJECT/uv-calls"\n'
                          'printf "%s\\n" "$UV_PYTHON_INSTALL_DIR" "$UV_CACHE_DIR" > "$GS_OJCS_PROJECT/uv-paths"\n'
                          'if [ "$1" = --version ]; then echo "uv 0.13.8"; exit 0; fi\nexit 47\n')
            uv.chmod(0o700)
            result = self.command(project, old_candidates=True)
            self.assertEqual(result.returncode, 47, result.stderr)
            self.assertIn('project-local CPython 3.13.9', result.stdout)
            self.assertEqual((project/'uv-calls').read_text().splitlines(), ['--version', 'python install 3.13.9'])
            self.assertEqual((project/'uv-paths').read_text().splitlines(),
                             [str(project/'.python'), str(project/'.cache/uv')])
            self.assertFalse((project/'.venv').exists())

    def test_venv_symlink_is_not_modified(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project, external = root/'project', root/'external'
            project.mkdir(); external.mkdir()
            (external/'marker').write_text('unchanged')
            (project/'.venv').symlink_to(external, target_is_directory=True)
            result = self.command(project)
            self.assertEqual(result.returncode, 2)
            self.assertIn('.venv is a symlink', result.stderr)
            self.assertEqual((external/'marker').read_text(), 'unchanged')

    def test_unverified_cached_installer_is_not_executed(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            installer = project/'.tools/installers/uv-0.13.8.sh'
            installer.parent.mkdir(parents=True)
            installer.write_text('#!/bin/sh\ntouch "$GS_OJCS_PROJECT/unsafe-marker"\n')
            result = self.command(project, force=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn('checksum mismatch', result.stderr)
            self.assertFalse((project/'unsafe-marker').exists())


if __name__ == '__main__':
    unittest.main()
