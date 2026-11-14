import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.dumps import Dumps

# Made-up dumps: none of this is anyone's real game.
TRACK_1 = b"\x01" * 4096
TRACK_2 = b"\x02" * 2352
CUE = 'FILE "Signal Lost (USA) (Track 1).bin" BINARY\n  TRACK 01 MODE2/2352\nFILE "Signal Lost (USA) (Track 2).bin" BINARY\n  TRACK 02 AUDIO\n'
SETTLED = {"settleSeconds": 60}


def made(path: Path, data: bytes | str, age: float = 600) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    then = time.time() - age
    os.utime(path, (then, then))
    return path


@pytest.fixture
def root(tmp_path) -> Path:
    (tmp_path / "staging").mkdir()
    (tmp_path / "dumps").mkdir()
    return tmp_path / "dumps"


@pytest.fixture
def client(monkeypatch, tmp_path, root):
    monkeypatch.setattr(main, "STAGING", str(tmp_path / "staging"))
    monkeypatch.setattr(main, "dumps", Dumps(str(root)))
    return TestClient(main.app)


def disc(folder: Path, tracks: int = 2, age: float = 600) -> None:
    made(folder / "Signal Lost (USA).cue", CUE, age)
    made(folder / "Signal Lost (USA) (Track 1).bin", TRACK_1, age)
    if tracks > 1:
        made(folder / "Signal Lost (USA) (Track 2).bin", TRACK_2, age)
    made(folder / "Signal Lost (USA).log", "redumper v2026 (made up)\nerrors: 0", age)
    made(folder / "Signal Lost (USA).scram", b"\x00" * 9000, age)


def listed(client, settings=SETTLED):
    return client.post("/v1/list", json={"settings": settings}).json()["candidates"]


def wait(client, job_id):
    for _ in range(200):
        status = client.get(f"/v1/fetch/{job_id}").json()
        if status["state"] not in ("queued", "running"):
            return status
        time.sleep(0.02)
    raise TimeoutError(status)


def test_a_finished_disc_is_offered_with_its_log_and_without_the_ripper_s_leftovers(client, root):
    disc(root / "ps1" / "Signal Lost (USA)")
    [candidate] = listed(client)
    assert candidate["name"] == "Signal Lost (USA)"
    assert candidate["source"] == "redumper: ps1/Signal Lost (USA)"
    assert candidate["format"] == "bin,cue"
    assert candidate["size"] == len(CUE) + len(TRACK_1) + len(TRACK_2)
    assert "errors: 0" in candidate["notes"]


def test_a_disc_is_offered_only_once_it_is_whole_and_left_alone(client, root):
    disc(root / "half", tracks=1)
    disc(root / "busy", age=5)
    assert listed(client) == []
    assert len(listed(client, {"settleSeconds": 0})) == 1  # whole, just written: only the half one stays out


def test_each_cartridge_in_a_dumper_s_folder_is_a_dump_of_its_own(client, root):
    made(root / "GB" / "Pixel Pond.gb", b"\x10" * 32768)
    made(root / "GB" / "Pixel Pond.txt", "Cartridge Reader (made up)\nCRC32: 12345678")
    made(root / "GB" / "Moss Maze.gb", b"\x20" * 32768)
    made(root / "GB" / "settings.cfg", "nothing")
    found = {c["name"]: c for c in listed(client)}
    assert set(found) == {"Pixel Pond", "Moss Maze"}
    assert found["Pixel Pond"]["source"] == "Cartridge Reader: GB/Pixel Pond.gb"
    assert "CRC32" in found["Pixel Pond"]["notes"]
    assert "notes" not in found["Moss Maze"]


def test_a_fetch_copies_the_image_and_logs_and_leaves_the_rest(client, root, tmp_path):
    disc(root / "Signal Lost (USA)")
    [candidate] = listed(client)
    body = {"settings": SETTLED, "jobId": "j", "candidate": candidate, "stagingDirectory": "downloads/j"}
    assert client.post("/v1/fetch", json=body).status_code == 202
    status = wait(client, "j")
    assert status["state"] == "completed"
    assert sorted(f["path"] for f in status["files"]) == [
        "Signal Lost (USA) (Track 1).bin", "Signal Lost (USA) (Track 2).bin", "Signal Lost (USA).cue", "Signal Lost (USA).log"]
    assert (root / "Signal Lost (USA)" / "Signal Lost (USA).cue").exists()  # kept, by default


def test_moved_dumps_can_take_the_leftovers_with_them(client, root, tmp_path):
    disc(root / "Signal Lost (USA)")
    [candidate] = listed(client)
    settings = {**SETTLED, "keepOriginals": False, "removeLeftovers": True}
    client.post("/v1/fetch", json={"settings": settings, "jobId": "m", "candidate": candidate, "stagingDirectory": "m"})
    assert wait(client, "m")["state"] == "completed"
    assert not (root / "Signal Lost (USA)").exists()
    assert (tmp_path / "staging" / "m" / "Signal Lost (USA) (Track 2).bin").read_bytes() == TRACK_2


def test_what_has_gone_fails_the_fetch_and_the_manifest_follows_the_contract(client, root, tmp_path, monkeypatch):
    gone = {"candidateId": '{"p":"nothing","s":1,"m":0}', "name": "gone", "source": "x"}
    client.post("/v1/fetch", json={"settings": {}, "jobId": "g", "candidate": gone, "stagingDirectory": "g"})
    assert "isn't a finished dump" in wait(client, "g")["error"]

    manifest = client.get("/v1/manifest").json()
    assert manifest["type"] == "retrieval" and set(manifest["capabilities"]) == {"list", "cancel"}
    monkeypatch.setattr(main, "dumps", Dumps(str(tmp_path / "missing")))
    assert client.post("/v1/health", json={"settings": {}}).json()["status"] == "unhealthy"
    assert client.post("/v1/list", json={"settings": {}}).status_code == 503
