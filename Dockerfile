# Usar uma imagem base oficial do Nginx (versão Alpine é leve)
FROM nginx:alpine

# Remover a configuração padrão do Nginx (opcional, mas limpa)
RUN rm /etc/nginx/conf.d/default.conf

# Copiar o ficheiro de configuração personalizado do Nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copiar os ficheiros da aplicação (o seu index.html) para o diretório web do Nginx
# Certifique-se de que o seu ficheiro index.html
# está na mesma pasta que este Dockerfile quando for construir a imagem.
COPY index.html /usr/share/nginx/html/index.html

# Expor a porta 80 (porta padrão do HTTP)
EXPOSE 80

# Comando para iniciar o Nginx quando o container for executado
CMD ["nginx", "-g", "daemon off;"]
