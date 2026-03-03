#!/usr/bin/env ruby
require_relative 'bitbucket'

def main
  branch = `git rev-parse --abbrev-ref HEAD`.strip
  abort("Not in a git repository") if branch.empty? || branch == 'HEAD'

  pr = find_open_pr_for_branch(branch)
  abort("No open PR found for branch: #{branch}") unless pr

  puts "\e[33mPR ##{pr[:id]}: #{pr[:title]}\e[0m"

  comments = fetch_pr_comments(pr[:id])
  abort("Failed to fetch comments") unless comments

  if comments.empty?
    puts "No comments."
    return
  end

  inline, general = comments.partition { |c| c[:file] }

  unless inline.empty?
    puts "\n\e[36m=== Inline Comments ===\e[0m"
    inline.group_by { |c| c[:file] }.each do |file, file_comments|
      puts "\n\e[33m#{file}\e[0m"
      file_comments.each do |c|
        puts "  Line #{c[:line]}: \e[32m@#{c[:author]}\e[0m"
        puts "  #{c[:body]}"
        puts
      end
    end
  end

  unless general.empty?
    puts "\n\e[36m=== General Comments ===\e[0m\n"
    general.each do |c|
      puts "\e[32m@#{c[:author]}\e[0m"
      puts c[:body]
      puts
    end
  end
end

main if __FILE__ == $PROGRAM_NAME
