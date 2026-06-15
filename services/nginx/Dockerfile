# ---------- Stage 1: Build Frontend ----------
FROM node:18-alpine AS frontend-builder
WORKDIR /app
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: Nginx Server ----------
FROM nginx:alpine

# 拷贝自定义 nginx 配置
COPY services/nginx/nginx.conf /etc/nginx/nginx.conf

# 清理默认静态文件
RUN rm -rf /usr/share/nginx/html/*

# 复制编译好的前端产物
COPY --from=frontend-builder /app/dist /usr/share/nginx/html

EXPOSE 8000
CMD ["nginx", "-g", "daemon off;"]
