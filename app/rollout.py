"""池切换编排：计算视图、生成快照、执行/接续合并。"""
from app import store
from app.pipeline import run
from app.pools import MERGED_PRODUCTS, contracts_for, normalize_pool, pool_members


def evaluate(text):
    """按当前池切换状态计算一次；结果内嵌视图快照，便于页面与证据复现。"""
    views, states, token = store.view_context()
    # 没有切换记录的池也要在页面与证据里显式给出视图（合并池），
    # 否则导出无法说明该段用的是共享池限席。
    known={s["pool"] for s in states}
    for pool in MERGED_PRODUCTS:
        if pool not in known:
            states.append(store.switch_payload(pool))
    states.sort(key=lambda s:s["pool"])
    result = run(text, views)
    result["pool_switches"] = states
    result["pool_token"] = token
    return result


def save_run(text):
    return store.save(text, evaluate(text))


def switch_leases(text, pool):
    """从一次完整计算中取该池的旧契约租约（新合并租约不迁移）与在池新租约。

    旧租约按 lease_key 去重；无论重试多少次，同一租约只登记一次。
    """
    result = run(text, {})
    old, fresh = {}, []
    for lease in result["leases"]:
        if lease["contract"] in pool_members(pool):
            key = "|".join([lease["contract"], lease["lease_id"], str(lease["rev"]), str(lease["a"])])
            old[key] = {"key": key, "contract": lease["contract"], "lease_id": lease["lease_id"],
                        "version": lease["rev"], "start": str(lease["a"]), "quantity": lease["quantity"],
                        "user": lease["user"]}
        elif lease["contract"] == pool:
            fresh.append(lease)
    return [old[k] for k in sorted(old)], fresh


def start_or_resume(text, pool, interrupt_after=None):
    name = normalize_pool(pool) or pool
    if len(pool_members(name)) <= 1:
        from app.errors import BusinessError
        raise BusinessError("POOL", "该产品不属于可合并席位池")
    leases, fresh = switch_leases(text, name)
    state = store.begin_switch(name, leases, interrupt_after)
    state["new_leases"] = len(fresh)
    state["new_seats"] = sum(x["quantity"] for x in fresh)
    state["contracts"] = list(contracts_for(name))
    state["occupied_seats"] = state["seats"] + state["new_seats"]
    return state


def current(pool):
    name = normalize_pool(pool) or pool
    state = store.switch_payload(name)
    state["contracts"] = list(contracts_for(name))
    return state
