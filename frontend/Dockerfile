FROM node:20.18-alpine
WORKDIR /app
# Copy lockfile too and install via `npm ci` so the image is reproducible:
# `npm install` ignores lockfile drift and can pull newer transitive versions
# than package-lock.json pins, which is exactly the kind of "works on my
# laptop, breaks on yours" trap we hit with the missing migrations.
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev"]
