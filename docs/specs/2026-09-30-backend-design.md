# 立委持股查詢網站：後端設計文件

- 日期：2026-09-30
- 範圍：後端（爬蟲、資料庫、API、部署）
- 參考網站：https://legislator-wealth.tw/legislator/

## 1. 目標

做出一個網站，列出立法委員申報的股票持股，並用每日收盤價估算持股市值。
本文件只涵蓋後端。前端由其他組員負責，雙方透過 JSON API 串接。

### 1.1 必做功能（第 1 個月）

1. 立委列表：姓名、政黨、持股總市值，可依政黨篩選、依市值排序
2. 立委個人頁：持有的股票、股數、目前市值
3. 個股頁：哪些立委持有這檔股票
4. 市值排行：前 10 名
5. 每日自動更新股價（cron）

### 1.2 加分功能（第 2～3 個月）

- A. 監察院 PDF 解析自動化，擴大到更多立委
- B. 持股市值歷史走勢
- C. 前後兩次申報的持股變化（買進、賣出、新增、出清）

### 1.3 持股資料取得策略：B→A

1. 先挑 5～10 位立委，以「爬蟲下載 PDF → 自動抽取文字 → 輸出 CSV → 人工校正 → 匯入」的半自動流程建立資料，確保能 demo。
2. 之後再逐步自動化，擴大到全部立委。

### 1.4 不在範圍內

- 基金、不動產、存款等股票以外的財產
- 掃描檔（圖片型 PDF）的 OCR：遇到時再評估
- 使用者帳號系統：只有一個管理用 API Key

## 2. 技術選擇

| 項目 | 選擇 | 理由 |
|---|---|---|
| 語言 | Python 3 | 寫爬蟲最方便，伺服器已安裝 Python 3.14 |
| API 框架 | FastAPI | 自動產生 `/docs` 文件，方便前端組員試打 |
| ORM | SQLAlchemy 2 | 爬蟲與 API 共用資料表定義，可以不改程式就更換資料庫 |
| 資料庫版本管理 | Alembic | 第一天就導入，不手動改資料表 |
| 資料庫 | SQLite | 單一檔案、免架伺服器；需要時透過 `DATABASE_URL` 換成 PostgreSQL |
| HTTP 客戶端 | httpx | |
| PDF 解析 | pdfplumber | 可以抽取表格 |
| 測試 | pytest | |
| 部署 | Docker，放在自架 Ubuntu 26.04 伺服器（192.168.0.137） | |
| 排程 | 伺服器上的 cron | |

## 3. 架構（方案 1：單一專案，爬蟲與 API 分開執行）

```
cron ──觸發──▶ 爬蟲 CLI ──寫入──▶ SQLite ◀──讀取── FastAPI ──JSON──▶ 前端
                  │
                  └──▶ crawl_log（執行紀錄）
```

- 爬蟲與 API 是同一個專案、共用 `models`，但分開執行：`python -m app.crawler <來源>` 與 `uvicorn app.api:app`。
- 只有爬蟲（和管理用的 PATCH API）會寫入資料庫，一般 API 只讀，所以 SQLite 的「不適合同時寫入」限制不會造成問題。
- 資料庫連線位址從環境變數 `DATABASE_URL` 讀取。

### 3.1 預計目錄結構

```
app/
  config.py          設定（讀取環境變數）
  db.py              資料庫連線、session
  models.py          SQLAlchemy 資料表定義
  api/               FastAPI 路由
  crawler/
    __main__.py      CLI 入口
    base.py          共用：重試、crawl_log、交易
    twse_prices.py   上市股價
    tpex_prices.py   上櫃股價
    backfill.py      歷史股價回補
    declarations/    監察院申報：download / extract / parse / import
  services/          市值計算、持股變化比對等商業邏輯
migrations/          Alembic
tests/
  fixtures/          真實 API 回應與 PDF 範本
docs/specs/
```

### 3.2 為擴充預留的設計

