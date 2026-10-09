from pathlib import Path
import pytest

from benchmarks.metrics import write_json
from controller.config import ExperimentConfig
from controller.freeze import freeze, validate_frozen


def settings():
    return ExperimentConfig(phase="pilot", epsilon=.2, benchmark={"seed":7,"repetitions":5},
                            model="explicit-test-model", image="sha256:"+"1"*64, input_token_limit=200000)


def pilot(root, condition, noise=.1):
    config = settings()
    write_json(root / "manifest.json", {"run_id":condition,"phase":"pilot","backend":"codex","synthetic":False,
                                        "condition":condition,"config":config.model_dump()})
    write_json(root / "state.json", {"status":"complete"})
    write_json(root / "journal" / "baseline-measure.json", {"result":{"aggregate":{"noise":{"relative_range":noise}}}})


def test_freeze_requires_both_real_pilots_and_threshold_above_noise(tmp_path):
    a,b=tmp_path/'a',tmp_path/'b'
    pilot(a,"memory")
    with pytest.raises(ValueError, match="Both"):
        freeze(settings(),[a],tmp_path/'final.yaml')
    pilot(b,"stateless",noise=.3)
    with pytest.raises(ValueError, match="epsilon"):
        freeze(settings(),[a,b],tmp_path/'final.yaml')
    pilot(b,"stateless")
    freeze(settings(),[a,b],tmp_path/'final.yaml')
    from controller.config import load_config
    frozen = load_config(tmp_path/'final.yaml')
    validate_frozen(frozen)
    with pytest.raises(ValueError, match="protocol hash"):
        validate_frozen(frozen.model_copy(update={"epsilon":.5}))
