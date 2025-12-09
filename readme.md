
# 竹笛智能练习平台 - 后端开发规范手册

## 1. 文档管理规则

- 所有开发文档必须存放在 `Development_process/YYYY-MM-DD/`
- 文档命名规范：`文档名称_YYYYMMDD_HHMM.md`
- 时间戳格式：`YYYYMMDD_HHMM`（精确到分钟）
- 根目录 `README` 仅记录项目规则和基本信息



## 2. 核心架构原则 (Architecture)
坚持分层架构（Layered Architecture），数据单向流动，禁止跨层“跳线”。

- ❌ 禁止行为  
  - 在 `api/routers` 中编写复杂业务逻辑（如 ABC 解析算法）  
  - 在 `models`（ORM）中写业务方法  
  - Service 层直接依赖 HTTP 请求对象 (`Request`/`Response`)
- ✅ 正确数据流向  
  - API Layer (`app/api`): 接收 HTTP 请求，Pydantic 校验，调用 Service  
  - Service Layer (`app/services`): 业务核心（评分计算、乐谱解析），调用 CRUD  
  - CRUD/Model Layer (`app/crud`, `app/models`): 仅做数据库读写

## 3. 目录归档规则 (Where to put files)
不要在根目录新建 `.py` 文件，按职责归档：

| 文件类型   | 存放位置            | 命名规范示例            |
| ---------- | ------------------- | ----------------------- |
| 数据表定义 | `app/models/`       | `user.py`, `score.py` (单数) |
| Pydantic 模型 | `app/schemas/`    | `user.py`, `token.py`   |
| API 路由   | `app/api/endpoints/`| `users.py`, `scores.py` (复数) |
| 复杂业务逻辑 | `app/services/`    | `ocr_service.py`, `audio_service.py` |
| 工具函数   | `app/core/utils.py` | 纯函数、无副作用       |
| 配置常量   | `app/core/config.py`| 只读不可写             |

## 4. 编码细节规范 (Coding Standards)
### 4.1 依赖注入 (Dependency Injection)
所有数据库会话必须通过 FastAPI 的 `Depends(get_db)` 获取，严禁手动创建全局 Session。

```python
# ✅ 正确
@router.get("/")
def get_scores(db: Session = Depends(get_db)):
    ...

# ❌ 错误
db = SessionLocal()
```

### 4.2 Pydantic Schemas
- 入参/出参分离：Create / Update / Response 通常分为三个 Schema  
- 示例：`ScoreCreate` 需要 `title`；`ScoreUpdate` 的 `title` 可选；`ScoreResponse` 包含 `id`, `created_at`  
- 严禁直接返回 ORM 对象给前端，必须经过 Schema 序列化

### 4.3 类型提示 (Type Hints)
Python 3.10+ 必须写类型提示，可显著降低低级错误率。

```python
def calculate_score(user_freqs: list[float], target_freqs: list[float]) -> dict:
    ...
```

## 5. 业务特定规则 (Domain Specific)
### 5.1 乐谱数据流
- ABC 优先：所有乐谱修改先更新 ABC 字符串，再由 Service 层解析生成 JSON  
- 禁止手动修改数据库中的 JSON 乐谱字段，避免 ABC 与 JSON 不一致

### 5.2 文件处理
- 上传图片/音频仅存物理文件或 OSS，数据库只存相对路径（如 `/static/scores/1.jpg`）  
- 禁止将二进制文件存入数据库 Blob 字段

## 6. Git 提交规范
- 提交前自检：
  - 是否新增依赖？若是，请更新 `requirements.txt`
  - 是否修改数据库模型？若是，请生成 Alembic 迁移脚本
- Commit message 模板：
  - `feat: 新增评分算法服务`
  - `fix: 修复 YIN 算法低频误判 bug`
  - `refactor: 重构目录结构为分层架构`
  - `docs: 更新 API 文档`



## 7. 操作数据规范

- 当需要删除文件时，严禁使用类似rm，等命令，而是mv命令以及类似的方式连带路径移动至recycle文件夹
