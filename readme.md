竹笛智能练习平台 v0.1 开发需求说明书
版本: v0.1 (MVP Skeleton)
状态: 待开发
核心目标: 验证“伴奏+录音+A-B循环”的技术可行性，跑通基础业务流程。
1. 项目概述 (Overview)
一个专为竹笛学习者设计的 B/S 架构 Web 应用。解决竹笛“同指法不同调”的伴奏匹配痛点，提供基于浏览器的实时录音、合成与练习工具。
前端: Vue 3 + Pinia + Wavesurfer.js + Tone.js + Naive UI
后端: Python 3.10 + FastAPI
数据库: MariaDB 10.11
基础设施: Nginx 
本地测试环境使用wsl1 ubuntu 18.04
2. 角色与权限 (Roles)
角色	权限描述	v0.1 限制
普通用户 (User)	1. 注册/登录<br>2. 搜索/查看曲谱<br>3. 创建/编辑自己的播放列表<br>4. 进入练习室录音并保存	只能看公开曲谱和自己的数据。
管理员 (Admin)	1. 拥有上帝权限 (通过特定接口或后门)<br>2. 可管理所有曲谱元数据<br>3. 可查看/删除任意用户的列表和录音	不进行练琴操作 (无练习数据)。v0.1 暂不需要复杂的管理后台，通过 API 或简单界面管理即可。
3. 功能模块 (Functional Requirements)
3.1 认证模块 (Auth)
功能: 用户注册、登录、注销。
逻辑: 基于 JWT (JSON Web Token)。
数据: 写入 users 表。
3.2 资源库模块 (Library)
功能:
曲谱上传: 管理员/用户上传简谱图片(.jpg)和伴奏(.mp3)。
必填元数据: 曲名、笛子调性 (C/D/G...)、指法 (全按作5/2...)。
标签系统: 输入自定义标签 (如: "一级", "长音")。
展示:
卡片式列表。
筛选器: 必须包含 [调性] 和 [指法] 的联合筛选。
3.3 播放列表系统 (Playlist)
功能:
CRUD (增删改查) 播放列表。
将曲谱库中的曲子 "Add to Playlist"。
列表内曲目排序 (Sort)。
管理员特权:
管理员在前端可以看到“用户搜索框”。输入用户名后，界面显示该用户的播放列表，并可进行删除/修改操作。
3.4 核心练习工作台 (Workbench) —— 重中之重
页面布局:
上: 曲谱图片查看器 (支持鼠标滚轮缩放、拖拽)。
中: 校音器面板 (Tone.js 简易键盘，发单音用于对笛子音准)。
下 (固定): 多轨音频控制台。
音频交互逻辑:
加载: 自动加载伴奏波形。
A-B 循环: 用户可在波形上拖拽出黄色区域，点击“循环播放”，音频只在区域内重复。
录音: 点击红点 -> 请求麦克风 -> 伴奏播放的同时录制人声。
合成回放: 录制结束后，自动对齐两轨，点击播放可同时听到伴奏+人声。
保存: 点击保存，将合成后的音频上传至服务器 recordings 表。
v0.1 暂不做: 复杂的频谱仪、自动翻谱、MIDI 识别。
4. 数据库设计 (Schema Snapshot)
基于 MariaDB 10.11
users: id, username, password, role (user/admin)
scores: id, title, flute_key, fingering, image_path, audio_path, tags (JSON)
playlists: id, user_id, name
playlist_items: id, playlist_id, score_id, sort_order
recordings: id, user_id, score_id, file_path
5. 接口规划 (API Roadmap v0.1)
Auth
POST /auth/login
POST /auth/register
Scores (资源)
GET /scores (支持 query params: key=G, fingering=5)
POST /scores (Multipart upload: image + audio + metadata)
GET /scores/{id}
Playlists (列表)
GET /playlists (默认返自己的。Admin 可传 target_user_id 查看别人的)
POST /playlists
POST /playlists/{id}/items (加歌)
DELETE /playlists/{id}/items/{item_id}
Practice (练习)
POST /recordings (上传最终录音文件)