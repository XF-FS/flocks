---
name: coruna-daily-waterhole
description: 手动执行 Coruna 水坑网站日常采集、汇总去重、代理验证，并输出按模板整理的新增 XLSX 报送文件。
---

# Coruna Daily Waterhole

适用场景：
- 用户要求“执行今天的水坑网站日报”
- 用户要求“把当前 Quake + 验证 + 模板输出流程固化为 skill”
- 用户要求“只看新增 URL 并生成 xlsx 报送文件”

## 结论

这类任务适合固化为 `skill`：
- skill 负责定义完整执行流程
- agent 在执行时按 skill 分步调用现有脚本与命令
- 不额外依赖单独的总控脚本
- 不包含定时任务

## 工作目录

- `/Users/xff/Desktop/Agent_test/Coruna攻击研判`

## 依赖文件

参考模板文件：
- 当前目录下历史 `水坑网站` 报送 xlsx
- 例如：`情报报送_水坑网站20260507.xlsx`
- 输出时应优先参考最近一次正式提交版本的 sheet 结构、列顺序、字段内容和命名风格

现有脚本：
- 验证脚本：`verify_any_feature_with_proxy.py`
- 汇总去重+验证脚本：`/Users/xff/Desktop/Agent_test/Coruna攻击研判/merge_dedup_verify_daily.py`
- 模板导出脚本：`/Users/xff/Desktop/Agent_test/Coruna攻击研判/export_waterhole_daily_xlsx.py`

外部脚本：
- Quake: `~/.claude/skills/quake-query/scripts/quake_query.py`
- Matrix: `~/.config/opencode/skills/Matrix/scripts/matrix_query.py`

## 默认特征

1. `position: fixed;top:0;width: 0;height:0;left:-1000px;border:0`
2. `position:fixed;top:0;left:-1000px;pointer-events:none;border:0`
3. `position: fixed;top:0;width:0;height:0;left:-1000px;border:0`
4. `LaSDK.init`
5. `51la-ll.js`

## 执行全过程

### 1. 建立当日目录

执行时，agent 应创建：
- `daily_runs/YYYYMMDD/`

用于保存：
- Matrix 各条件结果
- Quake 各条件结果
- 合并去重结果
- 验证命中结果
- 进度文件
- 当日 xlsx 副本
- `run_summary.txt`

### 2. 采集 Matrix

优先逐条串行执行，避免频繁请求。

示例：

```bash
python3 ~/.config/opencode/skills/Matrix/scripts/matrix_query.py \
  --base-url 'https://asset01.threatbook-inc.cn/api/search/asset' \
  --search 'body="LaSDK.init" && after="2026-05-07"' \
  --page_size 500 -o ./matrix_lasdk_recent_day.csv --yes
```

5 条查询分别落成：
- `matrix_lasdk_recent_day.csv`
- `matrix_51la_recent_day.csv`
- `matrix_pos1_recent_day.csv`
- `matrix_pos2_recent_day.csv`
- `matrix_pos3_recent_day.csv`

推荐查询语句：
- `body="position: fixed;top:0;width: 0;height:0;left:-1000px;border:0" && after="YYYY-MM-DD"`
- `body="position:fixed;top:0;left:-1000px;pointer-events:none;border:0" && after="YYYY-MM-DD"`
- `body="position: fixed;top:0;width:0;height:0;left:-1000px;border:0" && after="YYYY-MM-DD"`
- `body="LaSDK.init" && after="YYYY-MM-DD"`
- `body="51la-ll.js" && after="YYYY-MM-DD"`

执行要求：
- Matrix 必须串行跑
- 优先读取返回总数 `total`
- 导出字段使用 Matrix skill 默认统一字段
- 相邻查询之间暂停数秒，默认按 5 秒控制

### 3. 采集 Quake

逐条串行执行，避免限频。

示例：

```bash
python3 ~/.claude/skills/quake-query/scripts/quake_query.py \
  --search 'body: "LaSDK.init" AND after: "2026-05-07"' \
  --size 0 --page_size 300 -o ./quake_lasdk_recent_day.csv --yes
```

5 条查询分别落成：
- `quake_lasdk_recent_day.csv`
- `quake_51la_recent_day.csv`
- `quake_pos1_recent_day.csv`
- `quake_pos2_recent_day.csv`
- `quake_pos3_recent_day.csv`

执行要求：
- Quake 必须串行跑
- 相邻查询之间暂停数秒，默认按 8 秒控制

### 4. 汇总去重 + 验证

输入：
- `matrix_*_recent_day.csv`
- `quake_*_recent_day.csv`

统一字段：
- `url`
- `ip`
- `domain`
- `port`
- `host`
- `title`
- `协议`
- `指纹`
- `网站返回状态`
- `备案`
- `主体公司`
- `更新时间`
- `地区`
- `来源`

去重键：
- `(host or ip, port, protocol)`

输出：
- `merged_recent_day_dedup.csv`
- `verified_any_feature_recent_day_hits.csv`
- `verify_recent_day_progress.txt`

