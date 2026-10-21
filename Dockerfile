FROM python:3.12-slim

WORKDIR /app

# unstructured[all-docs] 需要的系统库：libmagic 识别文件类型、poppler 渲染 pdf、tesseract 做 ocr
RUN apt-get update && apt-get install -y --no-cache-dir --no-install-recommends \
    libmagic1 \
    poppler-utils \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖再拷代码，改代码时不会重复构建依赖层
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 容器内日志实时输出，避免 print/logging 被缓冲
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

CMD ["python", "-m", "app.http.app"]
