# GitHub Pages 每日投资建议部署

## 1. 添加仓库 Secrets

在 GitHub 仓库打开 **Settings → Secrets and variables → Actions**，添加：

- `DEEPSEEK_API_KEY`：DeepSeek API Key（必需）
- `ALPHAADVANTAGE_API_KEY`：当前盘中行情数据源的 API Key（必需）
- `JINA_API_KEY`：新闻搜索 Key（建议配置）
- `SEC_USER_AGENT`：SEC 要求的身份标识，例如 `Your Name email@example.com`（建议配置）
- `SUPABASE_URL`：Supabase 项目的 Project URL（必需）
- `SUPABASE_SECRET_KEY`：Supabase 的 `sb_secret_...` Key（必需，仅供 Actions 后端读取）
- `SUPABASE_USER_ID`：你的 Supabase Auth 用户 UUID（必需）

不要把任何 Key 写入 `.env` 后提交到 GitHub。

## 2. 启用 GitHub Pages

打开 **Settings → Pages → Build and deployment**，将 Source 设为 **GitHub Actions**。

工作流 `.github/workflows/daily-advisor-pages.yml` 会：

1. 工作日纽约时间 10:15 触发；
2. 更新盘中行情；
3. 验证至少 90% 的股票具有当日行情，覆盖不足时停止分析；
4. 调用 DeepSeek V4 Flash 生成唯一一份当日建议；
5. 导出 `docs/data/advice.json`；
6. 保存公开建议历史（真实持仓不会提交到仓库）；
7. 发布 `docs/` 到 GitHub Pages。

当前研究池固定为 25 只 Nasdaq-100 个股，定义在 `tools/universe.py`。筛选侧重大型、流动性、商业质量与行业覆盖；减少模型在 100 个名字之间漂移。行情以 Yahoo 为主源，Alpha Vantage 仅补抓缺失标的，因此不会日常耗尽免费 25 次额度。

首次部署也可以在 **Actions → Daily advisor and GitHub Pages → Run workflow** 手动触发。

## 3. 配置私有持仓同步

1. 在 Supabase 新建项目，在 **SQL Editor** 执行 `supabase/migrations/001_user_ledgers.sql`。
2. 在 **Authentication → URL Configuration** 中，把 GitHub Pages 地址设置为 Site URL，并加入 Redirect URLs。
3. 在 **Project Settings → API Keys** 复制 Project URL 和 `sb_publishable_...` Key，填入 `docs/assets/js/supabase-config.js`。
4. 部署网页后输入邮箱，点击“发送登录链接”；首次登录后，在 **Authentication → Users** 复制自己的 User UID，保存为 GitHub Secret `SUPABASE_USER_ID`。
5. 将 `sb_secret_...` Key 保存为 GitHub Secret `SUPABASE_SECRET_KEY`。绝对不要把它写入网页、源码或 `supabase-config.js`。

如果把网页安装到手机主屏幕，邮件链接通常会在系统浏览器打开，而浏览器与主屏幕 Web App 不共享登录会话。先在普通浏览器通过 Magic Link 登录一次，然后在网页同步区设置至少 8 位密码；之后电脑与主屏幕 App 都可用同一邮箱和密码分别登录。Magic Link 仍保留为首次验证方式。

浏览器端只能使用 publishable key。数据库迁移已启用 Row Level Security，每个登录用户只能读写自己的台账。GitHub Actions 使用 secret key 和指定 User UID，在每日分析前临时读取真实台账，并据此恢复零碎股、现金和含买入手续费的成本基础。

真实台账和持仓文件都不会提交到公开仓库；DeepSeek 会用它们推理，但系统提示禁止在公开建议中输出精确股数、现金、成本基础、手续费或账户标识。公开建议仍可能包含所分析或持有股票的代码，如果连股票代码也不希望公开，应使用受访问控制的站点而不是公开 GitHub Pages。

## 4. 实际交易记录

网页中的真实成交记录先保存在浏览器 `localStorage`；登录后会同步到 Supabase：

- 支持按美元金额录入零碎股交易；
- 支持修改实际成交价、手续费和卖出实际收益；
- 支持覆盖自动行情价格；
- 支持 JSON 导入和导出备份。

登录同一邮箱后可以跨浏览器或设备同步。JSON 导入/导出仍可作为额外备份。

## 5. 时间说明

GitHub 的 cron 使用 UTC。工作流同时配置 14:15 和 15:15 UTC，再按 `America/New_York` 时区过滤，因此能够兼容美国夏令时和冬令时。GitHub 定时任务可能因平台排队而延迟几分钟。
