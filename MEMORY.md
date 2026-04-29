# Long-Term Memory

## Key Facts
- 

## Decisions & Preferences
- 

## Lessons Learned

### task_create 正确参数
创建一次性定时任务的正确调用方式：
```python
task_create(
  title="任务标题",
  description="任务描述",
  type="scheduled",
  run_at="2026-04-28T22:18:00",  # 北京时间，直接填即可
  run_once=True,  # 必须设为 True
  user_prompt="执行指令"
)
```
注意：
- 不需要 `cron` 参数（只有循环任务才需要）
- 必须同时设置 `type="scheduled"` 和 `run_once=True`
- `run_at` 格式为 ISO 格式时间字符串

### get_time 时区
- `get_time` 返回北京时间 (Asia/Shanghai, 带 +08:00 时区信息)
- 任务调度器也统一使用北京时间比较

### memory_write / memory_get 正确用法
```
memory_write(content="内容", path="MEMORY.md")
memory_get(path="MEMORY.md")
```
注意：
- `memory_write` 会追加内容到文件末尾（append=true），不适合更新整个文件
- 要覆盖写入应使用 `write` 工具，路径为 `MEMORY.md`
- 读取使用 `memory_get`

## Important Context

### 企业微信推送配置
- 当前 IM session: `ses_2309718ffffeQejKXKkPG5uJ9C` (用户 GaoShuFeng)
- channel_type 应使用 `wecom_new`，而非 `wecom`
- `channel_message(session_id, message, channel_type="wecom_new")`