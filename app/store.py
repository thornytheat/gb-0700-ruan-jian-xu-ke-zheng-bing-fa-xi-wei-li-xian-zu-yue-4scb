import sqlite3, json, hashlib
from datetime import datetime, timezone
from app.config import DATA_DIR, RULE_VERSION
from app.errors import BusinessError

def connect():
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(DATA_DIR/"runs.sqlite", timeout=15)
    db.row_factory=sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, digest TEXT NOT NULL, result TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0, decision TEXT NOT NULL DEFAULT '待复核', created TEXT NOT NULL, input_text TEXT NOT NULL DEFAULT '')")
    # 池切换是独立元数据：只登记哪些旧租约已纳入合并池视图，绝不回写租约的产品契约。
    db.execute("CREATE TABLE IF NOT EXISTS pool_switches (pool TEXT PRIMARY KEY, token TEXT NOT NULL, status TEXT NOT NULL, attempt INTEGER NOT NULL DEFAULT 0, pending TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS pool_migrations (pool TEXT NOT NULL, lease_key TEXT NOT NULL, contract TEXT NOT NULL, lease_id TEXT NOT NULL, lease_version INTEGER NOT NULL, start_at TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 0, migrated_at TEXT NOT NULL, PRIMARY KEY(pool,lease_key))")
    _ensure_columns(db)
    return db

def _ensure_columns(db):
    run_cols={r[1] for r in db.execute("PRAGMA table_info(runs)")}
    if "input_text" not in run_cols:
        db.execute("ALTER TABLE runs ADD COLUMN input_text TEXT NOT NULL DEFAULT ''")
    migration_cols={r[1] for r in db.execute("PRAGMA table_info(pool_migrations)")}
    if "quantity" not in migration_cols:
        db.execute("ALTER TABLE pool_migrations ADD COLUMN quantity INTEGER NOT NULL DEFAULT 0")

def save(text, result):
    # 池状态进入摘要：切换完成或回退会生成新的证据快照，旧快照保持原计算结果。
    # 带池视图元数据的快照与纯计算快照分开编号，避免复用缺少池证据的旧批次。
    token=result.get("pool_token","") if isinstance(result,dict) else ""
    snapshot="pools" if isinstance(result,dict) and "pool_switches" in result else "plain"
    digest=hashlib.sha256((RULE_VERSION+"\n"+snapshot+"\n"+token+"\n"+text).encode()).hexdigest()
    ident=digest[:16]
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO runs(id,digest,result,created,input_text) VALUES(?,?,?,?,?)",(ident,digest,json.dumps(dict(result,rule_version=RULE_VERSION),ensure_ascii=False),datetime.now(timezone.utc).isoformat(),text))
    return get(ident)

def get(ident):
    with connect() as db:
        row=db.execute("SELECT * FROM runs WHERE id=?",(ident,)).fetchone()
    if row is None: raise BusinessError("NOT_FOUND","批次不存在",404)
    item=dict(row);item["result"]=json.loads(item["result"]);item["rule_version"]=item["result"].get("rule_version","2026.11.18.1")
    return item

def history():
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT id,revision,decision,created FROM runs ORDER BY created DESC LIMIT 40")]

def review(ident,revision,decision):
    if not isinstance(decision,str) or decision not in {"通过","退回"}: raise BusinessError("DECISION","复核决定无效")
    current=get(ident)
    if decision=="通过" and current["result"].get("blocked"):
        raise BusinessError("BLOCKED","存在阻断项，请先修正数据",409)
    with connect() as db:
        changed=db.execute("UPDATE runs SET revision=revision+1,decision=? WHERE id=? AND revision=?",(decision,ident,revision)).rowcount
        if not changed: raise BusinessError("STALE","版本已更新，请刷新",409)
    return get(ident)


def _now():
    return datetime.now(timezone.utc).isoformat()

def switch_state(pool):
    with connect() as db:
        row=db.execute("SELECT * FROM pool_switches WHERE pool=?",(pool,)).fetchone()
        if row is None:return None
        migrated=[dict(r) for r in db.execute("SELECT * FROM pool_migrations WHERE pool=? ORDER BY lease_key",(pool,))]
    state=dict(row);state["pending"]=json.loads(state["pending"]);state["migrations"]=migrated
    return state

def switch_payload(pool):
    state=switch_state(pool)
    if state is None:
        return {"pool":pool,"status":"NONE","attempt":0,"total":0,"migrated":0,"remaining":0,
                "seats":0,"migrated_seats":0,"view":"merged","migrations":[]}
    pending=state["pending"];migrated=state["migrations"]
    total=len(migrated)+len(pending)
    return {"pool":pool,"status":state["status"],"attempt":state["attempt"],"total":total,
            "migrated":len(migrated),"remaining":len(pending),
            "seats":sum(x["quantity"] for x in pending)+sum(x["quantity"] for x in migrated),
            "migrated_seats":sum(x["quantity"] for x in migrated),
            "view":"merged" if state["status"]=="COMPLETED" else "legacy",
            "created":state["created"],"updated":state["updated"],
            "migrations":migrated}

