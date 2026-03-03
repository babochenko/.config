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

  inline, general = comments.partition { |c| c[:file] }

  by_id = inline.each_with_object({}) { |c, h| h[c[:id]] = c }

  thread_root = lambda do |c|
    c[:parent_id] && by_id[c[:parent_id]] ? thread_root.call(by_id[c[:parent_id]]) : c
  end

  grouped = inline.group_by { |c| c[:file] }.transform_values do |file_comments|
    file_comments
      .group_by { |c| thread_root.call(c)[:id] }
      .values
      .sort_by { |t| thread_root.call(t.first)[:created_at] || '' }
      .map do |thread|
        root = thread_root.call(thread.first)
        {
          line: root[:line],
          thread: thread.sort_by { |c| c[:created_at] || '' }
        }
      end
  end

  grouped[:general] = general unless general.empty?

  puts JSON.pretty_generate(grouped)
end

main if __FILE__ == $PROGRAM_NAME
