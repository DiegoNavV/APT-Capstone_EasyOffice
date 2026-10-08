# ---------- build ----------
FROM node:20-alpine AS build
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Vite "hornea" las variables VITE_* en el bundle al compilar (no se pueden
# cambiar despues en runtime como un .env de backend). Default: el backend
# publicado en localhost:8000 por docker-compose.yml, porque quien hace el
# fetch es el navegador del usuario, no este contenedor.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# ---------- serve ----------
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