| 未來擴充 | 預先做的準備 |
|---|---|
| 換成 PostgreSQL | 一律透過 SQLAlchemy 存取資料庫，連線位址放在 `DATABASE_URL` |
| 資料表變更 | 使用 Alembic 遷移 |
| 納入縣市議員等其他政治人物 | 資料表用 `politician` + `term`（含 `role`），而不是 `legislator` |
| 新增資料來源 | 每個來源一個模組，統一實作 `fetch → parse → save` |
| 爬蟲變多、變慢 | 爬蟲本來就和 API 分開執行，可以直接拆成獨立容器 |

## 4. 資料庫設計

```
politician ──< term
    │
    └──< declaration ──< holding >── stock ──< stock_price
crawl_log
```

### 4.1 `politician`：政治人物

| 欄位 | 型態 | 說明 |
|---|---|---|
| id | int PK | 網址一律用 id，不用姓名轉成的代稱（避免原網站 issue #2 的 404 問題） |
| name | text, not null | 中文姓名 |
| name_alt | text, null | 原住民族語名／羅馬拼音 |
| photo_url | text, null | |

### 4.2 `term`：任期

| 欄位 | 型態 | 說明 |
|---|---|---|
| id | int PK | |
| politician_id | FK → politician | |
| role | text, not null | `legislator` / `councilor` |
| session | text, not null | 例：第11屆 |
| district | text, null | 選區；不分區為空 |
| party | text, not null | 黨籍放在任期上，因為黨籍可能改變 |
| start_date | date, not null | |
| end_date | date, null | 現任為空 |

### 4.3 `declaration`：財產申報

| 欄位 | 型態 | 說明 |
|---|---|---|
| id | int PK | |
| politician_id | FK → politician | |
| declared_date | date, not null | 申報基準日 |
| source_url | text, not null | 監察院 PDF 網址 |
| pdf_sha256 | text, unique | 避免重複下載、重複解析 |
| parse_status | text, not null | `pending` / `parsed` / `verified` / `failed` |

### 4.4 `holding`：持股

| 欄位 | 型態 | 說明 |
|---|---|---|
| id | int PK | |
| declaration_id | FK → declaration | |
| stock_code | FK → stock | |
| owner | text, not null | `本人` / `配偶` / `未成年子女` |
| shares | int, not null | 股數，須大於 0 |
| raw_text | text, null | PDF 原文，方便對照查錯 |

### 4.5 `stock`：股票

| 欄位 | 型態 | 說明 |
|---|---|---|
| code | text PK | 例：`2330`；用文字型態保留前導 0 |
| name | text, not null | |
| market | text, not null | `TWSE`（上市）/ `TPEx`（上櫃）/ `ESB`（興櫃） |

### 4.6 `stock_price`：每日收盤價

| 欄位 | 型態 | 說明 |
|---|---|---|
| stock_code | FK → stock，複合 PK | |
| date | date，複合 PK | |
| close | decimal, not null | 收盤價 |

### 4.7 `crawl_log`：爬蟲執行紀錄

| 欄位 | 型態 | 說明 |
|---|---|---|
| id | int PK | |
| source | text | 例：`twse_prices` |
| started_at / finished_at | datetime | |
| status | text | `success` / `failed` |
| rows | int | 寫入筆數 |
| message | text, null | 錯誤或警告訊息 |

### 4.8 計算規則

- **市值不存進資料庫**，查詢時才計算：
  市值 = 該立委「最新一份申報（`parsed` 或 `verified`）」的每筆持股 × 該股票「最新收盤價」，再加總。
- 某檔股票沒有收盤價時，那筆持股的市值為 `null`，不當作 0；總市值只加總有價格的持股，並在回應中標示「有持股缺少價格」。
- 歷史走勢（B）：持股股數 × 每一天的 `stock_price`。
- 持股變化（C）：比較同一立委依 `declared_date` 排序後最新兩份申報的 `holding`，以 `(stock_code, owner)` 為單位計算股數差異。

## 5. API 設計

- 所有網址以 `/api/v1` 開頭；回應格式都是 JSON。
- 所有 GET 都是公開、唯讀的。

### 5.1 必做

