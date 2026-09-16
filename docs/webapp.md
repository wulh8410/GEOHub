# GEO Check Web 工作台

这是 GEOHub 的本地浏览器界面。它保留 GEOHub 原始站点诊断，并增加独立的页面 SEO 快检；两个分数、证据与报告不混合。

## 启动

首次安装：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[web]'
```

启动页面服务（默认端口 8788）：

```powershell
.\scripts\start_geocheck.ps1
```

浏览器打开 `http://127.0.0.1:8788`。

Docker Desktop 可用时，也可以使用：

```powershell
docker compose up --build geocheck
```

此方式默认使用 `http://127.0.0.1:8787`。

## 两类报告

- **GEOHub 深度诊断**：沿用项目原生的代表页采样、AI 可访问性、实体清晰度、可回答性、证据可引用性、权威与信任、结构可提取性与维护性检查，生成原始 GEOHub HTML 报告。
- **页面 SEO 快检**：独立检查首个公开页面的标题、Meta 描述、Canonical、H1、页面语言、图片 alt、链接、robots.txt 与 sitemap 声明，生成独立 HTML 报告。

快检不会声称提供第三方流量、排名、WHOIS 或 AITDK 专有数据。若未来取得这类数据源的正式 API 与授权，可以在现有双报告结构中新增受控数据源。
