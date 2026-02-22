FROM node:20-alpine AS build

WORKDIR /app

# Copy package files first for better caching
COPY package.json package-lock.json* ./
RUN npm install

# Copy source code
COPY . .

# Build for production
RUN npm run build

# ─── Production stage ────────────────────────────────────────
FROM node:20-alpine AS production

WORKDIR /app

# Install a simple static file server
RUN npm install -g serve

# Copy built files from build stage
COPY --from=build /app/dist ./dist

EXPOSE 3000

CMD ["serve", "-s", "dist", "-l", "3000"]
