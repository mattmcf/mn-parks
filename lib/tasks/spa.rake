# frozen_string_literal: true

namespace :spa do
  desc "Build the Vite SPA and copy it into public/ for Rails to serve"
  task :build do
    sh "npm", "--prefix", "web", "ci"
    sh "npm", "--prefix", "web", "run", "build"
    sh File.expand_path("../../bin/install-spa", __dir__)
  end

  desc "Copy an already-built web/dist into public/"
  task :install do
    sh File.expand_path("../../bin/install-spa", __dir__)
  end
end
