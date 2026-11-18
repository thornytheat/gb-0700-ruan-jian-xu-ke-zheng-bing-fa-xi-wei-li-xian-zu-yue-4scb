from app.report import report
from app.pools import pool_members

def capacity_at(rows,a):
    """单个原产品契约在时刻 a 的有效采购量。

    采购记录按契约各自判定版本：区间内最高版本优先，同最高版不同数量为冲突。
    合并池只是把各契约的采购量相加，从不改写任何一条采购记录。
    """
    valid=[r for r in rows if r["a"]<=a<r["b"]]
    if not valid:return 0,False
    version=max(r["rev"] for r in valid);values={r["quantity"] for r in valid if r["rev"]==version}
    return min(values),len(values)>1

def capacity_contracts(pool,contract,capacities):
    """该视图下参与限席的容量记录归属。

    合并视图用池内所有原契约的采购量之和；旧版分产品视图只用签发契约自己的
    采购量。以合并名签发的新租约没有单独采购，按合并契约继承原契约采购量。
    """
    if contract is None:
        base=set(pool_members(pool)) or {pool}
        return sorted(base|{r["contract"] for r in capacities if r["pool"]==pool})
    base=set(pool_members(contract))
    if base:return sorted(base|{r["contract"] for r in capacities if r["contract"]==contract})
    return [contract]

def capacity_breakdown(capacities,contracts,a):
    total=0;conflict=False;items=[]
    for contract in contracts:
        value,bad=capacity_at([r for r in capacities if r["contract"]==contract],a)
        total+=value;conflict=conflict or bad
        items.append({"contract":contract,"capacity":value})
    return total,conflict,items

def allocate_excess(active,extra):
    """超用责任按租约开始倒序、再按编号倒序分配；逐席位归属到原契约。"""
    charged=[]
    for r in sorted(active,key=lambda r:(r["a"],r["lease_id"]),reverse=True):
        take=min(extra,r["quantity"])
        if take:charged.append({"id":r["lease_id"],"user":r["user"],"seats":take,
                                "contract":r.get("contract",r.get("canonical","")),
                                "pool":r.get("pool","")})
        extra-=take
    return charged

def apply(ctx):
    out=[];capacities=[r for r in ctx["normalized"] if r["kind"]=="capacity"]
    for segment in ctx["segments"]:
        pool=segment["pool"]
        contracts=capacity_contracts(pool,None if segment["view"]=="merged" else segment["contract"],capacities)
        caps=[r for r in capacities if r["pool"]==pool]
        cuts=sorted({segment["a"],segment["b"]}|{r[k] for r in caps for k in ("a","b") if segment["a"]<r[k]<segment["b"]})
        for a,b in zip(cuts,cuts[1:]):
            capacity,conflict,breakdown=capacity_breakdown(capacities,contracts,a)
            extra=max(0,segment["count"]-capacity)
            if segment["view"]=="merged":
                active=[r for r in ctx["leases"] if r["pool"]==pool and r["a"]<=a<r["b"]]
            else:
                active=[r for r in ctx["leases"] if r["contract"]==segment["contract"] and r["a"]<=a<r["b"]]
            out.append({"pool":pool,"product":segment["product"],"view":segment["view"],
                        "a":a,"b":b,"concurrent":segment["count"],"capacity":capacity,"excess":extra,
                        "capacity_by_contract":breakdown,
                        "contracts":segment["contracts"],
                        "offenders":allocate_excess(active,extra),
                        "status":"CAPACITY_CONFLICT" if conflict else "OVERUSE" if extra else "PASS"})
    ctx["usage"]=out
    return report(out,超用区间=sum(r["excess"]>0 for r in out),
                  冲突=sum(r["status"]=="CAPACITY_CONFLICT" for r in out),
                  席位池=len({r["pool"] for r in out}))
