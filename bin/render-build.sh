#!/usr/bin/env bash
# Render build: gems + Vite SPA + copy SPA into public/ + migrate + seed.
# Free-plan services have no pre-deploy command, so migrations run here.
set -o errexit
set -o nounset
set -o pipefail

bundle install --jobs=4 --retry=3

npm --prefix web ci
npm --prefix web run build
./bin/install-spa

bin/rails db:migrate
bin/rails db:seed
