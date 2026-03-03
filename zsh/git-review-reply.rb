#!/usr/bin/env ruby
require 'json'
require_relative 'bitbucket'

def main
  branch = `git rev-parse --abbrev-ref HEAD`.strip
  abort("Not in a git repository") if branch.empty? || branch == 'HEAD'

  pr = find_open_pr_for_branch(branch)
  abort("No open PR found for branch: #{branch}") unless pr

  comments = fetch_pr_comments(pr[:id])
  abort("Failed to fetch comments") unless comments

  puts JSON.pretty_generate(group_pr_comments(comments))
end

main if __FILE__ == $PROGRAM_NAME
