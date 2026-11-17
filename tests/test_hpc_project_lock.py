"""Exercise real shell processes against the project guard, without Slurm."""
from pathlib import Path
import json
import select
import subprocess
import tempfile
import shutil
import unittest


HELPER = Path(__file__).resolve().parents[1]/'hpc/project_lock.sh'


class ProjectLockTests(unittest.TestCase):
    def run_shell(self, project, script):
        return subprocess.run(['bash', '-c', 'source "$1"\n'+script, 'guard-test', str(HELPER), str(project)],
                              capture_output=True, text=True, timeout=10)

    def test_acquire_release_and_legacy_file_preservation(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            parent = project/'outputs/ojcs'
            parent.mkdir(parents=True)
            old = parent/'.campaign.lock'
            old.write_text('legacy file retained\n')
            result = self.run_shell(project, 'set -e\ngs_acquire_project_lock "$2"\ngs_release_project_lock')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((parent/'.campaign.guard').exists())
            self.assertEqual(old.read_text(), 'legacy file retained\n')

    def test_concurrent_owner_is_identified_and_cannot_be_released_by_contender(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            script = ('source "$1"\nexport SLURM_JOB_ID=111\ngs_acquire_project_lock "$2" || exit $?\n'
                      'trap gs_release_project_lock EXIT\nprintf "READY\\n"\nread -r finish\n')
            holder = subprocess.Popen(['bash', '-c', script, 'guard-holder', str(HELPER), str(project)],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                ready, _, _ = select.select([holder.stdout], [], [], 5)
                self.assertTrue(ready, 'Holder did not acquire the guard')
                self.assertEqual(holder.stdout.readline().strip(), 'READY')
                contender = self.run_shell(project, 'export SLURM_JOB_ID=222\ngs_acquire_project_lock "$2"')
                self.assertEqual(contender.returncode, 75, contender.stderr)
                self.assertIn('job_id=111', contender.stderr)
                self.assertTrue((project/'outputs/ojcs/.campaign.guard/owner').is_file())
                holder.communicate('finish\n', timeout=5)
                self.assertEqual(holder.returncode, 0)
                retry = self.run_shell(project, 'set -e\ngs_acquire_project_lock "$2"\ngs_release_project_lock')
                self.assertEqual(retry.returncode, 0, retry.stderr)
            finally:
                if holder.poll() is None:
                    holder.terminate()
                    holder.communicate(timeout=5)

    def test_existing_unknown_guard_is_not_reclaimed(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            guard = project/'outputs/ojcs/.campaign.guard'
            guard.mkdir(parents=True)
            result = self.run_shell(project, 'gs_acquire_project_lock "$2"')
            self.assertEqual(result.returncode, 75)
            self.assertIn('Owner metadata is unavailable', result.stderr)
            self.assertTrue(guard.is_dir())

    def test_filesystem_error_is_not_misreported_as_contention(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project/'outputs').write_text('not a directory')
            result = self.run_shell(project, 'gs_acquire_project_lock "$2"')
            self.assertEqual(result.returncode, 73)
            self.assertIn('cannot create project guard parent', result.stderr)
            self.assertNotIn('guard already exists', result.stderr)

    def test_changed_owner_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            result = self.run_shell(project, 'gs_acquire_project_lock "$2" || exit $?\n'
                                    'printf "token=different-owner\\n" > "$GS_PROJECT_LOCK_DIR/owner"\n'
                                    'gs_release_project_lock')
            self.assertEqual(result.returncode, 74)
            self.assertEqual((project/'outputs/ojcs/.campaign.guard/owner').read_text(), 'token=different-owner\n')

    def test_batch_startup_failure_releases_guard_and_records_real_phase(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            source = HELPER.parents[1]
            (project/'hpc').mkdir()
            for name in ['environment.sh', 'project_lock.sh']:
                shutil.copy2(source/'hpc'/name, project/'hpc'/name)
            batch = (source/'Batch').read_text().replace('/home/tariq.qayyum/hpc/GapSlice-OJCS', str(project))
            (project/'Batch').write_text(batch)
            # Exercise Batch itself, with a controlled module-load failure.
            # Run twice: neither failed startup may strand a project guard.
            for _ in range(2):
                result = subprocess.run(['bash', '-c', 'module() { return 19; }; export -f module; '
                                         'export SLURM_JOB_ID=111; bash "$1"', 'batch-test', str(project/'Batch')],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 19, result.stderr)
                status = json.loads((project/'outputs/job-111/status.json').read_text())
                self.assertEqual(status, dict(job_id='111', exit_code=19, phase='modules'))
                self.assertFalse((project/'outputs/ojcs/.campaign.guard').exists())


if __name__ == '__main__':
    unittest.main()
