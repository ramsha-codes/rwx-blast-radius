"""Diagnostics: ablation costs on the sample (base, oracle floor, no generator_memory, no fixed fallbacks)."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import selector
s=Path(__file__).resolve().parent.parent/'sample'; tests=json.load(open(s/'tests.json'))['tests']; by={t['number']:t for t in tests}
ans=json.load(open(s/'answers.json'))['commits']
sel=selector.Selector(tests)
def cost(nums):
    if not nums: return 0
    ws=[w for w in selector.best_split([by[n] for n in sorted(nums)]) if w]
    return max(sum(selector.duration_ms(by[n]) for n in w) for w in ws)/1000+2*len(ws)
mem=[t['number'] for t in tests if 'test_generator_memory' in t['id']]
tp=[t['number'] for t in tests if 'test_execute_tpcds' in t['id']]
T=dict(base=0,oracle=0,nomem=0,nomem_tp_unless_fail=0,noextra=0,miss_nomem=0)
for c,a in ans.items():
    n,_=sel.select((s/'commits'/(c+'.patch')).read_text())
    n=set(n); f=set(a['failing'])
    T['base']+=cost(n); T['oracle']+=cost(f&n)
    n2=n-set(mem); T['nomem']+=cost(n2); T['miss_nomem']+= bool(f-n2)
    base_fixed=set(sel.extra_always)|sel.numbers(sel.unmapped_bits)|sel.numbers(sel.proc_bits)
    T['noextra']+=cost(n-base_fixed|(f&n))
    if base_fixed&n: print(c,'always-ish tests in sel:',len(base_fixed&n), 'cost',round(cost(n),1),'->',round(cost(n-base_fixed),1))
print({k:round(v,1) for k,v in T.items()})
print('mem tests',mem,[by[m]['seconds'] for m in mem],'always',len(sel.extra_always),len(sel.numbers(sel.unmapped_bits)),len(sel.numbers(sel.proc_bits)))
