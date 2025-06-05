# Usar uma imagem base oficial do Python
FROM python:3.9-slim

# Definir variáveis de ambiente para Python não bufferizar stdout/stderr
ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1

# Definir o diretório de trabalho
WORKDIR /app

# Copiar o ficheiro de requisitos e instalar as dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar o resto da aplicação para o diretório de trabalho
COPY . .

# Expor a porta que a aplicação Flask/Gunicorn vai usar
EXPOSE 5001

# Comando para iniciar a aplicação com Gunicorn
# Ajuste o número de 'workers' conforme necessário para a sua aplicação e recursos
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "2", "app:app"]
