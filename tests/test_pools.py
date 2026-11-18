from app.modules.m4_concurrency.rules import sweep
from app.modules.m4_concurrency.rules import pool_segments,legacy_segments,apply as concurrency_apply
from app.modules.m2_products.rules import product
from app.modules.m3_leases.rules import apply as lease_apply
from app.pools import pool_for,contracts_for,pool_members

def lease(contract,lease_id="L1",a=0,b=100,quantity=1,rev=1,pool=None,kind="online"):
    return {"lease_id":lease_id,"contract":contract,"pool":pool or pool_for(contract) or contract,
            "a":a,"b":b,"quantity":quantity,"rev":rev,"user":"u","kind":kind,"start":str(a)}

def ctx(leases,capacities=(),views=None):
    return {"leases":list(leases),"normalized":list(capacities),"pool_views":views or {}}

def test_legacy_lease_keeps_original_contract_in_pool():
    a=lease("CAD");b=lease("RENDER",lease_id="R2")
    assert a["contract"]=="CAD" and b["contract"]=="RENDER"
    assert a["pool"]==b["pool"]=="CAD+RENDER"

def test_new_lease_issues_against_merged_product():
    assert product("CAD+RENDER")=="CAD+RENDER"
    assert product("CAD-RENDER")=="CAD+RENDER"
    assert product("CAD_RENDER")=="CAD+RENDER"

def test_pool_limits_shared_seats():
    leases=[lease("CAD",quantity=2),lease("RENDER",lease_id="R2",quantity=3)]
    segments=pool_segments(leases)
    assert len(segments)==1 and segments[0]["count"]==5 and segments[0]["pool"]=="CAD+RENDER"
    assert {x["contract"] for x in segments[0]["contracts"]}=={"CAD","RENDER"}

def test_merged_pool_does_not_double_book_capacity():
    # 两个原契约各 3 席采购，共享池容量是 6，而不是每个产品各 6。
    leases=[lease("CAD",quantity=2),lease("RENDER",lease_id="R2",quantity=2)]
    caps=[dict(lease("CAP1",lease_id="CAP01",a=0,b=100,quantity=3,kind="capacity"),contract="CAD",pool="CAD+RENDER"),
          dict(lease("CAP2",lease_id="CAP02",a=0,b=100,quantity=3,kind="capacity"),contract="RENDER",pool="CAD+RENDER")]
    r=concurrency_apply(ctx(leases,caps))
    assert r["metrics"]["席位池"]==1
    from app.modules.m5_excess.rules import apply as excess_apply
    e=ctx(leases,caps);e["segments"]=r["rows"]
    usage=excess_apply(e)
    assert all(seg["capacity"]==6 for seg in usage["rows"])

def test_legacy_view_splits_contract_capacity():
    leases=[lease("CAD",quantity=4),lease("RENDER",lease_id="R2",quantity=4)]
    caps=[dict(lease("CAP1",lease_id="CAP01",quantity=3,kind="capacity"),contract="CAD",pool="CAD+RENDER"),
          dict(lease("CAP2",lease_id="CAP02",quantity=3,kind="capacity"),contract="RENDER",pool="CAD+RENDER")]
    r=concurrency_apply(ctx(leases,caps,{"CAD+RENDER":"legacy"}))
    assert {seg["view"] for seg in r["rows"]}=={"legacy"}
    from app.modules.m5_excess.rules import apply as excess_apply
    e=ctx(leases,caps,{"CAD+RENDER":"legacy"});e["segments"]=r["rows"]
    usage=excess_apply(e)
    assert all(seg["capacity"]==3 for seg in usage["rows"])
    assert all(seg["excess"]==1 for seg in usage["rows"])

def test_release_matches_original_contract_only():
    leases=[lease("CAD",lease_id="00001")]
    release={"lease_id":"00001","contract":"CAD+RENDER","pool":"CAD+RENDER","a":10,"b":10,"quantity":1,"rev":1,"kind":"release","user":"u"}
    c={"leases":[],"normalized":leases+[release],"quarantine":[]}
    lease_apply(c)
    assert len(c["leases"])==1 and c["leases"][0]["b"]==100
    assert any(x["reason"]=="RELEASE_CONTRACT_MISMATCH" for x in c["lease_audit"])

def test_release_matches_original_contract_version():
    leases=[lease("CAD",lease_id="00001",rev=2)]
    release={"lease_id":"00001","contract":"CAD","pool":"CAD+RENDER","a":10,"b":10,"quantity":1,"rev":1,"kind":"release","user":"u"}
    c={"leases":[],"normalized":leases+[release],"quarantine":[]}
    lease_apply(c)
    assert c["leases"][0]["b"]==100
    assert any(x["reason"]=="RELEASE_VERSION_MISMATCH" for x in c["lease_audit"])

def test_contracts_for_pool():
    assert contracts_for("CAD+RENDER")==("CAD","RENDER")
    assert pool_members("CAD+RENDER")==("CAD","RENDER")
