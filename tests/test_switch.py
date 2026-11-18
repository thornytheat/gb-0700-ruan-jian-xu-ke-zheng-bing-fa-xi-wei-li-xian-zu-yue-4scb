import pytest
from app.errors import BusinessError
from app import rollout, store
from app.exporter import evidence_csv
from app.pipeline import sample_text

POOL = "CAD+RENDER"


def new_lease_csv(extra=""):
    return sample_text() + "N01,CAD+RENDER,newuser,2026-11-18T00:00:00+00:00,2026-11-18T02:00:00+00:00,online,1,4\n" + extra


@pytest.fixture(autouse=True)
def clean():
    store.reset_switch(POOL)
    yield
    store.reset_switch(POOL)


def test_interrupted_switch_keeps_legacy_view():
    state = rollout.start_or_resume(sample_text(), POOL, interrupt_after=3)
    assert state["status"] == "INTERRUPTED" and state["view"] == "legacy"
    result = rollout.evaluate(sample_text())
    assert {seg["view"] for seg in result["segments"]} == {"legacy"}
    assert all(seg["pool"] == POOL for seg in result["segments"])
    # 旧版视图仍逐份保留原产品契约与采购量。
    assert all(seg["contracts"] for seg in result["segments"])
    assert all(seg["capacity"] == 12 for seg in result["usage"])


def test_legacy_view_does_not_double_book_capacity():
    result = rollout.evaluate(sample_text())
    # 合并池容量 = CAD 12 + RENDER 0，不是每个产品各 12。
    assert all(seg["capacity"] == 12 for seg in result["usage"])
    assert all(sum(x["capacity"] for x in seg["capacity_by_contract"]) == seg["capacity"] for seg in result["usage"])


def test_resume_only_continues_unmigrated_leases():
    total = len(rollout.run(sample_text(), {})["leases"])
    first = rollout.start_or_resume(sample_text(), POOL, interrupt_after=4)
    second = rollout.start_or_resume(sample_text(), POOL, interrupt_after=5)
    assert first["migrated"] == 4
    assert second["migrated"] == 9 and second["remaining"] == total - 9
    keys = [m["lease_key"] for m in second["migrations"]]
    assert len(keys) == len(set(keys))


def test_retry_same_merge_does_not_double_occupy():
    rollout.start_or_resume(sample_text(), POOL)
    once = rollout.current(POOL)
    twice = rollout.start_or_resume(sample_text(), POOL)
    assert twice["migrated_seats"] == once["migrated_seats"] == once["seats"]
    assert twice["attempt"] == once["attempt"]
    assert twice["status"] == "COMPLETED"


def test_completion_switches_view():
    rollout.start_or_resume(sample_text(), POOL)
    result = rollout.evaluate(sample_text())
    assert {seg["view"] for seg in result["segments"]} == {"merged"}
    assert result["pool_switches"][0]["status"] == "COMPLETED"


def test_different_merge_conflicts():
    rollout.start_or_resume(sample_text(), POOL, interrupt_after=2)
    changed = sample_text() + "X9,CAD,user99,2026-11-18T08:00:00+00:00,2026-11-18T09:00:00+00:00,online,1,2\n"
    with pytest.raises(BusinessError) as caught:
        rollout.start_or_resume(changed, POOL)
    assert caught.value.code == "SWITCH_CONFLICT"
    assert rollout.current(POOL)["status"] == "INTERRUPTED"

def test_new_merged_lease_does_not_change_merge_identity():
    """切换期间补传的新合并租约不属于旧租约集合，不改变合并身份，也不需要迁移。"""
    rollout.start_or_resume(sample_text(), POOL)
    state = rollout.start_or_resume(new_lease_csv(), POOL)
    assert state["status"] == "COMPLETED"
    assert state["new_leases"] == 1 and state["new_seats"] == 4

def test_additional_old_contract_lease_conflicts_until_reset():
    """新增旧契约租约会改变旧租约集合，须显式重置后重新合并，不能悄悄扩大范围。"""
    rollout.start_or_resume(sample_text(), POOL)
    with pytest.raises(BusinessError) as caught:
        rollout.start_or_resume(sample_text() + "C77,CAD,user77,2026-11-18T08:00:00+00:00,2026-11-18T09:00:00+00:00,online,1,1\n", POOL)
    assert caught.value.code == "SWITCH_CONFLICT"


def test_unknown_pool_rejected():
    with pytest.raises(BusinessError):
        rollout.start_or_resume(sample_text(), "CAD")


def test_new_merged_lease_issues_in_pool_not_old_contract():
    state = rollout.start_or_resume(new_lease_csv(), POOL, interrupt_after=0)
    assert state["new_leases"] == 1 and state["new_seats"] == 4
    assert state["occupied_seats"] == state["seats"] + 4
    result = rollout.evaluate(new_lease_csv())
    assert {seg["pool"] for seg in result["segments"]} == {POOL}
    pending = [p for p in result["purchase"] if p["view"] == "pending"]
    assert pending and pending[0]["pending_seats"] == 4


def test_evidence_shows_contracts_pool_and_attribution():
    item = rollout.save_run(sample_text())
    text = evidence_csv(item).replace('""', '"')
    assert '"contract": "CAD"' in text and '"pool": "CAD+RENDER"' in text
    for kind in ("lease", "pool-switch", "pool-segment", "pool-attribution", "quarantine"):
        assert kind in text


def test_old_snapshot_keeps_its_view_after_switch_completes():
    rollout.start_or_resume(sample_text(), POOL, interrupt_after=2)
    old = rollout.save_run(sample_text())
    rollout.start_or_resume(sample_text(), POOL)
    fresh = rollout.save_run(sample_text())
    assert {seg["view"] for seg in old["result"]["segments"]} == {"legacy"}
    assert {seg["view"] for seg in fresh["result"]["segments"]} == {"merged"}
    assert old["id"] != fresh["id"]
    # 历史快照不会被新视图覆盖。
    assert {seg["view"] for seg in store.get(old["id"])["result"]["segments"]} == {"legacy"}


def test_switch_does_not_change_purchase_quantities():
    before = rollout.run(sample_text(), {})
    rollout.start_or_resume(sample_text(), POOL)
    after = rollout.evaluate(sample_text())
    total_before = {c["contract"]: c["capacity"] for c in before["usage"][0]["capacity_by_contract"]}
    total_after = {c["contract"]: c["capacity"] for c in after["usage"][0]["capacity_by_contract"]}
    assert total_before == total_after