| 方法 | 網址 | 說明 |
|---|---|---|
| GET | `/politicians` | 列表。參數：`party`、`sort`（`market_value` / `name`，加 `-` 代表由大到小）、`limit`（預設 20，最大 100）、`page` |
| GET | `/politicians/{id}` | 個人資料 + 持股明細 |
| GET | `/stocks` | 股票列表。參數：`sort=-holders`（依持有人數由多到少） |
| GET | `/stocks/{code}` | 個股資訊 + 持有的立委 |
| GET | `/meta` | 最新股價日期、最新申報日期、最後更新時間 |

排行不另開網址：市值前 10 名 = `/politicians?sort=-market_value&limit=10`。

`GET /politicians/{id}` 回應範例：

```json
{
  "id": 12,
  "name": "王小明",
  "name_alt": null,
  "party": "中國國民黨",
  "session": "第11屆",
  "declared_date": "2026-06-29",
  "price_date": "2026-09-30",
  "market_value": 15234000,
  "missing_price": false,
  "holdings": [
    {"stock_code": "2330", "stock_name": "台積電", "owner": "本人",
     "shares": 10000, "close": 1050.0, "market_value": 10500000}
  ]
}
```

回應同時提供 `declared_date` 與 `price_date`，讓前端清楚標示持股的申報日期和股價日期。

### 5.2 加分

| 方法 | 網址 | 說明 | 功能 |
|---|---|---|---|
| GET | `/politicians/{id}/history?from=&to=` | `[{date, market_value}]` | B |
| GET | `/politicians/{id}/changes` | 最新兩份申報的差異：`buy` / `sell` / `new` / `closed` | C |
| GET | `/declarations?status=` | 依解析狀態列出申報 | A |
| PATCH | `/declarations/{id}` | 人工校正持股、修改狀態；需要 `X-API-Key` | A |

### 5.3 共通規則

- 錯誤格式：`{"error": {"code": "not_found", "message": "找不到這位立委"}}`，搭配正確的 HTTP 狀態碼（400 / 401 / 404 / 422 / 500）。
- 驗證：寫入類 API 必須帶 `X-API-Key`，金鑰存放在環境變數 `ADMIN_API_KEY`。
- CORS：允許的前端網域寫在環境變數 `CORS_ORIGINS`；開發時包含 `http://localhost:*`。
- 文件：FastAPI 自動產生的 `/docs`。

## 6. 爬蟲設計

### 6.1 共同結構

每個來源實作三個步驟：

1. `fetch()`：發出 HTTP 請求，取得原始資料
2. `parse()`：純函式，把原始資料轉成乾淨的資料結構；不碰網路也不碰資料庫
3. `save()`：在同一個資料庫交易中 upsert

`base.py` 統一處理：重試、請求間隔、寫入 `crawl_log`、交易。

### 6.2 上市股價 `twse_prices`

- 來源：`https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL`（已實際確認可用）
- 欄位：`Date`、`Code`、`Name`、`ClosingPrice` 等，值都是字串
- 處理細節：
  - `Date` 是民國年格式（`1150929` → 2026-09-29）
  - `ClosingPrice` 是空字串或 `--`（當天無成交）時跳過，不存成 0
  - 同時 upsert `stock`（代號、名稱、`market=TWSE`）
  - 以 `(stock_code, date)` 為 PK，重複執行不會產生重複資料
- 排程：週一至週五 17:00，18:30 再執行一次作為保險

### 6.3 上櫃股價 `tpex_prices`

結構同 6.2，來源：`https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes`，欄位 `SecuritiesCompanyCode`、`CompanyName`、`Close`；沒有成交時 `Close` 是 `" ---"`。`market=TPEx`。

### 6.3.1 興櫃股價 `esb_prices`

來源：`https://www.tpex.org.tw/openapi/v1/tpex_esb_latest_statistics`，`market=ESB`。興櫃沒有收盤價，以 `LatestPrice`（最新成交價）代替；`0` 視為沒有成交。

### 6.4 歷史股價回補 `backfill`

- 一次性指令，指定日期範圍，逐日呼叫證交所「指定日期」的行情 API。
- 每次請求間隔至少 3 秒，避免 IP 被封鎖。
- 只回補有人持有的股票所需的日期範圍。

### 6.5 監察院財產申報 `declarations`