执行要求：
- 默认直接调用复用脚本完成汇总去重和验证：

```bash
python3 /Users/xff/Desktop/Agent_test/Coruna攻击研判/merge_dedup_verify_daily.py \
  --run-dir /path/to/daily_runs/YYYYMMDD
```

- 如需覆盖并发与超时，可追加：

```bash
python3 /Users/xff/Desktop/Agent_test/Coruna攻击研判/merge_dedup_verify_daily.py \
  --run-dir /path/to/daily_runs/YYYYMMDD \
  --max-workers 4 \
  --timeout 10
```

验证策略：
- 默认不挂代理
- 如需代理，再显式附加 `https_proxy/http_proxy/all_proxy`
- 小并发，默认 `--max-workers 4`
- 超时默认 `--timeout 10`
- 命中任一默认 5 特征即写入结果
- 验证命中结果中应包含 `verified_at`
- `verified_at` 表示 agent 实际访问页面并确认命中特征的时间

### 5. 输出到模板

历史基准来源：
- 当前目录下所有历史 `水坑网站` 报送 xlsx
- 文件匹配时应优先包含：
  - `情报报送_水坑网站*.xlsx`
  - `*.情报报送_水坑网站.xlsx`
  - 其它名称中包含 `水坑网站` 的正式日报文件
- 忽略临时锁文件，例如 `.~...xlsx`

历史基准 sheet：
- 不只读取某一天
- 应扫描每个历史日报文件中与 `Sheet2` / `水坑网站` / `新增数据` 匹配的工作表
- 以所有历史日报的目标 sheet 汇总结果作为总基准

模板选择规则：
- 对比基准：使用所有历史日报合并结果
- 输出样式：优先使用最近一次正式提交版日报作为样式模板
- 不要只拿某一天的 URL 作为基准

对比逻辑：
- 从所有历史日报目标 sheet 中提取 `完整URL`
- 对 URL 做统一归一化：
  - 去空格
  - 小写
  - 去结尾 `/`
- 将所有天的 URL 汇总成历史总基准集合
- 对比验证命中结果中的 `url / verified_url`
- 仅保留历史总基准里不存在的新增 URL

发现时间规则：
- 输出到日报 `Sheet2` 的 `发现时间` 默认使用验证结果中的 `verified_at`
- 不再默认使用 Quake 返回的 `更新时间`
- 若 `verified_at` 缺失，才回退使用 `更新时间`

输出方式：
- 输出一个新的日报 xlsx
- 第二个工作表命名固定为：`Sheet2【水坑网站】M.D日新增数据`
- 示例：`Sheet2【水坑网站】5.7日新增数据`
- 其中月份和日期不补零，按自然显示
- 列结构保持与最近一次正式提交版一致
- `发现时间` 应写入实际验证命中特征时间 `verified_at`
- `分析研判依据` 应按正式提交版口径填写，不再默认留空
- 若最近一次正式提交版该列使用 `命中body特征`，则新增数据默认同样填写 `命中body特征`

输出文件名：
- 固定使用：`情报报送_水坑网站YYYYMMDD.xlsx`
- 示例：`情报报送_水坑网站20260507.xlsx`
- 日期部分使用 8 位 `YYYYMMDD`

默认直接调用复用脚本：

```bash
python3 /Users/xff/Desktop/Agent_test/Coruna攻击研判/export_waterhole_daily_xlsx.py \
  --base-dir /Users/xff/Desktop/Agent_test/Coruna攻击研判 \
  --run-dir /path/to/daily_runs/YYYYMMDD
```

脚本输出：
- `new_urls_YYYYMMDD.csv`
- `情报报送_水坑网站YYYYMMDD.xlsx`

### 6. 最终汇报

执行完成后，agent 应输出：
- Matrix 近一天数量
- Quake 近一天数量
- 合并去重后数量
- 验证命中数量
- 新增 URL 数量
- xlsx 输出路径
- 当日中间产物目录

## Skill 执行要求

当用户要求“执行 coruna-daily-waterhole”时，默认理解为：
1. 建立 `daily_runs/YYYYMMDD/`
2. 串行执行 Matrix 5 条查询并控制频率
3. 串行执行 Quake 5 条查询并控制频率
4. 汇总 Matrix + Quake 结果并去重
5. 使用代理执行验证
6. 将验证命中与所有历史日报的 `Sheet2` 基准对比，只保留新增 URL
7. 生成当天的 xlsx
8. 返回统计信息和结果路径

## 手动触发 skill 的口径

推荐用户指令：

```text
执行 coruna-daily-waterhole
```

或：

```text
跑今天的水坑网站日报，并输出 xlsx
```

## 可调参数

环境变量：
- `VERIFY_MAX_WORKERS`
- `VERIFY_TIMEOUT`
- `https_proxy`
- `http_proxy`
- `all_proxy`

## 不包含的内容

- 不包含定时任务
- 不包含单独总控脚本
- 由 agent 按 skill 分步执行现有命令和脚本
