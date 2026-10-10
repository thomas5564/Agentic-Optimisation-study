from pathlib import Path
from datetime import datetime,timezone
from controller.storage import read_json,write_json,run_lock,load_snapshot
from controller.config import ExperimentConfig
from controller.engine import Engine,score
from controller.evaluation import Evaluator
root=Path('/Users/jaymesonkoh/.codex/visualizations/2026/10/09/01a11e69-8712-76f2-a79c-5dacf01d710e/experiments/soclaas-final-2026-10-10')
run=root/'pair-01-memory'
with run_lock(root),run_lock(run):
 config=ExperimentConfig.model_validate(read_json(run/'manifest.json')['config'])
 engine=Engine(run,None,Evaluator(config,isolated=True));engine.verify()
 attempts=engine.attempts()
 assert len(attempts)==1, 'Unexpected stop boundary'
 assert not any(read_json(p).get('paid') and read_json(p)['status']=='started' for p in (run/'journal').glob('*.json')), 'Unresolved role call'
 engine.materialize(attempts)
 retained=attempts[-1]['retained_hash']
 final=engine.evaluation('final-remeasurement','measure',load_snapshot(run,retained),required=True)
 state={'status':'stopped_by_user','completed_iterations':len(attempts),'planned_iterations':30,'retained_hash':retained,'final_remeasurement_score_ms':score(final),'reason':'User requested wrap-up; active attempt completed, remaining horizon and scheduled runs not executed.'}
 write_json(run/'state.json',state)
 schedule=read_json(root/'batch.json')['schedule']; states=[]
 for entry in schedule:
  p=root/entry['directory']/'state.json'
  states.append({**entry,**(read_json(p) if p.exists() else {'status':'not_started','completed_iterations':0})})
 record={'schema_version':1,'stopped_at':datetime.now(timezone.utc).isoformat(),'reason':state['reason'],'complete':False,'planned_attempts':300,'completed_attempts':sum(x['completed_iterations'] for x in states),'completed_pairs':1,'runs':states}
 write_json(root/'batch-status.json',record)
 write_json(root/'operator-stop.json',record)
 write_json(Path('research/evidence/live-2026-10-10/final-execution-status.json'),record)
 print(record)
