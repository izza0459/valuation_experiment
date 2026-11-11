FROM node:22-slim
WORKDIR /app
ARG API_PROXY_TARGET
ENV API_PROXY_TARGET=$API_PROXY_TARGET NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build
ENV NODE_ENV=production
EXPOSE 3000
CMD ["npm", "run", "start"]
