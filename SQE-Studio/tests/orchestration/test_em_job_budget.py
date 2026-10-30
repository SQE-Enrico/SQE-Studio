"""Time budgets are fixed by trusted application code, never from user input."""
from sqe_studio.jobs import (_job_budget_seconds, MAX_SECONDS, MAX_SWEEP_SECONDS,
                             MAX_REVIEWED_EM_SECONDS)

def test_only_reviewed_em_solve_gets_bounded_longer_job_budget():
    def snapshot(engine='sqdmetal_palace', execution='solve', sweep=False):
        study={'engine':engine, 'inputs':{'em':{'execution':execution, 'solver':{'max_iterations':10}}}}
        result={'study':study}
        if sweep:result['sweep_plan']={'points':[{}]}
        return result
    assert _job_budget_seconds(snapshot())==MAX_REVIEWED_EM_SECONDS==900
    assert _job_budget_seconds(snapshot(execution='deck_only'))==MAX_SECONDS
    assert _job_budget_seconds(snapshot(engine='scqubits'))==MAX_SECONDS
    assert _job_budget_seconds(snapshot(sweep=True))==MAX_SWEEP_SECONDS
    changed=snapshot()
    changed['study']['inputs']['em']['solver']['timeout_seconds']=10_000_000
    assert _job_budget_seconds(changed)==MAX_REVIEWED_EM_SECONDS
