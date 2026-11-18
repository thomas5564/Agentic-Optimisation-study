from pathlib import Path
import re
s=Path('docs/PROJECT_REPORT.md').read_text()
s=s[s.index('## Introduction and problem definition'):s.index('## Evidence and deliverables')]
s=s.replace('## Related work\n','## Related work\n')
s=re.sub(r'PerfAgent \(Deng et al\., 2026, https://arxiv.org/abs/2607.19653\)',r'PerfAgent \\citep{deng2026perfagent}',s)
s=re.sub(r'Reflexion\n\(Shinn et al\., 2023, https://arxiv.org/abs/2303.11366\)',r'Reflexion \\citep{shinn2023reflexion}',s)
s=re.sub(r'Self-Refine \(Madaan et al\., 2023,\nhttps://arxiv.org/abs/2303.17651\)',r'Self-Refine \\citep{madaan2023selfrefine}',s)
s=s.replace('(`benchmarks/fixtures.py`)','(project-generated; \\citealt{koh2026testbed})')
s=s.replace('Exact first generated record:', 'Annotated first record (Unicode body shown with code-point escapes):')
s=s.replace('café 世界','caf\\u00e9 \\u4e16\\u754c')
s=s.replace('## Contributions','\\clearpage\n## Contributions')
def esc(t):
 t=t.replace('–','--').replace('—','---')
 t=t.replace('×',r'$\times$').replace('−',r'$-$').replace('’',"'")
 t=re.sub(r'\\u([0-9a-fA-F]{4})',lambda m:r'\textbackslash{}u'+m.group(1),t)
 t=t.replace('&',r'\&').replace('%',r'\%').replace('#',r'\#').replace('_',r'\_')
 t=re.sub(r'`([^`]+)`',lambda m:r'\texttt{'+m.group(1).replace('{',r'\{').replace('}',r'\}')+'}',t)
 t=re.sub(r'\*\*(.*?)\*\*',lambda m:r'\textbf{'+m.group(1)+'}',t)
 return t
lines=s.splitlines();parts=[];i=0
while i<len(lines):
 l=lines[i]
 if l.startswith('## '):parts.append(r'\section{'+esc(l[3:])+'}');i+=1
 elif l.startswith('```'):
  i+=1;b=[]
  while i<len(lines) and not lines[i].startswith('```'):b.append(lines[i]);i+=1
  # display each field on its own short line
  parts.append(r'\begin{quote}\small\ttfamily '+r'\\'.join(esc(x) for x in ['title: Beta #1','body: Deterministic note 1.',r'Unicode: caf\u00e9',r'\u4e16\u754c. seed=7','tags: ["alpha", "notes"]'])+r'\end{quote}');i+=1
 elif l.startswith('|'):
  rows=[]
  while i<len(lines) and lines[i].startswith('|'):
   cells=[x.strip() for x in lines[i].strip('|').split('|')]
   if not all(re.fullmatch(r'[:\- ]+',x) for x in cells):rows.append(cells)
   i+=1
  # compact the broad results table to fit one column; outcomes stay in prose
  if len(rows[0])==7:
   rows=[[r[0],r[1],r[2],r[6]] for r in rows];rows[0]=['Arm','ms','Speedup','Conv.']
  if len(rows[0])==3 and 'Max Planner' in rows[0][-1]:rows[0]=['Arm','All input','Max Planner']
  
  if len(rows[0])==4 and 'Final latency' in rows[0][1]:rows[0]=['Arm','Final ms','Kept','Input tokens']
  cols='l'+'r'*(len(rows[0])-1)
  parts.append(r'\begin{table}[H]\centering\small\begin{tabular}{'+cols+r'}\toprule'+'\n'+r'\\'.join(' & '.join(esc(x) for x in row) for row in rows[:1])+r'\\\midrule'+'\n'+r'\\'.join(' & '.join(esc(x) for x in row) for row in rows[1:])+r'\\\bottomrule\end{tabular}\caption{'+['Unrestricted study: final remeasurement latency, accepted changes and input tokens.','Strict study: final latency, own-baseline speedup and convergence iteration.','Strict study: all-role total input and largest Planner input, in tokens.'][sum('\\begin{table}' in p for p in parts)]+r'}\end{table}')
 elif l.startswith('- '):
  items=[]
  while i<len(lines) and (lines[i].startswith('- ') or (lines[i].startswith('  ') and lines[i].strip())):
   if lines[i].startswith('- '):items.append(lines[i][2:])
   else:items[-1]+=' '+lines[i].strip()
   i+=1
  # use paragraphs for metric definitions and dataset annotations
  parts.extend(esc(x)+'\n\n' for x in items)
 else:parts.append(esc(l));i+=1