def switch_list():
    with connect() as db:
        pools=[r[0] for r in db.execute("SELECT pool FROM pool_switches ORDER BY pool")]
    return [switch_payload(pool) for pool in pools]

def view_context():
    """当前计算视图与快照令牌。

    只有切换未完成的池才强制回退旧版分产品视图；没有切换记录的池按合并池
    视图计算。令牌变化会产生新的证据快照，历史快照保持原样。
    """
    states=switch_list()
    views={s["pool"]:"legacy" for s in states if s["status"]!="COMPLETED"}
    token=";".join(f'{s["pool"]}:{s["status"]}:{s["attempt"]}:{s["migrated"]}:{s["migrated_seats"]}' for s in states)
    return views,states,token

def _switch_canonical(db,pool,pending):
    """切换已知的完整旧租约集合 = 已迁移台账 + 未迁移队列。"""
    known={r["lease_key"]:{"key":r["lease_key"],"contract":r["contract"],"lease_id":r["lease_id"],
                           "version":r["lease_version"],"start":r["start_at"],"quantity":r["quantity"]}
           for r in db.execute("SELECT * FROM pool_migrations WHERE pool=?",(pool,))}
    for lease in pending:known[lease["key"]]=lease
    return known

def _switch_token(known):
    return hashlib.sha256(json.dumps([known[k] for k in sorted(known)],ensure_ascii=False,sort_keys=True).encode()).hexdigest()

CORE_FIELDS=("key","contract","lease_id","version","start","quantity")

def _core(lease):
    return {k:lease.get(k) for k in CORE_FIELDS}

def begin_switch(pool,leases,interrupt_after=None):
    """开始或接续一次池切换。

    leases 为本次采信的旧契约租约（已按 lease_key 去重）。重复调用同一切换
    只补齐未迁移项：已迁移项由主键去重，不会重复占席。

    判定规则：切换身份就是旧租约集合本身。输入必须与已登记的集合一致（同
    一合并），才允许接续未迁移部分；缺少、增加或改写任一旧租约都说明这是另
    一次合并，返回 409，必须显式重置后才能重新开始。以合并产品签发的新租约
    不在旧租约集合内，不参与判定。
    """
    if not isinstance(pool,str) or not pool:raise BusinessError("POOL","席位池无效")
    if interrupt_after is not None and (type(interrupt_after) is not int or interrupt_after<0):
        raise BusinessError("INTERRUPT","中断点须为非负整数")
    now=_now()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT * FROM pool_switches WHERE pool=?",(pool,)).fetchone()
        pending=[] if row is None else json.loads(row["pending"])
        known=_switch_canonical(db,pool,pending)
        incoming={x["key"]:x for x in leases}
        if row is not None and (set(known)!=set(incoming) or any(_core(known[k])!=_core(incoming[k]) for k in known)):
            raise BusinessError("SWITCH_CONFLICT","该席位池已有其他合并，请核对输入或显式重置",409)
        if row is None:
            token=_switch_token(incoming)
            db.execute("INSERT INTO pool_switches(pool,token,status,attempt,pending,created,updated) VALUES(?,?,?,?,?,?,?)",(pool,token,"PENDING",0,json.dumps(leases,ensure_ascii=False,sort_keys=True),now,now))
            row=db.execute("SELECT * FROM pool_switches WHERE pool=?",(pool,)).fetchone()
            known=dict(incoming)
        done={r[0] for r in db.execute("SELECT lease_key FROM pool_migrations WHERE pool=?",(pool,))}
        remaining=[x for x in (known[k] for k in sorted(known)) if x["key"] not in done]
        if row["status"]=="COMPLETED" and not remaining:
            return switch_payload(pool)
        batch=remaining if interrupt_after is None else remaining[:interrupt_after]
        for lease in batch:
            db.execute("INSERT OR IGNORE INTO pool_migrations(pool,lease_key,contract,lease_id,lease_version,start_at,quantity,migrated_at) VALUES(?,?,?,?,?,?,?,?)",(pool,lease["key"],lease["contract"],lease["lease_id"],lease["version"],lease["start"],lease["quantity"],now))
        left=remaining[len(batch):]
        status="COMPLETED" if not left else "INTERRUPTED"
        db.execute("UPDATE pool_switches SET status=?,attempt=attempt+1,pending=?,updated=? WHERE pool=?",(status,json.dumps(left,ensure_ascii=False,sort_keys=True),now,pool))
    return switch_payload(pool)

def reset_switch(pool):
    with connect() as db:
        db.execute("DELETE FROM pool_migrations WHERE pool=?",(pool,))
        db.execute("DELETE FROM pool_switches WHERE pool=?",(pool,))
    return switch_payload(pool)
