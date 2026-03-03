#!/usr/bin/env ruby
require 'json'
require 'open3'
require_relative 'bitbucket'

def timed(label)
  t0 = Time.now
  result = yield
  [result, Time.now - t0]
end

def fmt_duration(seconds)
  seconds >= 60 ? "#{(seconds / 60).to_i}m #{(seconds % 60).to_i}s" : "#{seconds.round(1)}s"
end

def main
  branch = `git rev-parse --abbrev-ref HEAD`.strip
  abort("Not in a git repository") if branch.empty? || branch == 'HEAD'

  pr = find_open_pr_for_branch(branch)
  abort("No open PR found for branch: #{branch}") unless pr

  comments, t_fetch = timed("fetch") { fetch_pr_comments(pr[:id]) }
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

  ratings, t_rate = timed("rate") { rate_with_claude(unanswered) }
  puts JSON.pretty_generate(ratings)

  easy_fixes = ratings.select { |r| r['complexity'] <= 2 }
  _, t_apply = timed("apply") { apply_fixes_with_claude(easy_fixes) }

  puts "\n=== Timing ==="
  puts "  Fetch comments : #{fmt_duration(t_fetch)}"
  puts "  Rate with Claude: #{fmt_duration(t_rate)}"
  puts "  Apply fixes    : #{fmt_duration(t_apply)}"
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

  json_str = output[/\[.*\]/m] || output
  JSON.parse(json_str)
rescue StandardError => e
  abort("Failed to rate comments: #{e.message}")
end

def apply_fixes_with_claude(easy_fixes)
  return if easy_fixes.empty?

  puts "\nApplying #{easy_fixes.size} fix(es) with complexity <= 2..."

  fix_list = easy_fixes.map.with_index(1) do |fix, i|
    "#{i}. File: #{fix['file']}\n   Line: #{fix['line']}\n   Comment: #{fix['comment']}\n   Reason: #{fix['reason']}"
  end.join("\n\n")

  prompt = <<~PROMPT
    Apply the following code review fixes. For each item, read the specified file, find the relevant line, and apply the appropriate change to address the review comment.

    #{fix_list}
  PROMPT

  require 'tempfile'
  Tempfile.create('git-review-fixes') do |f|
    f.write(prompt)
    f.flush
    f.rewind
    system('claude', in: f, out: $stdout, err: $stderr)
  end
end

main if __FILE__ == $PROGRAM_NAME
