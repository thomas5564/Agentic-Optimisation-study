import fs from 'node:fs/promises';
import path from 'node:path';
import { Presentation, PresentationFile } from '@oai/artifact-tool';
import { finalizePresentation } from '/Users/jaymesonkoh/.codex/plugins/cache/openai-primary-runtime/presentations/26.1007.11041/skills/presentations/container_tools/artifact_tool_utils.mjs';

const root = process.cwd();
process.env.RUNTIME_NODE_MODULES='/Users/jaymesonkoh/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const build = path.join(root, '.presentation-build');
const skill = '/Users/jaymesonkoh/.codex/plugins/cache/openai-primary-runtime/presentations/26.1007.11041/skills/presentations';
const p = Presentation.create({slideSize:{width:1280,height:720}});
const C = {ink:'#142D3A',muted:'#4E6470',teal:'#006D77',paper:'#F8FAF9',white:'#FFFFFF',pale:'#E7EFEE',gold:'#C48122'};
const font = 'Arial';
const notes = [];
function text(s,t,x,y,w,h,size=28,color=C.ink,bold=false){
  const q=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  q.text=t; q.text.style={typeface:font,fontSize:size,color,bold};return q;
}
function slide(title, num, dark=false){
  const s=p.slides.add();s.background.fill=dark?C.ink:C.paper;
  if(title)text(s,title,70,48,1135,90,44,dark?C.white:C.ink,true);
  text(s,String(num).padStart(2,'0'),1165,657,55,26,18,dark?'#BDD8DA':C.muted);
  return s;
}
function note(s,timing,script,sources){
  const content=`${timing}\n\n${script}\n\nSources (repository-relative paths):\n${sources.join('\n')}`;
  s.speakerNotes.text=content;
  notes.push(content);
}
function table(s,values,x,y,w,h,widths){
  const tb=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,values,columnWidths:widths});
  tb.borders.assign({fill:C.paper,width:2,style:'solid'});
  for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){
    const cell=tb.getCell(r,c);cell.fill=r===0?C.ink:(r%2?C.pale:C.white);
    cell.text.style={typeface:font,fontSize:24,color:r===0?C.white:C.ink,bold:r===0};
  }
  return tb;
}

