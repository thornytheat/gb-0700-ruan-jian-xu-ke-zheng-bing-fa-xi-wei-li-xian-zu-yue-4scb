# 席位定义

lease_id、user保持字符串。CAD-Pro、cad归一为CAD；Render归一为RENDER。合并产品CAD+RENDER（别名见 `app/pools.py`）用于新租约签发。kind取online、offline、heartbeat、release、capacity。start/end必须带时区并转换UTC。seats为正整数；capacity记录表示采购生效区间的席位上限。

## 契约与池

每条规范化事件带两个身份：`contract`（签发时的原产品，永不因合并改写）与
`pool`（由契约推导的共享池）。旧租约的 `contract` 保持 CAD 或 RENDER；以合并
产品签发的租约 `contract` 即 `CAD+RENDER`。详见 `docs/POOLS.md`。

在线租约可由同租约同版本release提前结束；release 只匹配相同 `contract` 与相同
`version`。契约或版本不匹配的回执不释放任何租约，记为
`RELEASE_CONTRACT_MISMATCH` / `RELEASE_VERSION_MISMATCH` 待人工核验。离线授权一直
占用至原到期时刻，即使收到release仍保留。心跳不建立租约。租约采用最高版本；
同版多条实体租约冲突隔离。租约ID在产品契约内唯一；不同产品允许相同租约号。

采购区间可重叠，最高version优先，同最高版不同数量返回CAPACITY_CONFLICT。采购
记录按原契约各自判定；共享池容量是池内各契约采购量之和，不会把同一条采购
重复计入多个产品。

并发使用半开区间[a,b)，结束同刻开始不重叠。采购边界必须切分并发段。超用责任
按租约开始时间倒序、再按编号倒序分配，分配席位严格等于超用数量；每席位同时
记录其原产品契约，便于池汇总与逐契约归属对账。超用席位小时为超用数量×秒数
/3600，Decimal计算。此工具只核验约定席位数，不含厂商复杂许可证条款。

线上租约在start同刻release得到零时占用，离线仍保留原到期。
