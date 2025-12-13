# 认证模块 API 文档

**版本**: 1.0  
**日期**: 2025-12-13  

---

## 1. 获取当前用户信息

获取当前登录用户的详细信息，包括权限角色。

- **URL**: `/api/v1/auth/me` (注意：实际路由前缀取决于 `main.py` 中的配置，通常是 `/auth/me` 或 `/api/v1/auth/me`)
- **Method**: `GET`
- **Auth**: Required (Bearer Token)

### 请求头 (Headers)

| 参数名 | 必填 | 说明 |
|---|---|---|
| Authorization | 是 | Bearer <access_token> |

### 响应示例 (200 OK)
```json
{
  "id": 1,
  "username": "admin",
  "role": "admin"
}
```

### 响应示例 (200 OK - 普通用户)
```json
{
  "id": 2,
  "username": "user123",
  "role": "user"
}
```

### 错误响应 (401 Unauthorized)
```json
{
  "detail": "Could not validate credentials"
}
```

---

## 2. 用户注册

- **URL**: `/auth/register`
- **Method**: `POST`

### 请求体 (JSON)
```json
{
  "username": "newuser",
  "password": "securepassword"
}
```

### 响应示例 (200 OK)
```json
{
  "id": 3,
  "username": "newuser",
  "role": "user"
}
```

---

## 3. 用户登录

- **URL**: `/auth/login`
- **Method**: `POST`
- **Content-Type**: `application/x-www-form-urlencoded`

### 请求参数 (Form Data)
| 参数名 | 必填 | 说明 |
|---|---|---|
| username | 是 | 用户名 |
| password | 是 | 密码 |

### 响应示例 (200 OK)
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```
