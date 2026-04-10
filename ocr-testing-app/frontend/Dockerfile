FROM node:18-alpine AS build

WORKDIR /app

ARG VITE_API_URL=http://localhost:8000/api
ENV VITE_API_URL=$VITE_API_URL

# Copy package files
COPY package.json ./
RUN npm install

# Copy source and build
COPY . .
RUN chmod +x node_modules/.bin/* && npm run build

# Production stage - serve with nginx
FROM nginx:alpine

# Copy built files
COPY --from=build /app/dist /usr/share/nginx/html

# Nginx config to proxy /api to backend and handle SPA routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
