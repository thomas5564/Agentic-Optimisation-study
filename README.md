# COMP 690 Notes Baseline

This project implements the Milestone 1 baseline for the notes application.

## Setup

```bash
python -m pip install -e .
```

## Run the API

```bash
python -m uvicorn app.main:app --reload
```

## Run tests

```bash
python -m pytest tests/ -q
```

## Get result

```
.venv/bin/python -m benchmarks.run --config configs/pilot.yaml --output benchmark-output
```

