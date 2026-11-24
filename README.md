# Market Data Consistency｜行情数据一致性与差异归因

从增量 L2 行情重建 25 档订单簿，在 10 秒窗口内与参考快照逐档比较。这个仓库是 [SingularityX Evolution SX-CH-002](https://github.com/SingularityX-Evolution/.github/blob/main/profile/challenge-board/tasks/SX-CH-002-market-data-consistency.md) 的个人作品集版本，非官方实现，不代表主办方认证。

*An offline Python showcase for reconstructing a 25-level limit order book, aligning 10-second windows, and measuring price and quantity discrepancies. The default demo uses synthetic inputs only.*

## 快速运行

需要 Python 3.10+。安装依赖后，默认演示无需网络、账号或行情数据。

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m src.main
```

结果写入 `output/`：`report.md` 展示一档量价的对比；`per_feature_metrics.csv` 包含 100 个量价字段的 Pearson 相关性（题面口径 IC）、MAE、RMSE 和有效配对数；`reconstructed.csv` 和 `reference.csv` 可用于复核。

**演示怎么验证？** 参考快照由合成行情规则直接生成，不读取重建结果。只在 12 个窗口中的一个窗口给参考买一量加 2：买一量 MAE 应为 `0.166667`，所有价格的 MAE 为 `0`。这验证的是实现能定位已知差异，不是市场实测成绩。

## 关键设计

- **重建盘口：** 以快照初始化，按输入顺序应用同一时间戳的更新；数量是绝对值，零数量删除对应价位。保留更深的价位，仅在输出时取前 25 档。
- **对齐窗口：** 使用半开区间 `[start, start + 10s)`。窗口结束时才到达的事件属于下一窗口，不能影响上一窗口。参考侧取窗口内最后一条完整记录，不跨记录拼接字段。
- **解释结果：** 价格和数量分别计量；相关性不是误差大小。缺失值不补齐，样本不足或序列恒定时不报告相关性。实际行情中的差异可能来自采样时刻、覆盖率或数据源口径，不能凭高低 IC 判定原因。

## 使用自己的数据

每次对比同一合约的两份 CSV；请只使用你有权处理的数据。程序不会下载市场数据。

```bash
python -m src.main --incremental path/to/incremental.csv --reference path/to/snapshots.csv
```

| 输入 | 格式 |
| --- | --- |
| 增量 L2 | `timestamp,is_snapshot,side,price,amount`，时间戳为整数微秒且不倒序，`side` 为 `bid` 或 `ask`，`is_snapshot` 为 `true` 或 `false`。同一时间戳下连续的快照行视为一次重置。 |
| 参考快照 | `timestamp` 为整数微秒，档位字段使用 `bids[0].price`、`bids[0].amount`、`asks[0].price` 等命名，最高到 `[24]`，空档留空。 |

重建侧只输出已被输入时间戳覆盖到右边界的窗口，因此最后一个未闭合窗口不会输出。无更新的已闭合窗口延续最近的可用盘口；本实现不检测断流，不能将盘口延续视为数据源连续性的证明。

## 展示范围

原项目探索了 BTCUSDT、ETHUSDT、BNBUSDT、DOTUSDT 的 Tardis 增量 L2 与 Tardis 参考快照。此版修正了旧实现的窗口边界，所以不沿用旧指标，也不将同源的增量/快照对比当作 Tardis 与 Binance 实采对比。公开版只覆盖离线订单簿重建与评估，不包含 Binance 实时采集、其他通道验证或隐藏评测成绩。
