#!/usr/bin/env ruby
require 'json'
require 'open3'
require_relative 'bitbucket'

def main
  branch = `git rev-parse --abbrev-ref HEAD`.strip
  abort("Not in a git repository") if branch.empty? || branch == 'HEAD'

  pr = find_open_pr_for_branch(branch)
  abort("No open PR found for branch: #{branch}") unless pr

  comments = fetch_pr_comments(pr[:id])
  abort("Failed to fetch comments") unless comments

  grouped = group_pr_comments(comments)

  unanswered = grouped
    .reject { |k, _| k == :general }
    .transform_values { |threads| threads.select { |t| t[:thread].size == 1 } }
    .reject { |_, threads| threads.empty? }

  if unanswered.empty?
    puts "No unanswered inline comments."
    return
  end

  puts JSON.pretty_generate(rate_with_claude(unanswered))
end

def rate_with_claude(unanswered)
  sections = unanswered.map do |file, threads|
    file_content = File.read(file) rescue "(file not readable)"
    comment_lines = threads.map { |t| "  Line #{t[:line]}: #{t[:thread].first[:body]}" }.join("\n")
    "=== FILE: #{file} ===\n#{file_content}\n\nComments on #{file}:\n#{comment_lines}"
  end

  prompt = <<~PROMPT
    I have code review comments that need to be addressed. For each comment, rate the complexity of implementing the change on a scale of 0 to 5:
    - 0: Trivial (rename, typo, formatting)
    - 1: Simple (one-line change)
    - 2: Minor (small local change, a few lines)
    - 3: Moderate (multiple lines or small refactor)
    - 4: Complex (significant refactor or new logic)
    - 5: Very complex (architectural change or large refactor)

    Return ONLY a JSON array, no other text. Each element: { "file": "...", "line": N, "comment": "...", "complexity": N, "reason": "one sentence" }

    #{sections.join("\n\n")}
  PROMPT

  output, status = Open3.capture2('claude', '-p', stdin_data: prompt)
  abort("claude failed: #{output}") unless status.success?

  JSON.parse(output)
rescue StandardError => e
  abort("Failed to rate comments: #{e.message}")
end

main if __FILE__ == $PROGRAM_NAME
