# 项目目录结构（需随目录变更更新）

根路径：`D:/dizi/backend`

```
backend/
├─ main.py                 # FastAPI 入口，挂载路由/静态资源
├─ database.py             # SQLAlchemy 引擎与 Session 管理
├─ models.py               # 数据库模型
├─ schemas.py              # Pydantic 模型
├─ utils.py                # 加密与认证工具
├─ routers/                # 业务路由
│  ├─ auth.py              # 注册 / 登录
│  ├─ scores.py            # 曲谱资源
│  ├─ playlists.py         # 播放列表
│  ├─ recordings.py        # 录音上传/查询
│  └─ debug.py             # 调试日志收集
├─ uploads/                # 静态上传文件挂载目录
├─ Development_process/    # 开发文档（日期分目录）
│  └─ 2025-12-09/
│     └─ API列表_20251209_1618.md
├─ requirements.txt
├─ readme.md               # 项目规则与需求说明
└─ LICENSE
```

维护要求：
- 新增/删除目录或重要文件时同步更新本文件。
- 开发文档应存放在 `Development_process/YYYY-MM-DD/`，命名遵循 `文档名称_YYYYMMDD_HHMM.md`。