來源：監察院公職人員財產申報查詢網站 `priso.cy.gov.tw`。網頁是 JavaScript 動態產生的，背後有 JSON API（參考原網站 legislator-wealth.tw 的 `scripts/fetch-priso-pdfs.ts`，2026-09-30 已實測可用）：

- 查詢：`POST https://priso.cy.gov.tw/api/Query/QueryData`
  body：`{"Data": {"Type": "name", "Value": "<姓名>"}, "Page": {"PageNo": 1, "PageSize": 200, "OrderByNum": 0, "OrderBySort": ""}}`
  回應的每一筆包含 `Id`、`Name`、`Period`（期數）、`Dept`（機關，例如「立法院」）、`Title`、`PublishType`（`01一般申報`、`04信託申報`…）、`PublishDate`（`民國115年 03月 19日`）、`OverFiveYear`
- 下載：`POST https://priso.cy.gov.tw/api/Query/getFile`，body：`{"From": "base", "FileId": "<Id>"}`，回傳 PDF
- 請求需要帶 `origin: https://priso.cy.gov.tw` 和 `referer: https://priso.cy.gov.tw/layout/baselist`
- 同名同姓的人要用 `Dept` 篩選
- PDF 是文字型（不需要 OCR）。股票在「（八）有價證券 → 1. 股票」段落，只寫股票**名稱**、沒有代號，所以需要用名稱對應 `stock.code`。原網站的解析程式超過 2000 行，專門處理換行、斷字等例外，這證實了這一段要用半自動流程起步

階段 1（半自動，5～10 位立委）：

1. `download`：下載 PDF、計算 `pdf_sha256`；已經存在的就跳過
2. `extract`：用 pdfplumber 抽出股票表格，保存原始文字
3. `parse`：轉成 `(股票名稱, 所有人, 股數)`，並用名稱對應 `stock.code`
4. `export`：輸出 CSV 供人工檢查、修正
5. `import`：匯入修正後的 CSV，將申報標記為 `verified`

階段 2（自動化）：批次處理全部立委；成功的直接匯入並標記為 `parsed`，失敗的標記為 `failed`，再透過 CSV 或 `PATCH /declarations/{id}` 人工修正。

## 7. 錯誤處理

| 情況 | 處理方式 |
|---|---|
| 網路逾時、5xx | 重試 3 次，等待時間每次加倍 |
| 回應格式和預期不同 | 整批放棄、不寫入，在 `crawl_log` 記錄為 `failed` |
| 單筆資料異常 | 跳過該筆，記錄警告，其他照常處理 |
| 股票名稱對應不到代號 | 申報標記為 `failed`，等待人工處理，不猜測 |
| 寫入 | 整批包在同一個交易中 |

## 8. 測試

- **parse 單元測試**：使用 `tests/fixtures/` 中保存的真實 API 回應與 PDF，不連網路。
- **API 測試**：FastAPI TestClient 搭配測試專用的 SQLite 資料庫，涵蓋正常回應、篩選、排序、分頁、404、422、401。
- **計算測試**：市值計算（包含缺少價格的情況）、持股變化比對。
- 工具：pytest。每個功能完成時一併補上測試。

## 9. 部署

- 用 Docker 映像檔打包，部署到 192.168.0.137。
- SQLite 檔案放在掛載的 volume 中，重建容器不會遺失資料。
- 定期備份：每天複製一份 SQLite 檔案，保留 7 天。
- cron 透過 `docker exec`（或 `docker run --rm`）執行爬蟲指令。
- 環境變數：`DATABASE_URL`、`ADMIN_API_KEY`、`CORS_ORIGINS`。

## 10. 時程（約 3 個月）

| 週次 | 內容 |
|---|---|
| 1～2 | 專案骨架、資料表、Alembic、上市／上櫃股價爬蟲、cron |
| 3～4 | 必做 API；5～10 位立委的半自動申報資料；部署到伺服器，讓前端開始串接 |
| 5～6 | 加分 B：歷史股價回補、走勢 API |
| 7～8 | 加分 C：持股變化 API |
| 9～11 | 加分 A：申報 PDF 批次自動化、校正 API |
| 12 | 緩衝、補測試、準備 demo |
