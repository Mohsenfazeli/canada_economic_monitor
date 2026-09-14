FROM python:3.12-slim
WORKDIR /app
COPY app.py README.md requirements.txt LICENSE Dockerfile render.yaml .gitignore ./
COPY economy/ economy/
COPY templates/ templates/
COPY data/ data/
COPY tests/ tests/
COPY .github/ .github/
RUN python app.py build && useradd --create-home dashboard
USER dashboard
ENV PORT=8080
EXPOSE 8080
CMD ["python", "app.py", "serve", "--host", "0.0.0.0"]
