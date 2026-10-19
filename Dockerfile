# Production image: Vite SPA baked into public/, Rails + Puma serves both.
# Default host is Render native Ruby (render.yaml). This file is for Coolify / Fly / local prod.
# syntax=docker/dockerfile:1

ARG RUBY_VERSION=3.2.3
ARG NODE_VERSION=22

FROM node:${NODE_VERSION}-bookworm-slim AS spa
WORKDIR /spa
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM ruby:${RUBY_VERSION}-bookworm AS app
WORKDIR /rails

ENV RAILS_ENV=production \
    BUNDLE_DEPLOYMENT=1 \
    BUNDLE_WITHOUT="development:test" \
    RAILS_LOG_TO_STDOUT=true \
    RAILS_SERVE_STATIC_FILES=true \
    WEB_CONCURRENCY=1

RUN apt-get update -qq && \
    apt-get install --no-install-recommends -y libpq-dev libvips && \
    rm -rf /var/lib/apt/lists/*

COPY Gemfile Gemfile.lock .ruby-version ./
RUN bundle install && rm -rf /usr/local/bundle/cache

COPY . .
COPY --from=spa /spa/dist /rails/web/dist
RUN chmod +x bin/install-spa && ./bin/install-spa && \
    bundle exec bootsnap precompile --gemfile app/ lib/ || true

EXPOSE 3451
CMD ["bundle", "exec", "puma", "-C", "config/puma.rb"]
