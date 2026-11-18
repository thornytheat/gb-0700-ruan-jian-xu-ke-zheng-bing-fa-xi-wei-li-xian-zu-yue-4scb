# 深度登记 软件许可证并发席位与离线租约

- 规模：中型
- 核心规则：按租约有效区间扫线统计并发，同刻先结束后开始；离线到期前始终占席，重复心跳不重复占用

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 会话接收 | 运行会话接收并核对证据 | `POST /api/1` | `app/modules/m1_sessions/rules.py` | `tests/test_sessions.py` |
| M2 产品映射 | 运行产品映射并核对证据 | `POST /api/2` | `app/modules/m2_products/rules.py` | `tests/test_products.py` |
| M3 租约裁决 | 运行租约裁决并核对证据 | `POST /api/3` | `app/modules/m3_leases/rules.py` | `tests/test_leases.py` |
| M4 并发扫描 | 运行并发扫描并核对证据 | `POST /api/4` | `app/modules/m4_concurrency/rules.py` | `tests/test_concurrency.py` |
| M5 超用归属 | 运行超用归属并核对证据 | `POST /api/5` | `app/modules/m5_excess/rules.py` | `tests/test_excess.py` |
| M6 采购对照 | 运行采购对照并核对证据 | `POST /api/6` | `app/modules/m6_purchase/rules.py` | `tests/test_purchase.py` |
| M7 补传审计 | 运行补传审计并核对证据 | `POST /api/7` | `app/modules/m7_audit/rules.py` | `tests/test_audit.py` |

## 陷阱登记

| TRAP | 现象 | 朴素实现会怎样 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-02 | BOM | 静默采信错误值 | 首列清理 | `app/modules/m1_sessions/rules.py` | `tests/test_sessions.py::test_sessions_bom` |
| TRAP-08 | 前导零 | 静默采信错误值 | 字符串保存 | `app/modules/m1_sessions/rules.py` | `tests/test_sessions.py::test_sessions_id` |
| TRAP-11 | 时区混合 | 静默采信错误值 | UTC归一 | `app/modules/m2_products/rules.py` | `tests/test_products.py::test_product_timezone` |
| TRAP-13 | 乱序补传 | 静默采信错误值 | 事件端点排序 | `app/modules/m4_concurrency/rules.py` | `tests/test_concurrency.py::test_sweep_sample_sorted` |
| TRAP-14 | 重复心跳 | 静默采信错误值 | 不重复占席 | `app/modules/m1_sessions/rules.py` | `tests/test_sessions.py::test_sessions_duplicate` |
| TRAP-19 | 采购版冲突 | 静默采信错误值 | 显式版本优先级 | `app/modules/m5_excess/rules.py` | `tests/test_excess.py::test_excess_capacity_version` |
| TRAP-23 | 同刻交接 | 静默采信错误值 | 先结束后开始 | `app/modules/m4_concurrency/rules.py` | `tests/test_concurrency.py::test_sweep_boundary` |
| TRAP-26 | 陈旧补传 | 静默采信错误值 | 递增版本 | `app/modules/m7_audit/rules.py` | `tests/test_audit.py::test_audit_stale` |
| TRAP-31 | 合并后重映射旧回执 | 旧租约被改挂到合并产品，旧回执失效或静默释放 | 租约保留原产品契约，回执只按原契约+同版本匹配，失配项单独审计 | `app/modules/m3_leases/rules.py` | `tests/test_pools.py::test_release_matches_original_contract_only` |
| TRAP-32 | 分产品限额算共享池 | 两个产品各自拿全部池容量，超用被漏计 | 合并视图按池内各契约采购量之和限席，容量逐契约拆解 | `app/modules/m5_excess/rules.py` | `tests/test_pools.py::test_merged_pool_does_not_double_book_capacity` |
| TRAP-33 | 切换中断后视图错乱 | 页面显示半迁移数据或重复占席 | 未完成切换落回旧版分产品视图；重试只接续未迁移租约 | `app/store.py`、`app/rollout.py` | `tests/test_switch.py::test_interrupted_switch_keeps_legacy_view` |
| TRAP-34 | 重试同一合并重复占席 | 每次重试重新登记已迁移租约 | 迁移台账按 lease_key 主键去重，已完成切换原样返回 | `app/store.py` | `tests/test_switch.py::test_retry_same_merge_does_not_double_occupy` |
| TRAP-35 | 切换期间新租约无处归 | 新合并租约被塞进某个原产品，虚增其超用 | 旧版视图单列"待切换"，席位照实呈现；切换完成后并入共享池 | `app/modules/m6_purchase/rules.py` | `tests/test_switch.py::test_new_merged_lease_issues_in_pool_not_old_contract` |
| TRAP-36 | 切换期间旧回执补传 | 新提交的旧契约租约被悄悄扩大合并范围 | 旧租约集合变化返回409，须显式重置后重新合并 | `app/store.py` | `tests/test_switch.py::test_additional_old_contract_lease_conflicts_until_reset` |

## 共享池

契约、池与切换状态机见 `docs/POOLS.md`。切换接口：`GET/POST /api/pools/{pool}`。

## 对账规则

输入记录=采信记录+隔离记录+空行；重复记录归隔离；算法输出另记业务单位，不冒充输入行数。金额/浓度/时长使用Decimal；证据含原始行号。池汇总的超用席位小时等于各原契约归属之和。

## 已知不覆盖

不支持超过2MB输入，不执行生产自动放行；异常值需人员复核。
