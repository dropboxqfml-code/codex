import json
import subprocess
import sys


def command(*arguments):
    return subprocess.run(
        [sys.executable, "-m", "image_monitor", *arguments],
        capture_output=True,
        text=True,
        check=False,
    )


def test_demo_persists_queue_and_status_can_read_it_after_restart(tmp_path):
    path = tmp_path / "queue.sqlite3"
    result = command("queue-demo", "--db", str(path))
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["synthetic_only"] is True
    assert output["browser_started"] is False
    assert output["files_downloaded"] == 0
    assert path.is_file()
    repeated = command("queue-status", "--db", str(path))
    assert repeated.returncode == 0, repeated.stderr
    assert json.loads(repeated.stdout) == output["summary"]


def test_demo_refuses_to_modify_existing_file(tmp_path):
    path = tmp_path / "do-not-overwrite.sqlite3"
    path.write_bytes(b"existing user file")
    result = command("queue-demo", "--db", str(path))
    assert result.returncode == 2
    assert path.read_bytes() == b"existing user file"
    assert "Traceback" not in result.stderr


def test_status_does_not_create_a_missing_database(tmp_path):
    path = tmp_path / "missing.sqlite3"
    result = command("queue-status", "--db", str(path))
    assert result.returncode == 2
    assert not path.exists()
    assert "Traceback" not in result.stderr
