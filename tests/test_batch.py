from controller import batch
from controller.storage import read_json
from test_controller import config


def test_batch_alternates_conditions_and_preserves_paired_protocol(tmp_path, monkeypatch):
    seen = []
    class RecordingEngine:
        def __init__(self, root, backend, evaluator):
            self.manifest = read_json(root / "manifest.json")
        def run(self):
            seen.append((self.manifest["pair_id"], self.manifest["condition"], self.manifest["config"]["benchmark"]["seed"]))
            return {"status":"complete", "completed_iterations":3}
    monkeypatch.setattr(batch,"Engine",RecordingEngine)
    settings = config().model_copy(update={"replicates":2})
    batch.run_batch(settings,"mock",3,tmp_path)
    assert seen == [("0","stateless",7),("0","memory",7),("1","memory",7),("1","stateless",7)]
    assert read_json(tmp_path / "batch-status.json")["complete"] is True
