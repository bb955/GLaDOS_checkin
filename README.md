# GLaDOS 自动签到 · 全新精简版

面向单个 GLaDOS 账号的 GitHub Actions 项目。与旧脚本分离；不自动兑换积分，也不尝试规避 GLaDOS 对自动签到的限制。

## 功能

- `status`：使用现有 Cookie 查询账号状态；**不发起签到**。
- `checkin`：先校验登录状态，再请求 `https://glados.cloud/api/user/checkin`，只有服务端明确回复签到成功或今日已签到才返回成功。
- 遇到 `code=4`（Automated check-in detected）直接失败，不进行 UA 伪造或反复尝试。
- Cookie、账号资料和完整服务器响应均不输出到公开日志。
- Python 3.12、Ubuntu 24.04；`requests` 唯一依赖；包含 18 项以上单元测试。

## 配置

在 GitHub → 仓库 → **Settings → Secrets and variables → Actions** 中：

1. **Repository secret：** `GLADOS_COOKIE`，取自你自己在 `glados.cloud` 的已登录会话，应同时具有 `gld:sess`、`gld:sess.sig`。**不要提交到代码**，不要粘贴到 Issue、公开日志或聊天。
2. **Repository variable 或 secret：** `GLADOS_USER_AGENT`，值必须是**获取 Cookie 时同一个浏览器**的完整 UA。可以在该浏览器的 Console 输入 `navigator.userAgent` 读取。不提供时，`status` 可查询登录状态，但 `checkin` 会拒绝尝试，避免无意义的请求。

旧名称 `GLADOS_UA` Secret 也兼容。

本项目当前使用固定主站 `glados.cloud`，不会将 Cookie 发送到其他站点。新仓库必须重新配置 Secret；**GitHub 不会跨仓库共享 Repository Secrets**。若将本项目放在已有仓库的新分支，现有同名 Secrets 可以复用。

## 使用

在 Actions → **GLaDOS Daily Check-in (Rewritten)** → **Run workflow** 中选择分支和模式，先运行 `status`，确认账号有效后再执行 `checkin`。工作流文件需要位于仓库默认分支，GitHub 才能提供手动触发入口；当前仅在开发分支创建时可能需要先合并或上传为默认分支。

正式默认分支每天 UTC 10:17（北京时间/台北时间 **18:17**）计划签到。GitHub 定时触发不保证精确到分钟。

在本地执行：

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python checkin.py --mode status
python checkin.py --mode checkin
```

## 错误说明

- `缺少 GLADOS_COOKIE`：Repository Secret 未配置。
- `缺少 GLADOS_USER_AGENT`：请在浏览器里取得**真实 UA** 并设置相应变量。
- `登录状态校验失败`：Cookie 失效或站点不接受当前会话。
- `code=4`：服务端拒绝自动签到。即使 Cookie 有效也不意味着自动签到受支持；可通过官方网页手动签到。
- `没有确认签到成功`：不把未知响应误报为成功。

请尊重服务条款。站点认证策略可能发生变化，项目不承诺自动签到永久可用。