// 1. 0:00–0:30
{
 const s=slide('',1,true);
 text(s,'Memory-Guided Long-Horizon\nCode Optimization with LLM Agents',70,128,1120,205,57,C.white,true);
 text(s,'Does remembering past attempts improve future optimizations?',74,374,1045,88,31,'#BDD8DA');
 text(s,'Jaymeson Koh and Thomas Choo',74,544,1050,40,26,C.white);
 text(s,'COMP690-158 Advanced Topics in Natural Language Processing\nProgress update, 9 October 2026',74,593,1050,60,20,'#BDD8DA');
 note(s,'30 seconds • 0:00–0:30',`Our project asks whether an LLM agent can become better at optimizing an application by remembering its own previous attempts. We compare full attempt history against a stateless planner while both conditions keep successful code changes. Today I will explain the task and dataset, then separate the experimental system we have verified from the research results we still need to collect.`,['proposal.pdf, title and research question','docs/PROJECT_REPORT.md, status dated 2026-10-08']);
}
// 2. 0:30–1:20
{
 const s=slide('The optimization problem',2);
 text(s,'Make the same notes application faster\nwithout changing its behavior.',72,166,1060,104,39,C.teal,true);
 text(s,'Why memory might help',72,327,510,40,29,C.ink,true);
 text(s,'Past failures may prevent repeated mistakes, such as a cache that returns stale notes after an update.',72,385,525,155,29);
 text(s,'Why memory might hurt',684,327,510,40,29,C.ink,true);
 text(s,'A growing history may distract the planner or describe bottlenecks that no longer exist in the evolving code.',684,385,525,155,29);
 text(s,'Research question: does the benefit grow, plateau, or diminish over 30 attempts?',72,584,1090,60,26,C.muted);
 note(s,'50 seconds • 0:30–1:20',`The task is performance optimization under a fixed behavioral contract. Our test application stores notes and supports create, read, update, delete, and list or search operations. There are deliberate opportunities in database access and repeated data processing. Memory could help an agent avoid trying the same failed change again. For example, remembering that a cache became stale after an update could improve its next plan. But accepted changes also alter the program. Old advice may become irrelevant, and a longer history could distract the planner. These are competing hypotheses, not findings. We want to observe the whole trajectory over thirty attempts, rather than compare only a single final answer.`,['proposal.pdf, motivation and long-horizon evaluation','app/db.py','docs/SPEC.md']);
}
// 3. 1:20–2:30
{
 const s=slide('An optimization input and output',3);
 text(s,'INPUT TO THE AGENT',72,153,550,35,22,C.teal,true);
 text(s,'Current code + measured profile\nFull attempt history in the memory condition',72,195,1090,79,29);
 text(s,'ILLUSTRATIVE CANDIDATE OUTPUT',72,294,1050,35,22,C.teal,true);
 text(s,'A code patch that caches note reads\nand invalidates the cache after every write',72,337,1090,82,32,C.ink,true);
 table(s,[['API input (fields abbreviated)','Required output'],['PUT /notes/1 with title: Revised','200 + note with title: Revised'],['GET /notes/1 after the update','200 + note with title: Revised']],72,443,1135,176,[605,530]);
 text(s,'The runner rejects stale output, even when the response is faster.',72,634,1055,34,23,C.muted);
 note(s,'70 seconds • 1:20–2:30',`There are two kinds of input and output to distinguish. The optimizer receives the current source code and a measured profile. In the memory condition, the Planner also sees every previous attempt and its outcome. The Developer produces a candidate source-code patch. The caching patch on this slide is an illustration, not a change produced by a live model in our experiments. At the application boundary, suppose note one already exists. We update it with the title Revised, the body Updated, and the tag changed. The response must contain that updated note and its ID. A following read must return those same updated values. If a cache returns the old note, the candidate fails correctness regardless of latency. The runner independently decides whether to retain the patch. The experiment's eventual output is a retained application snapshot and a trajectory of measured performance and correctness across attempts.`,['app/main.py, update_note and get_note routes','app/models.py, Note and NoteUpdate schemas','agents/schemas/developer.json','benchmarks/oracle.py','docs/SPEC.md']);
}
// 4. 2:30–3:40
{
 const s=slide('The dataset is a controlled synthetic workload',4);
 text(s,'Notes fixture',72,157,550,44,31,C.teal,true);
 text(s,'Seed 7 generates reproducible notes\n5 title prefixes, Unicode in note bodies\n1–2 unique tags from a pool of 7',72,218,1070,123,30);
 table(s,[['Requests per cycle','Add','Get','Update','Delete','List / search'],['12 total','1','3','1','1','6']],72,366,1135,116,[285,140,140,175,160,235]);
 text(s,'Development benchmark',72,519,560,37,28,C.ink,true);
 text(s,'100 notes, 20 cycles, 5 repetitions\n1,200 timed requests',72,566,570,75,27);
 text(s,'Controller and container smoke tests',681,519,530,37,28,C.ink,true);
 text(s,'10 notes, 2 cycles, 2 repetitions\n48 timed requests per snapshot',681,566,530,75,27);
 note(s,'70 seconds • 2:30–3:40',`We are not training a model or using an external corpus. Our dataset is a reproducible application fixture together with a fixed HTTP request trace and an independent reference oracle. A seeded generator creates notes with five repeating title prefixes, Unicode text, and one or two unique tags drawn from seven choices. Every workload cycle contains twelve requests. Half exercise list or search, three read individual notes, and one each creates, updates, and deletes a note. Reads and searches follow mutations, so the trace can expose stale state. The standalone development benchmark used one hundred starting notes, twenty cycles per repetition, and five repetitions, giving twelve hundred timed requests. The smaller controller and container smoke checks use ten notes and forty-eight requests per measured snapshot. Neither configuration is a finalized research dataset. We will calibrate the final workload in the live pilot. One application and synthetic data limit generalization.`,['benchmarks/fixtures.py','benchmarks/workload.py','configs/pilot.yaml','configs/mock-paired.yaml','research/evidence/baseline-2026-10-08/benchmark_summary.json']);
}
// 5. 3:40–4:55
{
 const s=slide('The controlled comparison',5);
 table(s,[['Planner input','Stateless condition','Full-memory condition'],['Current accepted code + profile','Yes','Yes'],['All previous attempt outcomes','None','All k − 1 at attempt k'],['Accepted code persists','Yes','Yes']],72,156,1135,240,[430,325,380]);
 text(s,'Planner proposes the optimization. Developer produces the patch.',72,440,1120,46,28);
 text(s,'The runner tests and measures it. Auditor records the outcome.',72,498,1120,46,28);
 text(s,'Fresh role calls each time. Only the Planner receives history.\nNo retrieval, filtering, or summarization of previous attempts.',72,576,1100,70,26,C.teal,true);
 note(s,'75 seconds • 3:40–4:55',`The treatment is explicit attempt history. Both conditions begin from the same baseline and retain code changes that pass the acceptance rule. Stateless therefore does not mean starting from the original program each time. Its Planner sees the currently accepted code and a fresh profile, but no explicit record of past attempts. At attempt k, the memory Planner sees all k minus one previous attempt records, including failed and rejected attempts. We do not select relevant memories or summarize the history because the proposal asks about continuously growing full memory. Planner, Developer, and Auditor are fresh calls. Only the Planner receives history, so hidden conversation state cannot become an extra treatment. The Developer submits a patch, the independent runner decides correctness and acceptance, and the Auditor interprets the measured outcome. The Auditor cannot overrule the runner. Paired independent runs will use the same frozen model and workload settings, with condition order alternated.`,['proposal.pdf, experimental conditions','agents/inputs.py','controller/engine.py','controller/batch.py','docs/SPEC.md']);
}
// 6. 4:55–5:55
{
 const s=slide('What qualifies as an improvement',6);
 text(s,'1',72,165,70,76,50,C.teal,true);
 text(s,'Correct behavior',168,163,1030,45,33,C.ink,true);
 text(s,'Official tests and full response checks must pass.',168,220,1030,45,29);
 text(s,'2',72,303,70,76,50,C.teal,true);
 text(s,'A repeatable latency reduction',168,301,1030,45,33,C.ink,true);
 text(s,'Compare parent and candidate using repeated real HTTP runs.\nAccept only when relative improvement exceeds a calibrated threshold.',168,358,1030,85,28);
 text(s,'3',72,484,70,76,50,C.teal,true);
 text(s,'A reproducible record',168,482,1030,45,33,C.ink,true);
 text(s,'Archive code, measurements, role outputs, and every rejection.\nMeasure checkpoint snapshots again independently.',168,539,1030,85,28);
 note(s,'60 seconds • 4:55–5:55',`We need to separate actual optimization from broken behavior and timing noise. First, the candidate must pass the official correctness suite and the workload oracle. The oracle checks complete responses, not just HTTP status. Second, parent and candidate are measured in repeated real HTTP runs. Each repetition starts a fresh application process and database. Setup, warmups, oracle checks, and profiling are outside request timing. The primary score is the median across repetition means. Acceptance requires relative improvement above epsilon, which still needs calibration in a representative pilot. We also report mean and p95 by operation, including separate list and search reporting alongside the proposed CRUD metrics. Third, every attempt gets an authoritative record. Interrupted work can resume, and checkpoint snapshots are remeasured. This makes rejected changes and uncertainty visible instead of reporting only successful patches.`,['benchmarks/run.py','benchmarks/oracle.py','controller/evaluation.py','controller/journal.py','controller/resume.py','analysis/report.py','docs/SPEC.md']);
}
// 7. 5:55–7:00
{
 const s=slide('Current progress: the system is verified',7);
 text(s,'92',72,153,380,112,88,C.teal,true);
 text(s,'tests passed',76,269,340,45,30,C.ink,true);
 text(s,'3 × 2',490,153,350,112,88,C.teal,true);
 text(s,'mock attempts\nacross two conditions',493,269,390,88,30,C.ink,true);
 text(s,'0',952,153,250,112,88,C.gold,true);
 text(s,'live model calls',955,269,255,85,30,C.ink,true);
 text(s,'Memory Planner saw 0, 1, then 2 prior attempts.\nStateless Planner saw 0, 0, then 0.',72,405,1110,88,32);
 text(s,'Container isolation, correctness, profiling, and 48/48 requests passed.\nResume preserved the completed run without changing its records.',72,526,1120,88,28);
 text(s,'Evidence of working infrastructure. No measured memory benefit yet.',72,629,1085,35,25,C.teal,true);
 note(s,'65 seconds • 5:55–7:00',`The baseline application, benchmark harness, role controller, full-history treatment, recovery, paired scheduling, and offline analysis are implemented. The verified suite has ninety-two passing tests. We ran three scripted mock attempts in each condition: a comment-only patch, a syntax error, and a no-op. All were rejected, so both conditions retained exactly the baseline code. This checks control flow, not model intelligence. Crucially, the memory Planner received zero, one, then two prior records, while the stateless Planner received none in all three iterations. The completed run resumed without changing archived records. In a real Linux container, the official baseline tests passed, all forty-eight timed requests were valid, profiling worked, and the filesystem isolation checks passed. There have been zero live model calls. Any small latency difference between the identical mock snapshots is noise and cannot support a claim that memory helps.`,['research/evidence/controller-2026-10-08/verification.json','docs/PROJECT_REPORT.md']);
}
// 8. 7:00–8:00
{
 const s=slide('The remaining research milestones',8);
 text(s,'Live-model smoke and pilot',72,166,1090,45,33,C.teal,true);
 text(s,'Choose the model, verify a real iteration, and calibrate the workload\nand acceptance threshold before freezing the protocol.',72,225,1125,86,29);
 text(s,'Paired 30-attempt study',72,351,1090,45,33,C.teal,true);
 text(s,'At least 3 independent pairs, targeting 5.\nCheckpoint comparisons at attempts 10, 15, 20, 25, and 30.',72,410,1125,86,29);
 text(s,'Analysis of memory over time',72,536,1090,45,33,C.teal,true);
 text(s,'Latency and correctness trajectories, failed attempts,\nand whether longer histories help, plateau, or hinder progress.',72,590,1125,75,29);
 note(s,'60 seconds • 7:00–8:00',`The next gate is a real model smoke run, followed by a representative pilot. We still need to choose and configure the model, verify one real iteration, and calibrate the workload and acceptance threshold before freezing final settings. The planned study then runs thirty attempts per condition across independent replicate pairs, with at least three pairs and a target of five. We compare remeasured snapshots at attempts ten, fifteen, twenty, twenty-five, and thirty. The statistical replicate is an independent optimization run, not each HTTP request or iteration. We will examine performance together with correctness and failed attempts, and track the growth of history. The central question remains open: does full history improve the trajectory, and does that effect change as the history becomes longer? The system now supports that experiment, but we have not yet established its answer.`,['proposal.pdf, checkpoints and evaluation','docs/SPEC.md, replication and pilot protocol','docs/PLAN.md','docs/PROJECT_REPORT.md']);
}
// 9. Q&A
{
 const s=slide('',9,true);
 text(s,'Questions & Answers',72,161,1120,100,66,C.white,true);
 text(s,'5 minutes',75,281,1050,45,30,'#BDD8DA');
 text(s,'Can full attempt history improve optimization\nas the application and the history both evolve?',75,418,1110,112,40,C.white);
 text(s,'Backup slides: workload details and measurement uncertainty',75,608,1100,36,23,'#BDD8DA');
 note(s,'5 minutes • 8:00–13:00',`Invite questions. Useful discussion topics: Why use full history instead of retrieval? That preserves the original treatment and tests history growth directly. Why only one application? It controls the task but limits generalization. Is the model chosen? Not yet. Do mock timings show a memory effect? No, both conditions retained identical code. How will we avoid pseudoreplication? Compare independent run pairs, not individual requests as independent experiments. Use the backup slides for workload counts or timing noise.`,['proposal.pdf','docs/SPEC.md','docs/PROJECT_REPORT.md']);
}
// 10. Backup
{
 const s=slide('Backup: workload and dataset details',10);
 table(s,[['Setting','Development benchmark','Smoke checks'],['Initial notes','100','10'],['Cycles per repetition','20','2'],['Timed requests per repetition','240','24'],['Repetitions','5','2'],['Total timed requests','1,200','48'],['Concurrency / seed','1 / 7','1 / 7']],72,153,1135,364,[455,360,320]);
 text(s,'Each repetition uses a fresh process and database. Seeding and\nread-only warmups are untimed. Profiling runs separately.',72,552,1120,78,27);
 text(s,'These are development settings. Final study settings remain to be frozen.',72,642,1090,32,23,C.muted);
 note(s,'Backup • use only during questions',`The twelve-request cycle is: get a seeded note, list, filtered list, add, get the new note, list its tag, update it, get the updated note, list the old tag, list the new tag, delete it, and list the new tag again. A reference oracle checks IDs, content, tags, counts, ordering, pagination, and mutations. The fixture is seeded through the public API so a candidate's schema remains intact. Two development warmup cycles each contain two read-only requests, for four unmeasured warmup requests per repetition. Smoke uses one warmup cycle. The development benchmark recorded all twelve hundred valid requests. The container check recorded all forty-eight. No external or personal dataset is used.`,['benchmarks/fixtures.py','benchmarks/workload.py','benchmarks/reset.py','benchmarks/oracle.py','configs/pilot.yaml','configs/mock-paired.yaml']);
}
// 11. Backup
{
 const s=slide('Backup: timing noise and research limits',11);
 text(s,'Development baseline measurements',72,161,1085,46,32,C.teal,true);
 table(s,[['Repetition','1','2','3','4','5'],['Mean latency (ms)','1.109','1.018','1.407','1.436','1.088']],72,230,1135,116,[335,160,160,160,160,160]);
 text(s,'Median of repetition means: 1.109 ms\nCoefficient of variation: 16.07%',72,385,1100,85,31,C.ink,true);
 text(s,'This is noise evidence, not an optimization result.\nThe final acceptance threshold still needs pilot calibration.',72,489,1100,78,29);
 text(s,'Limits: one synthetic application, growing context length,\nand possible sensitivity to the chosen model and machine.',72,598,1100,69,26,C.muted);
 note(s,'Backup • use only during questions',`These five repetition means come from the standalone macOS baseline benchmark. Their spread motivates calibration and repeated measurement. The primary score is the median of those means, approximately 1.109 milliseconds. The recorded coefficient of variation is 16.07 percent and the relative range is 34.48 percent. These values do not establish a reasonable final epsilon by themselves, especially on a small development workload. The smoke configuration's epsilon of 0.5 is explicitly a control-flow threshold, not a final noise-calibrated choice. Do not compare these host timings with Linux container timings. If asked about broader validity, the current design studies one app and a synthetic workload, and its result will be conditional on model, workload, environment, and full-history context limits.`,['research/evidence/baseline-2026-10-08/benchmark_summary.json','docs/PROJECT_REPORT.md','configs/mock-paired.yaml','docs/SPEC.md']);
}

await fs.mkdir(path.join(build,'renders'),{recursive:true});
await (await PresentationFile.exportPptx(p)).save(path.join(build,'draft.pptx'));
await fs.writeFile(path.join(build,'speaker-notes.txt'),notes.map((n,i)=>`SLIDE ${i+1}\n${n}`).join('\n\n'));
const final=path.join(root,'output/presentations/memory-guided-optimization-8min.pptx');
await finalizePresentation({workspaceDir:root,candidatePath:path.join(build,'draft.pptx'),finalPath:final,
 pythonExecutable:'/Users/jaymesonkoh/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3',
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit',...[3,4,5,10,11].flatMap(n=>['--require-native-table-slide',String(n)])],
 requiredNativeTableOwnerSlides:[3,4,5,10,11],fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,
 receiptPath:path.join(build,'validation-final.json')});
for(let i=0;i<p.slides.items.length;i++){
 const blob=await p.export({slide:p.slides.items[i],format:'png',scale:1});
 await fs.writeFile(path.join(build,'renders',`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await blob.arrayBuffer()));
}
console.log(final);
