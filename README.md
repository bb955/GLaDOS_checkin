# GLaDOS 自动签到

本项目保留两条路径：GitHub 云端只做账号状态检查；真正签到使用 Mac 上的可见浏览器打开 GLaDOS 官方页面，让官网自己执行验证和签到。

## 当前故障结论（2026-11-23）

最近一次 GitHub Actions 真实运行中，33 项离线测试通过，账号状态接口也认可现有登录会话，但真正签到被 Cloudflare Turnstile 拦截（`code=5`）。这说明 Cookie 可用，不代表云端 API 请求能通过人机验证。

因此：

- `checkin.py --mode status`：只检查登录状态，不签到。
- `checkin.py --mode checkin`：旧的直接 API 路径；当前可能被 Turnstile 拦截，不应在 GitHub 云端反复重试。
- `browser_checkin.py`：用 Playwright 打开官网真实页面，只点击官网签到按钮并读取官网返回结果；不伪造浏览器指纹、不提取或重放 Turnstile token、不绕过人工验证。
- `docs/workflows/glados-browser-checkin.yml`：Mac 自托管 Runner 工作流模板。**只能复制到新的私有仓库中启用。**

## 为什么需要新的私有仓库

当前 `bb955/GLaDOS_checkin` 是公开仓库，而且是一个公开 fork。GitHub 官方不建议在公开仓库使用自托管 Runner：公开仓库的 Pull Request 可能修改工作流并在 Runner 上执行不可信代码，从而危及 Mac 上的文件和浏览器登录态。公开 fork 也不能单独改成私有仓库。

请新建一个**独立的 Private repository（不要点 Fork）**，再把本项目代码复制过去。官方说明：
- [GitHub：自托管 Runner 安全建议](https://docs.github.com/en/actions/reference/security/secure-use)
- [GitHub：Fork 的可见性规则](https://docs.github.com/en/pull-requests/reference/forks)

## 启用 Mac 浏览器签到

1. 新建一个 GitHub 私有仓库，例如 `GLaDOS_checkin_private`。
2. 把本仓库的代码推送到新仓库。可以在 Mac 终端执行：

   ```bash
   git clone https://github.com/bb955/GLaDOS_checkin.git
   cd GLaDOS_checkin
   git remote remove origin
   git remote add origin https://github.com/你的用户名/GLaDOS_checkin_private.git
   git push -u origin main
   ```

3. 在新私有仓库中，把 `docs/workflows/glados-browser-checkin.yml` 复制为 `.github/workflows/glados-browser-checkin.yml`。
4. 在新私有仓库打开 **Settings → Actions → Runners → New self-hosted runner**，选择 macOS。GitHub 会显示专属下载和注册命令；按页面指示在 Mac 上执行。注册令牌是短时有效的，不要发给别人。
5. 第一次先在 Mac 的已登录桌面会话中，从终端运行 Runner 的 `./run.sh`，不要先安装成后台服务。这样浏览器窗口才有机会显示出来。保持终端和 Mac 唤醒，Runner 才能接收定时任务。
6. 在新私有仓库的 **Actions → GLaDOS Browser Check-in (Mac) → Run workflow** 手动运行一次。浏览器首次打开时，在该专用 Chromium 窗口登录 GLaDOS；如果页面要求 Turnstile 人工验证，就由你本人完成。登录状态保存在 Mac 本地的：

   ```
   ~/Library/Application Support/GLaDOSCheckin/ChromiumProfile
   ```

   不需要把 Cookie 或 User-Agent 放进新仓库的 Secrets。这个浏览器配置目录不要上传到 GitHub，也不要删除，否则需要重新登录。
7. 之后工作流每天按 UTC 10:17（北京时间/台北时间 18:17）尝试签到。Mac 必须开机、唤醒，并且 Runner 正在运行；如果 Turnstile 要求人工点击而你不在电脑旁，该次仍会失败，不会伪报成功。

## 本地手动运行

在 Mac 终端执行：

```bash
python3 -m pip install -r requirements-browser.txt
python3 -m playwright install chromium
python3 browser_checkin.py
```

第一次运行会打开专用浏览器窗口，需要你登录并按页面要求验证。后续使用同一个本地浏览器配置。

## 现有云端工作流

`.github/workflows/runGladosAction.yml` 现在只执行状态检查，不再从 GitHub 云端直接发送签到请求。它仍使用仓库 Secret `GLADOS_COOKIE` 做只读状态检查；真正签到请使用私有仓库中的 Mac 浏览器工作流。

请尊重 GLaDOS 和 Cloudflare 的验证机制。是否成功只以官网返回的明确结果为准。
