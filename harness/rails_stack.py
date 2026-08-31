#!/usr/bin/env python3
"""Dump what the Rails app actually is, so "is that a real Rails app?" has an answer.

Records the live middleware stack, the Active Record methods Rails generated for
the models, and whether YJIT is on — straight out of the running process, into
docs/rails-stack.md.

Run it on its own; it starts a container.
"""
import json

from common import ROOT, compose, sh, start, stop

SNIPPET = r'''
require "/app/config/environment"
out = {}
out["rails_version"] = Rails.version
out["ruby"] = RUBY_DESCRIPTION
out["yjit_enabled"] = defined?(RubyVM::YJIT) ? RubyVM::YJIT.enabled? : false
out["api_only"] = Rails.application.config.api_only
out["eager_load"] = Rails.application.config.eager_load
out["middleware"] = Rails.application.middleware.map { |m| m.name }
out["prepared_statements"] = ActiveRecord::Base.connection.prepared_statements
out["association_methods"] = Post.instance_methods(false).grep(/tag|user|comment/).map(&:to_s).sort
out["generated_association_methods"] =
  Post.send(:generated_association_methods).instance_methods(false).map(&:to_s).sort
# Active Record defines attribute methods on first use, not at boot. Counting
# them before and after touching one is the cheapest proof of that.
out["attribute_methods_before_first_use"] =
  Post.send(:generated_attribute_methods).instance_methods(false).size
Post.new.title
out["attribute_methods_after_first_use"] =
  Post.send(:generated_attribute_methods).instance_methods(false).size
out["post_columns"] = Post.column_names
puts JSON.generate(out)
'''


def main():
    start("rails", env={"APP_CPUS": "4.0", "WEB_CONCURRENCY": "1", "APP_THREADS": "1",
                        "DB_POOL": "2", "RAILS_YJIT": "1"})
    try:
        cid = compose("ps -q rails").stdout.strip()
        with open("/tmp/_rails_stack.rb", "w") as f:
            f.write('require "json"\n' + SNIPPET)
        sh(f"docker cp /tmp/_rails_stack.rb {cid}:/tmp/probe.rb")
        r = sh(f"docker exec -e RAILS_ENV=production {cid} bundle exec ruby /tmp/probe.rb")
        data = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        stop("rails")

    lines = ["# What the Rails app in this repo actually is", "",
             "Read out of the running process by `harness/rails_stack.py`, not written by hand.",
             "", "```json",
             json.dumps({k: v for k, v in data.items() if k != "middleware"}, indent=2),
             "```", "",
             f"## Middleware stack ({len(data['middleware'])} entries)", "",
             "This is the live `Rails.application.middleware`. It is what `rails new --api`",
             "gives you, minus nothing — no middleware was removed to make the numbers better.",
             "", "```"] + [f"use {m}" for m in data["middleware"]] + ["```", ""]
    with open(f"{ROOT}/docs/rails-stack.md", "w") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