body='\n'.join(parts)
body=body.replace('Rows are arms; columns report independent final latency, own-baseline speedup,\naccepted changes, errors/all attempts, no-ops and convergence iteration.', 'The table rows are arms; columns report final latency, own-baseline speedup and convergence. Accepted steps, error rates and no-op counts are reported in the text.')
body=body.replace('LRU accepted only attempts', 'Errors occurred in 13/30 stateless, 12/30 full-history and 2/30 LRU attempts; no-op counts were 5, 9 and 20 respectively. LRU accepted only attempts')
# Place contributions after references, excluded from four-page body.
body,contrib=body.split('\\clearpage\n\\section{Contributions}')
header=r'''\documentclass[11pt]{article}
\usepackage{acl2023}
\usepackage{times,latexsym}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{microtype,booktabs,float}
\title{Memory-Guided Long-Horizon Code Optimization:\\Full History versus a Bounded Notebook}
\author{Jaymeson Koh \and Thomas Choo\\University of North Carolina at Chapel Hill\\COMP 690-158: Advanced Topics in Natural Language Processing}
\date{}
\begin{document}
\maketitle
\begin{abstract}
We study whether explicit attempt history helps a language model optimize an evolving notes application. A protected controller compares no history, complete history, and a six-entry least-recently-used cache. Two exploratory studies each run 30 attempts per arm. Without enforced patch scope, initial rewrites dominate. With a one-operation scope rule, final latencies are 0.737, 0.584 and 0.560 milliseconds respectively; bounded history uses 18.7\% fewer input tokens than complete history. Each study has one run per arm, so these are descriptive observations, not replicated evidence of a causal memory benefit. We release an auditable testbed and identify correctness, workload and replication limits.
\end{abstract}
'''
tail=r'''
\clearpage
\bibliographystyle{acl_natbib}
\bibliography{references}
\section*{Contributions}
'''+contrib+r'''
\clearpage
\appendix
\section{Prompt details}
The following are the complete base role prompts used by the controller. Runtime source, evidence and JSON schemas are appended as structured inputs. Only the Planner directly receives allowed history. Strict-scope and LRU additions are disclosed below; they do not replace the base prompt.
'''
for role in ['planner','developer','auditor']:
 tail+='\n\\subsection{'+role.title()+'}\n'+esc(Path(f'agents/prompts/{role}.txt').read_text())+'\n'
# Exact policy additions with natural wrapping, not a long verbatim line.
import ast
module=ast.parse(Path('lru_memory/policy.py').read_text())
for n in module.body:
 if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ['POLICY_NOTE','STRICT_NOTE','DEVELOPER_NOTE']:
  tail+='\n\\subsection{'+{'POLICY_NOTE':'LRU Planner addition','STRICT_NOTE':'Strict Planner addition','DEVELOPER_NOTE':'Strict Developer addition'}[n.targets[0].id]+'}\n'+esc(ast.literal_eval(n.value))+'\n'
tail+=r'\end{document}'
Path('output/report/final-project-report.tex').write_text(header+body+tail)
