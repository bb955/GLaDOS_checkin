# GLaDOS 自动签到（GitHub Actions）

每天北京时间 **18:00** 自动运行，也可以在 **Actions → 开始每日签到 → Run workflow** 手动执行。

本项目会验证实际的 GLaDOS 接口响应：**签到成功或今日已签到时，Actions 才显示绿色**。Cookie 缺失、失效、权限拒绝、HTTP 错误或未知响应会让任务变红，并显示不含 Cookie 的错误说明。

## 初次设置 / 更新 Cookie

1. 在浏览器中登录 [GLaDOS](https://glados.cloud)，确认可以正常进入控制台。
2. 打开浏览器开发者工具，从当前已登录域名的网络请求中复制**完整的 Cookie 请求头值**（通常包含 `gld:sess` 和 `gld:sess.sig`）。不要复制 `Cookie:` 这几个字符，也不要把 Cookie 提交到代码或公开日志中。
3. 在本仓库 **Settings → Secrets and variables → Actions → Repository secrets** 中创建或更新 `GLADOS_COOKIE`。此脚本当前支持单个账户，Cookie 原样填写，不用 `&` 分割。
4. 如果 GLaDOS 提示设备或浏览器不匹配，建议再添加 `GLADOS_UA` Secret，值为同一登录浏览器控制台执行 `navigator.userAgent` 得到的完整字符串。
5. 手动运行一次 Actions，展开 **Run checkin** 确认显示“签到成功”或“今日已签到”。首次成功后才能依赖定时运行。

## 域名设置

- 默认使用 `https://glados.cloud`，请求正文中的 `token` 自动取当前域名 `glados.cloud`。
- 如果 Cookie 来自其他支持的主站域名，在 **Repository variables**（非 Secrets）中添加 `GLADOS_ORIGIN`，例如 `https://glados.rocks`；脚本会自动让 API 域名、Origin、Referer 和 token 保持一致。
- 不同站点的 Cookie 可能不互通。**Cookie 必须与配置的域名对应**。
- `GLADOS_UA` 未配置时保留旧脚本的 `Mozilla/5.0` 作为默认值，但新版本账号校验可能需要完整且一致的浏览器 User-Agent。

## 运行环境

- 固定 `ubuntu-24.04`，避免 `ubuntu-latest` 在迁移 Ubuntu 26.04 期间意外改变。
- Python 已从 3.9 升级到 3.12，依赖只有 `requests`；时间处理使用 Python 标准库。
- 现有定时执行时间不变：`0 10 * * *`（UTC 10:00，北京时间 18:00）。
- GitHub Token 工作流权限设为只读。

## 诊断

| 日志提示 | 处理方式 |
| --- | --- |
| `未配置 GLADOS_COOKIE` | 创建或更新该 Repository Secret |
| `账号验证失败` | 重新登录配置的域名，获取新的完整 Cookie |
| `签到被拒绝` | 检查接口提示、登录域名和 `GLADOS_UA` |
| `签到未确认成功` | 接口返回了未知业务状态，请查看脱敏后的提示，不要把它当作成功 |
| `HTTP 401/403` | 登录态无效或服务器拒绝请求，更新 Cookie/UA 后重试 |

不要在公开 Issue、聊天记录或代码中贴出完整 Cookie。已经泄露时应退出 GLaDOS 会话并重新登录，以更新凭据。
