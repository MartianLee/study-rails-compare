Rails.application.routes.draw do
  get  "/healthz",          to: "health#show"
  get  "/api/posts",        to: "posts#index"
  get  "/api/posts/:id",    to: "posts#show"
  post "/api/comments",     to: "comments#create"

  # Rails-only probes: same middleware, same router, different amount of
  # Active Record. Used to decompose where a Rails request actually spends time.
  get "/api/static",      to: "probes#static"
  get "/api/posts_pluck", to: "probes#pluck"
end
